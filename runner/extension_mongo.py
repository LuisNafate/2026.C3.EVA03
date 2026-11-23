"""Mide MongoDB comunitario desde la laptop mediante un túnel SSH local."""

import argparse
from contextlib import contextmanager
import csv
from decimal import Decimal
from getpass import getpass
import hashlib
import json
from pathlib import Path
import random
import re
from shlex import quote
from socketserver import BaseRequestHandler, ThreadingTCPServer
from threading import Thread
from time import sleep

from bson import Decimal128, json_util
import paramiko
from pymongo import MongoClient

from experimento import ROOT, Telemetry, base, expected, run_cell, utc, write_json
from benchmark_extendido import DIAGNOSTIC_TIMES, FINAL_TIMES, SIZES, check, cooldown, history, temperature
from probar_mongo_arm import ISOLATION, MONGOD_SHA, RELEASE, SSL_SHA, cents


PORT = 28081
UNIT = "edge-mongo-benchmark"
SUDO = "sudo -k -S -p '' "


class Tunnel(ThreadingTCPServer):
    daemon_threads = True

    def __init__(self, ssh):
        self.transport = ssh.get_transport()
        super().__init__(("127.0.0.1", 0), TunnelConnection)

    def __enter__(self):
        self.thread = Thread(target=self.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.shutdown()
        self.server_close()
        self.thread.join()


class TunnelConnection(BaseRequestHandler):
    def handle(self):
        channel = self.server.transport.open_channel(
            "direct-tcpip", ("127.0.0.1", PORT), self.client_address, timeout=8
        )
        with channel:
            def upstream():
                try:
                    while data := self.request.recv(65536):
                        channel.sendall(data)
                except (OSError, EOFError):
                    pass
                finally:
                    channel.shutdown_write()

            worker = Thread(target=upstream, daemon=True)
            worker.start()
            try:
                while data := channel.recv(65536):
                    self.request.sendall(data)
            except (OSError, EOFError):
                pass


def restore_services(host, user, password, raw):
    """Recover the experimental services using a fresh SSH connection."""
    command = (f"systemctl stop {UNIT}; "
               "if pgrep -x mongod; then exit 5; fi; "
               "systemctl start postgresql@17-main.service && "
               "systemctl is-active postgresql@17-main.service && pg_lsclusters")
    for attempt in range(1, 4):
        try:
            with paramiko.SSHClient() as fresh:
                fresh.load_system_host_keys(str(Path.home() / ".ssh/known_hosts"))
                fresh.connect(host, username=user, password=password, timeout=10,
                              allow_agent=False, look_for_keys=False)
                if base["log_command"](fresh, raw / f"recuperacion-servicio-{attempt}.log",
                                       SUDO + "/bin/sh -c " + quote(command), password, timeout=35):
                    raise RuntimeError("No se pudo levantar el clúster tras cerrar el servicio experimental.")
                return
        except (OSError, paramiko.SSHException) as exc:
            (raw / f"recuperacion-error-{attempt}.log").write_text(type(exc).__name__ + "\n", encoding="utf-8")
            if attempt == 3:
                raise
            sleep(15)


@contextmanager
def server(ssh, password, raw, host, user):
    capture = base["log_command"]
    _, out, _ = ssh.exec_command("find /var/tmp -maxdepth 1 -type d -user $(id -un) -name 'edge-mongo.*'", timeout=8)
    stage = out.read().decode().strip()
    if not re.fullmatch(r"/var/tmp/edge-mongo\.[A-Za-z0-9]{8}", stage):
        raise RuntimeError("Primero prepara un único directorio remoto con la prueba funcional de MongoDB.")
    prepare = (f"set -eu; cd {quote(stage)}; echo '{MONGOD_SHA}  mongod' | sha256sum -c -; "
               f"echo '{SSL_SHA}  libssl-arm64.deb' | sha256sum -c -; "
               "dpkg-deb -x libssl-arm64.deb compat")
    if capture(ssh, raw / "transferencia.log", prepare, timeout=120):
        raise RuntimeError("No se verificó el entorno de MongoDB.")
    isolation = (ISOLATION.replace("-p PrivateNetwork=yes ", "").replace("RuntimeMaxSec=120", "RuntimeMaxSec=32400")
                 + f" -p BindReadOnlyPaths={stage}:/opt/edge-mongo -p StateDirectory={UNIT}"
                   " --setenv=LD_LIBRARY_PATH=/opt/edge-mongo/compat/usr/lib/aarch64-linux-gnu")
    guard = f"""
set -eu
pg=postgresql@17-main.service
systemctl is-active --quiet "$pg"
clients=$(runuser -u postgres -- psql -XAtq -d postgres -c "SELECT count(*) FROM pg_stat_activity WHERE backend_type='client backend' AND pid<>pg_backend_pid()")
[ "$clients" = 0 ]
if pgrep -x mongod || ss -ltn 'sport = :{PORT}' | grep -q LISTEN; then exit 5; fi
restore() {{ systemctl start "$pg"; systemctl is-active "$pg"; }}
trap restore EXIT
trap 'exit 130' HUP INT TERM
systemctl stop "$pg"
systemd-run {isolation} --unit={UNIT} /bin/sh -c 'db=$(mktemp -d "$STATE_DIRECTORY/db.XXXXXXXX"); findmnt -T "$db" -no SOURCE,FSTYPE; exec /opt/edge-mongo/mongod --bind_ip 127.0.0.1 --nounixsocket --port {PORT} --dbpath "$db" --wiredTigerCacheSizeGB 0.25'
"""
    with base["channel"](ssh, SUDO + "/bin/sh -c " + quote(guard), 25) as stream:
        stream.sendall((password + "\n").encode())
        stream.shutdown_write()
        stream.settimeout(None)

        def copy_log():
            with (raw / "servidor.log").open("x", encoding="utf-8") as log:
                for line in stream.makefile("r"):
                    log.write(line)
                    log.flush()

        reader = Thread(target=copy_log, daemon=True)
        reader.start()
        try:
            yield
        finally:
            try:
                if not ssh.get_transport().is_active():
                    raise paramiko.SSHException("SSH desconectado durante el cierre")
                stopped = capture(ssh, raw / "cierre-servicio.log", SUDO + f"systemctl stop {UNIT}", password)
                reader.join(50)
                result = capture(ssh, raw / "estado-final.log", "pg_lsclusters; free -k; if pgrep -a -x mongod; then exit 5; fi; "
                                 "systemctl is-active postgresql@17-main.service")
                if stopped or result or reader.is_alive():
                    raise RuntimeError("Revisar parada de MongoDB y retorno de PostgreSQL.")
            except (OSError, RuntimeError, paramiko.SSHException):
                restore_services(host, user, password, raw)


def load(collection, path):
    batch = []
    with path.open(encoding="ascii") as source:
        for line in source:
            doc = json.loads(line)
            doc["_id"] = doc["order_id"]
            for item in doc["items"]:
                item["price"] = Decimal128(Decimal(str(item["price"])))
            doc["payment"]["final_total"] = Decimal128(Decimal(str(doc["payment"]["final_total"])))
            batch.append(doc)
            if len(batch) == 500:
                collection.insert_many(batch)
                batch.clear()
    if batch:
        collection.insert_many(batch)


class Query:
    def __init__(self, collection):
        self.collection = collection

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def execute(self, statement):
        query, pipeline, disk = statement
        with self.collection.aggregate(pipeline, allowDiskUse=disk, collation={"locale": "simple"}, maxTimeMS=8000) as cursor:
            if query == "q1":
                return [f"{row['_id']['country']}|{row['_id']['category']}|"
                        f"{cents(row['sum_subtotal'].to_decimal()):.2f}|{cents(row['avg_subtotal'].to_decimal()):.2f}|{row['items']}"
                        for row in cursor]
            return [f"{row['order_id']}|{cents(row['final_total'].to_decimal()):.2f}" for row in cursor]


def pipelines():
    source = (ROOT / "workloads/mongodb/consultas.js").read_text(encoding="utf-8")
    result = {}
    for name in ("q1", "q2"):
        literal = source.split(f"const {name} = ", 1)[1].split(";", 1)[0]
        literal = re.sub(r'([{,]\s*)([\w$]+)(?=\s*:)', r'\1"\2"', literal)
        result[name] = json.loads(re.sub(r",\s*([}\]])", r"\1", literal))
    return result


def experiment(args, password):
    raw = args.raw
    raw.mkdir(parents=True, exist_ok=False)
    status = {"status": "running", "started_utc": utc(), "completed": 0, "attempted": 0}
    write_json(raw / "estado.json", status)
    try:
        plan = pipelines()
        entries = {item["documents"]: item for item in json.loads((args.dataset / "manifiesto.json").read_text())}
        resume, completed = history(getattr(args, "resume", None))
        write_json(raw / "consultas.json", plan)
        write_json(raw / "protocolo.json", {"source": RELEASE, "server_sha256": MONGOD_SHA,
                   "cache_gb": 0.25, "memory_cap_mib": 320, "swap_cap_mib": 128,
                   "transport": "cliente PyMongo externo, túnel SSH y servidor loopback", "sizes_and_clients": SIZES,
                   "seed": 202603, "idle_s": 600, "pilot_seconds": [5, 30, 5], "pilot_repeats": 3,
                   "final_seconds": FINAL_TIMES, "final_repeats": 5,
                   "disk_diagnostic_seconds": DIAGNOSTIC_TIMES, "disk_diagnostic_repeats": 5,
                   "cooldown_threshold_c_above_baseline": 3, "cooldown_max_s": 300,
                   "resume": [path.name for path in resume], "skip_run_ids": sorted(completed)})
        with paramiko.SSHClient() as ssh:
            ssh.load_system_host_keys(str(Path.home() / ".ssh/known_hosts"))
            ssh.connect(args.host, username=args.user, password=password, timeout=10, allow_agent=False, look_for_keys=False)
            ssh.get_transport().set_keepalive(15)
            base["log_command"](ssh, raw / "entorno.log", "date -u; uname -srmo; cat /etc/os-release; free -k; df -h /; pg_lsclusters; cat /proc/sys/kernel/random/boot_id")
            with server(ssh, password, raw, args.host, args.user), Tunnel(ssh) as tunnel, MongoClient(
                "127.0.0.1", tunnel.server_address[1], directConnection=True, serverSelectionTimeoutMS=15000,
                connectTimeoutMS=8000, socketTimeoutMS=12000, retryReads=False, retryWrites=False,
            ) as client, Telemetry(ssh, raw / "telemetria.csv", "mongod", timeout=20) as telemetry:
                version = client.server_info()["version"]
                if version != "7.0.40":
                    raise RuntimeError(f"Versión inesperada: {version}")
                status.update(phase="reposo", phase_started_utc=utc())
                write_json(raw / "estado.json", status)
                check(telemetry, 600)
                baseline_temp = temperature(telemetry, 60)
                if baseline_temp is None:
                    raise RuntimeError("Telemetría insuficiente para estimar la temperatura basal.")
                status.update(baseline_temperature_c=baseline_temp)
                db = client.edge_lab
                oracle, fixtures = {}, {}
                write_json(raw / "validacion.json", fixtures)
                rng = random.Random(202603)
                with (raw / "corridas.csv").open("x", newline="", encoding="utf-8") as stream:
                    writer = None
                    for tag, cells, repeats, warm, measure, cool in (
                        ("piloto-topk", ((5000, 1),), 3, 5, 30, 5),
                        ("ampliacion", SIZES, 5, *FINAL_TIMES),
                        ("sin-disco", ((10000, 1),), 5, *DIAGNOSTIC_TIMES),
                        ("con-disco", ((10000, 1),), 5, *DIAGNOSTIC_TIMES),
                    ):
                        for size, clients in cells:
                            collection = db[f"orders_{size}"]
                            if size not in oracle:
                                check(telemetry, 1)
                                fixture = args.dataset / f"orders-{size}.jsonl"
                                if hashlib.sha256(fixture.read_bytes()).hexdigest() != entries[size]["sha256"]:
                                    raise RuntimeError(f"Hash de entrada inesperado en {size}.")
                                load(collection, fixture)
                                reference, qualifying = expected(fixture)
                                actual = collection.count_documents({})
                                if actual != size or (size == 5000 and qualifying <= 1000):
                                    raise RuntimeError(f"Falló la condición de recuento o Top-1000 en {size}.")
                                for name, pipeline in plan.items():
                                    if Query(collection).execute((name, pipeline, True)) != reference[name]:
                                        raise RuntimeError(f"Consulta {name} difiere del oráculo en {size}.")
                                fixtures[size] = {"documents": actual, "q1_rows": len(reference["q1"]),
                                                  "q2_rows": len(reference["q2"]), "q2_qualifying": qualifying}
                                write_json(raw / "validacion.json", fixtures)
                                oracle[size] = reference
                            for rep in range(1, repeats + 1):
                                queries = ["q2"] if tag in ("con-disco", "sin-disco") else rng.sample(list(plan), 2)
                                for name in queries:
                                    if f"v2-{tag}-{size}-{name}-c{clients}-r{rep}" in completed:
                                        continue
                                    status.update(phase=tag, documents=size, clients=clients, query=name, repetition=rep,
                                                  phase_started_utc=utc())
                                    write_json(raw / "estado.json", status)
                                    disk = tag != "sin-disco"
                                    row = run_cell(ssh, password, "", telemetry, raw, tag, size, name, clients,
                                                   rep, warm, measure, oracle[size][name], entries[size], synchronized=True,
                                                   connect=lambda: Query(collection), statement=(name, plan[name], disk),
                                                   engine=("MongoDB comunitario", version), telemetry_gap_s=5)
                                    if writer is None:
                                        writer = csv.DictWriter(stream, fieldnames=row)
                                        writer.writeheader()
                                    writer.writerow(row)
                                    stream.flush()
                                    status["attempted"] += 1
                                    if row["status"] != "completed":
                                        raise RuntimeError(f"{row['run_id']}: {row['error']}")
                                    status["completed"] += 1
                                    status.update(phase="enfriamiento", phase_started_utc=utc())
                                    write_json(raw / "estado.json", status)
                                    cooldown(telemetry, raw, row, cool, baseline_temp)
                for size in sorted(oracle):
                    for name, pipeline in plan.items():
                        check(telemetry, 1)
                        explain = db.command("explain", {"aggregate": f"orders_{size}", "pipeline": pipeline,
                                                         "cursor": {}, "allowDiskUse": True}, verbosity="executionStats")
                        (raw / f"plan-{size}-{name}.json").write_text(json_util.dumps(explain, indent=2), encoding="utf-8")
        status.update(status="completed")
    except Exception as exc:
        status.update(status="interrupted", error=str(exc))
        raise
    finally:
        status["ended_utc"] = utc()
        write_json(raw / "estado.json", status)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", default="rasp")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--resume", type=Path, help="Conserva los pilotos válidos de una sesión previa.")
    experiment(parser.parse_args(), getpass("Contraseña SSH (entrada oculta): "))
