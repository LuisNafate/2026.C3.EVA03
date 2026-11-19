"""Valida un MongoDB comunitario ARMv8-A en un servicio temporal aislado."""

import argparse
from decimal import Decimal, ROUND_HALF_UP
from getpass import GetPassWarning, getpass
import hashlib
import json
from pathlib import Path
import re
from shlex import quote
import warnings

import paramiko

from experimento import ROOT, base, expected, write_json

RELEASE = "https://github.com/themattman/mongodb-raspberrypi-binaries/releases/tag/r7.0.40-rpi-unofficial"
SHA256 = "ebbf873eeee24f2fedf7f418e08d0acd7fd68016ba46a0c6fda18b93fb44e7fa"
MONGOD_SHA = "59cfb8767ec7850fd69da83e06caa3090c9b2577a91d67c79abe26461093314b"
MONGO_SHA = "ed71c5588b48e3ed3cf6076a31cd98d3a41e4b1778e30f76e4ce9c38725ef9df"
SSL_SHA = "0fba4e602e499c97c4b623bd56295115667c312ff583221a71b476dd6983a5e0"
ISOLATION = (
    "--wait --pipe --collect -p DynamicUser=yes -p PrivateNetwork=yes -p PrivateDevices=yes "
    "-p PrivateTmp=yes -p ProtectHome=yes -p ProtectSystem=strict -p NoNewPrivileges=yes "
    "-p InaccessiblePaths=/var/lib/postgresql -p MemoryMax=320M -p MemorySwapMax=128M "
    "-p TasksMax=80 -p RuntimeMaxSec=120"
)

GUARD = """
set -eu
unit=postgresql@17-main.service
was_active=0
restore() {
    if [ "$was_active" = 1 ]; then
        systemctl start "$unit"
        printf 'PostgreSQL restaurado: '
        systemctl is-active "$unit"
    fi
}
trap restore EXIT
if systemctl is-active --quiet "$unit"; then
    clients=$(runuser -u postgres -- psql -XAtq -d postgres -c "SELECT count(*) FROM pg_stat_activity WHERE backend_type='client backend' AND pid<>pg_backend_pid()")
    if [ "$clients" != 0 ]; then
        echo "Prueba aplazada: existe otra conexión de PostgreSQL."
        exit 3
    fi
    was_active=1
    systemctl stop "$unit"
    echo "PostgreSQL detenido temporalmente para la prueba."
fi
systemctl is-active --quiet "$unit" && exit 4
if pgrep -x mongod >/dev/null; then
    echo "Prueba aplazada: otro mongod está activo."
    exit 5
fi
systemd-run {isolation} --unit="{unit}" -p RuntimeDirectory="{unit}" /bin/sh /opt/edge-mongo/smoke.sh /opt/edge-mongo
"""


