"""Retoma las celdas pendientes de benchmark-v1 conservando sus crudos."""

import argparse
import csv
from getpass import GetPassWarning, getpass
import json
from pathlib import Path
import random
import re
import warnings

import paramiko

from experimento import Psql, QUERIES, Telemetry, base, run_cell, sleep, write_json


def resume(args, password):
    raw = args.raw
    raw.mkdir(parents=True, exist_ok=False)
    previous = args.previous
    plan = json.loads((previous / "plan_final.json").read_text(encoding="utf-8"))
    db = plan["db"]
    if not re.fullmatch(r"edge_lab_\d{8}_\d{6}", db):
        raise ValueError("El nombre de la base no corresponde a un ensayo.")
    refs = json.loads((previous / "referencias.json").read_text(encoding="utf-8"))
    stored = json.loads((previous / "tamanos_almacenados.json").read_text(encoding="utf-8"))
    entries = {e["documents"]: e for e in stored}
    cells = ((50000, 1), (10000, 2), (10000, 5))
    write_json(raw / "enmienda.json", {
        "origen": previous.name, "db": db, "celdas": cells, "motivo":
        "Q1 a 50k devolvió filas válidas fuera de la ventana de 5 s (v1, repetición 2).",
        "cambios": "Calentamientos terminan antes de una barrera común. Q1 a 50k usa 20 s. "
                   "Q2 a 50k y concurrencia restante conservan 5 s. Cinco repeticiones en estas celdas.",
        "incorporacion": "Se usan las 40 corridas válidas v1 de 1k a 25k con c1 y las 30 v2. "
                         "Se conservan los cuatro intentos originales de 50k como antecedente.",
    })
    with paramiko.SSHClient() as ssh:
        ssh.load_system_host_keys(str(Path.home() / ".ssh/known_hosts"))
        ssh.connect(args.host, username=args.user, password=password, timeout=10, allow_agent=False, look_for_keys=False)
        ssh.get_transport().set_keepalive(15)
        capture = base["log_command"]
        capture(ssh, raw / "entorno.log",
                "date -u; uname -srmo; cat /etc/os-release; cat /proc/sys/kernel/random/boot_id; free -k; vcgencmd get_throttled")
        with Psql(ssh, password, db) as probe:
            for n in entries:
                if probe.execute(f"SELECT count(*) FROM orders_{n};") != [str(n)]:
                    raise RuntimeError(f"Persistencia incompleta en {n}.")
        base["emit"](raw, "Continuidad confirmada. Inicia matriz de continuación con protocolo enmendado.")
        rng = random.Random(202603)
        with (raw / "corridas.csv").open("x", encoding="utf-8", newline="") as stream, Telemetry(ssh, raw / "telemetria.csv") as telem:
            writer = None
            for n, c in cells:
                for rep in range(1, 6):
                    order = list(QUERIES)
                    rng.shuffle(order)
                    for q in order:
                        window = 20 if n == 50000 and q == "q1" else plan["window_s"]
                        report = run_cell(ssh, password, db, telem, raw, "final", n, q, c, rep, 1, window,
                                          refs[str(n)][q], entries[n], synchronized=True)
                        if writer is None:
                            writer = csv.DictWriter(stream, fieldnames=report)
                            writer.writeheader()
                        writer.writerow(report)
                        stream.flush()
                        if report["status"] != "completed":
                            raise RuntimeError(f"{report['run_id']}: {report['error']}")
                        sleep(1)
                base["emit"](raw, f"Continuación completa: {n} documentos, {c} cliente(s).")
        plans = {}
        with Psql(ssh, password, db) as psql:
            for n in (1000, 10000, 50000):
                for name, statement in QUERIES.items():
                    plans[f"{n}-{name}"] = psql.execute(
                        "EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON) "
                        + statement.replace("__TABLE__", f"orders_{n}")
                    )
            psql.execute("SET jit=off;")
            plans["50000-q1-jit-off"] = psql.execute(
                "EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON) "
                + QUERIES["q1"].replace("__TABLE__", "orders_50000")
            )
        write_json(raw / "planes.json", plans)
        capture(ssh, raw / "estado-final.log",
                "date -u; cat /proc/sys/kernel/random/boot_id; uptime; free -k; vcgencmd get_throttled; pg_lsclusters")
        capture(ssh, raw / "kernel.log",
                """sudo -k -S -p '' sh -c 'journalctl -k --since "-1 hour" --no-pager |
                grep -Ei "out of memory|oom-kill|under.?voltage|throttl|I/O error" || true'""", password)
        base["emit"](raw, "Matriz de continuación y diagnóstico guardados.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.1.80")
    parser.add_argument("--user", default="rasp")
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    args = parser.parse_args()
    warnings.filterwarnings("error", category=GetPassWarning)
    try:
        resume(args, getpass("Contraseña SSH (entrada oculta): "))
    except Exception as error:
        if args.raw.is_dir():
            base["emit"](args.raw, f"Continuación interrumpida: {type(error).__name__}: {error}")
        raise