def cents(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def verify(log, fixture):
    oracle, qualified = expected(fixture)
    prefixes = {key: [] for key in ("META", "Q1", "Q2")}
    for line in log.read_text(encoding="utf-8").splitlines():
        for key, items in prefixes.items():
            prefix = f"EDGE_{key} "
            if line.startswith(prefix):
                items.append(json.loads(line.removeprefix(prefix)))
    if [item["phase"] for item in prefixes["META"]] != ["insert", "restart"]:
        raise RuntimeError("No se registraron las dos fases.")
    if any(item["documents"] != 1000 or item["version"] != "7.0.40" for item in prefixes["META"]):
        raise RuntimeError("Versión o recuento inesperados.")
    q1 = [[f"{a}|{b}|{cents(total):.2f}|{cents(avg):.2f}|{n}"
           for a, b, total, avg, n in rows] for rows in prefixes["Q1"]]
    q2 = [[f"{i}|{cents(total):.2f}" for i, total in rows] for rows in prefixes["Q2"]]
    if q1 != [oracle["q1"]] * 2 or q2 != [oracle["q2"]] * 2:
        raise RuntimeError("Los resultados no coinciden con el oráculo.")
    return {"q1_groups": len(oracle["q1"]), "q2_rows": len(oracle["q2"]), "q2_qualifying": qualified}


def smoke(args, password):
    args.raw.mkdir(parents=True, exist_ok=False)
    report = {"status": "incomplete", "source": RELEASE, "archive_sha256": SHA256,
              "scope": "Variante comunitaria. Prueba funcional sin mediciones de rendimiento."}
    try:
        with args.archive.open("rb") as archive:
            if hashlib.file_digest(archive, "sha256").hexdigest() != SHA256:
                raise RuntimeError("El archivo no coincide con el SHA-256 fijado.")
        if args.compat:
            if hashlib.sha256(args.compat.read_bytes()).hexdigest() != SSL_SHA:
                raise RuntimeError("SHA-256 incorrecto en libssl1.1 de Debian.")
            report["libssl1_1_sha256"] = SSL_SHA
        manifest = json.loads((args.dataset.parent / "manifiesto.json").read_text())
        fixture_hash = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
        if fixture_hash != next(row["sha256"] for row in manifest if row["documents"] == 1000):
            raise RuntimeError("El dataset no coincide con los 1,000 documentos originales.")
        report["dataset_sha256"] = fixture_hash
        with paramiko.SSHClient() as ssh:
            ssh.load_system_host_keys(str(Path.home() / ".ssh/known_hosts"))
            ssh.connect(args.host, username=args.user, password=password, timeout=8, allow_agent=False, look_for_keys=False)
            ssh.get_transport().set_keepalive(10)
            capture = base["log_command"]
            capture(ssh, args.raw / "plataforma.log", "uname -srmo; dpkg --print-architecture; lscpu; free -k; pg_lsclusters")
            stage_command = ("find /var/tmp -maxdepth 1 -type d -user $(id -un) -name 'edge-mongo.*'"
                             if args.reuse_stage else "mktemp -d /var/tmp/edge-mongo.XXXXXXXX")
            _, out, _ = ssh.exec_command(stage_command, timeout=8)
            stage = out.read().decode().strip()
            if not re.fullmatch(r"/var/tmp/edge-mongo\.[A-Za-z0-9]{8}", stage):
                raise RuntimeError("Directorio aislado inesperado.")
            unit = "edge-mongo-" + stage.rsplit(".", 1)[-1].lower()
            with ssh.open_sftp() as sftp:
                if not args.reuse_stage:
                    sftp.put(str(args.archive), f"{stage}/release.tar.gz")
                    sftp.put(str(args.dataset), f"{stage}/orders-1000.jsonl")
                sftp.put(str(ROOT / "workloads/mongodb/smoke-edge.sh"), f"{stage}/smoke.sh")
                if args.compat:
                    sftp.put(str(args.compat), f"{stage}/libssl-arm64.deb")
                with sftp.open(f"{stage}/test.js", "w") as combine:
                    for name in ("consultas.js", "smoke-edge.js"):
                        combine.write((ROOT / f"workloads/mongodb/{name}").read_bytes())
                        combine.write(b"\n")
            prepare = (f"set -eu; cd {quote(stage)}; echo '{SHA256}  release.tar.gz' | sha256sum -c -; "
                       f"echo '{fixture_hash}  orders-1000.jsonl' | sha256sum -c -; "
                       f"if [ ! -f mongod ] || [ ! -f mongo ]; then tar -xzf release.tar.gz -- mongod mongo; fi; "
                       f"echo '{MONGOD_SHA}  mongod' | sha256sum -c -; echo '{MONGO_SHA}  mongo' | sha256sum -c -; "
                       "chmod 755 mongod mongo .; chmod 644 orders-1000.jsonl smoke.sh test.js; chmod 600 release.tar.gz")
            if args.compat:
                prepare += (f"; echo '{SSL_SHA}  libssl-arm64.deb' | sha256sum -c -; "
                            "dpkg-deb -f libssl-arm64.deb Package Version Architecture; dpkg-deb -x libssl-arm64.deb compat")
            if capture(ssh, args.raw / "transferencia.log", prepare, timeout=110):
                raise RuntimeError("Falló la comprobación del binario transferido.")
            prefix = "sudo -k -S -p '' "
            isolation = ISOLATION + f" -p BindReadOnlyPaths={stage}:/opt/edge-mongo"
            if args.compat:
                isolation += " --setenv=LD_LIBRARY_PATH=/opt/edge-mongo/compat/usr/lib/aarch64-linux-gnu"
            if capture(ssh, args.raw / "version.log", prefix + "systemd-run " + isolation
                       + f" --unit={unit}-version /bin/sh -c 'exec /opt/edge-mongo/mongod --version'", password, timeout=40):
                raise RuntimeError("mongod no pudo ejecutar --version. Consulta el log.")
            command = GUARD.replace("{isolation}", isolation).replace("{unit}", unit)
            code = capture(ssh, args.raw / "factibilidad.log", prefix + "/bin/sh -c " + quote(command),
                           password, timeout=145)
            capture(ssh, args.raw / "estado-final.log", "pg_lsclusters; free -k; pgrep -a -x mongod || :")
            if code:
                raise RuntimeError("No se completó la prueba funcional. Consulta el log.")
            report.update(verify(args.raw / "factibilidad.log", args.dataset), status="completed")
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        write_json(args.raw / "resumen.json", report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--compat", type=Path, help="Paquete ARM64 libssl1.1 1.1.1w-0+deb11u8, solo para extraer.")
    parser.add_argument("--reuse-stage", action="store_true", help="Reutiliza el único directorio remoto de transferencia de esta cuenta.")
    args = parser.parse_args()
    warnings.filterwarnings("error", category=GetPassWarning)
    smoke(args, getpass("Contraseña SSH (entrada oculta): "))
