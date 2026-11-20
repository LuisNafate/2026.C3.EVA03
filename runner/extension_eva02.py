"""Ejecuta el protocolo de ventanas largas de PostgreSQL desde la laptop."""

import argparse
import csv
from getpass import GetPassWarning, getpass
import json
from pathlib import Path
import random
import re
from statistics import median
from time import monotonic, sleep
import warnings

import paramiko

from experimento import Psql, QUERIES, Telemetry, base, run_cell, utc, write_json


SIZES = ((1000, 1), (5000, 1), (10000, 1), (10000, 2), (10000, 5), (25000, 1), (50000, 1))
FINAL_TIMES = (10, 60, 120)
DIAGNOSTIC_TIMES = (5, 30, 120)


def temperature(telemetry, seconds):
    floor = monotonic() - seconds
    values = [sample[4] for sample in telemetry.records if sample[0] >= floor]
    return median(values) if len(values) >= seconds / 2 else None


def cooldown(telemetry, raw, row, minimum, baseline):
    if minimum < 120:
        check(telemetry, minimum)
        return
    path = raw / "enfriamiento.csv"
    started = monotonic()
    values = [utc(), row["run_id"], baseline, row["temperature_max_c"]]
    current, recovered = None, False
    try:
        check(telemetry, minimum)
        while True:
            current = temperature(telemetry, 15)
            recovered = current is not None and current <= baseline + 3
            if recovered or monotonic() - started >= 300:
                break
            check(telemetry, 5)
    finally:
        header = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as output:
            writer = csv.writer(output)
            if header:
                writer.writerow(("started_utc", "run_id", "baseline_c", "load_max_c", "end_median_c", "cooldown_s", "within_baseline_plus_3c"))
            writer.writerow((*values, current, round(monotonic() - started, 1), int(recovered)))


def check(telemetry, duration):
    deadline = monotonic() + duration
    while monotonic() < deadline:
        if telemetry.incident:
            raise RuntimeError(telemetry.incident)
        sleep(min(1, max(0, deadline - monotonic())))


def experiment(args, password):
    raw = args.raw
    raw.mkdir(parents=True, exist_ok=False)
    status = {"status": "running", "started_utc": utc(), "completed": 0, "attempted": 0}
    write_json(raw / "estado.json", status)
    with paramiko.SSHClient() as ssh:
        capture = base["log_command"]
        try:
            baseline = args.previous
            db = json.loads((baseline / "plan_final.json").read_text())["db"]
            if not re.fullmatch(r"edge_lab_\d{8}_\d{6}", db):
                raise ValueError("Nombre de base experimental inesperado.")
            references = json.loads((baseline / "referencias.json").read_text())
            entries = {entry["documents"]: entry for entry in json.loads((baseline / "tamanos_almacenados.json").read_text())}
            resume = getattr(args, "resume", None)
            completed = set()
            if resume:
                with (resume / "corridas.csv").open(encoding="utf-8", newline="") as source:
                    completed = {row["run_id"] for row in csv.DictReader(source) if row["status"] == "completed"}
            write_json(raw / "protocolo.json", {
                "baseline": baseline.name, "sizes_and_clients": SIZES, "seed": 202603,
                "pilot_seconds_warm_measure_cool": [5, 30, 5], "pilot_repeats": 3,
                "final_seconds_warm_measure_cool": FINAL_TIMES, "final_repeats": 5,
                "diagnostic_seconds_warm_measure_cool": DIAGNOSTIC_TIMES,
                "cooldown_threshold_c_above_baseline": 3, "cooldown_max_s": 300,
                "idle_seconds": 600, "cache": "caliente", "stop_temperature_c": 70,
                "stop_available_kib": 65536, "resume": resume.name if resume else None,
                "skip_run_ids": sorted(completed), "resume_max_telemetry_gap_s": 5 if resume else None,
            })
            ssh.load_system_host_keys(str(Path.home() / ".ssh/known_hosts"))
            ssh.connect(args.host, username=args.user, password=password, timeout=10,
                        allow_agent=False, look_for_keys=False)
            ssh.get_transport().set_keepalive(15)
            prep = ("set -eu; date -u; uname -srmo; cat /etc/os-release; "
                    "cat /proc/sys/kernel/random/boot_id; timedatectl show -p NTPSynchronized; "
                    "pg_lsclusters; df -h /; free -k; vcgencmd get_throttled; "
                    "if pgrep -x mongod; then exit 4; fi")
            if capture(ssh, raw / "entorno.log", prep):
                raise RuntimeError("Falló la verificación del entorno. Consulta entorno.log.")
            with Psql(ssh, password, db) as psql:
                settings = psql.execute("SELECT version(); SHOW work_mem; SHOW shared_buffers; SHOW jit;")
                if not settings[0].startswith("PostgreSQL 17.12 "):
                    raise RuntimeError("Cambió la versión de PostgreSQL.")
                write_json(raw / "postgresql.json", settings)
                for n, _ in SIZES:
                    if psql.execute(f"SELECT count(*) FROM orders_{n};") != [str(n)]:
                        raise RuntimeError(f"Recuento inesperado para {n} pedidos.")

            rng = random.Random(202603)
            with Telemetry(ssh, raw / "telemetria.csv", timeout=20 if resume else 8) as telemetry, (raw / "corridas.csv").open("x", newline="", encoding="utf-8") as stream:
                if args.diagnostic:
                    status.update(phase="reposo_diagnostico", phase_started_utc=utc())
                    write_json(raw / "estado.json", status)
                    check(telemetry, 30)
                    stages = tuple((f"work_mem_{mem}MiB", SIZES[-1:], 1, *DIAGNOSTIC_TIMES, mem, rep)
                                   for rep in range(1, 6) for mem in rng.sample([4, 16], 2))
                else:
                    status.update(phase="reposo", phase_started_utc=utc())
                    write_json(raw / "estado.json", status)
                    check(telemetry, 600)
                    stages = (("piloto", SIZES[:1], 3, 5, 30, 5, None, 1),
                              ("ampliacion", SIZES, 5, *FINAL_TIMES, None, 1))
                baseline_temp = temperature(telemetry, 25 if args.diagnostic else 60)
                if baseline_temp is None:
                    raise RuntimeError("Telemetría insuficiente para estimar la temperatura basal.")
                status.update(baseline_temperature_c=baseline_temp)
                writer = None
                for tag, cells, repeats, warm, measure, cool, mem, first_rep in stages:
                    for size, clients in cells:
                        for repetition in range(first_rep, first_rep + repeats):
                            order = list(QUERIES)
                            rng.shuffle(order)
                            for query in order:
                                run_id = f"v2-{tag}-{size}-{query}-c{clients}-r{repetition}"
                                if run_id in completed:
                                    continue
                                status.update(phase=tag, query=query, documents=size, clients=clients,
                                              repetition=repetition, phase_started_utc=utc())
                                write_json(raw / "estado.json", status)
                                row = run_cell(ssh, password, db, telemetry, raw, tag, size, query, clients,
                                               repetition, warm, measure, references[str(size)][query], entries[size],
                                               synchronized=True, session_sql=f"SET work_mem='{mem}MB';" if mem else "",
                                               telemetry_gap_s=5 if resume else None)
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
                if args.diagnostic:
                    with Psql(ssh, password, db) as psql:
                        for mem in (4, 16):
                            psql.execute(f"SET work_mem='{mem}MB'; SET statement_timeout='15s';")
                            for query, sql in QUERIES.items():
                                check(telemetry, 1)
                                plan = psql.execute("EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON) "
                                                    + sql.replace("__TABLE__", "orders_50000"))
                                write_json(raw / f"plan-{query}-work-mem-{mem}.json", json.loads("\n".join(plan)))
            status.update(status="completed")
        except Exception as exc:
            status.update(status="interrupted", error=str(exc))
            raise
        finally:
            status["ended_utc"] = utc()
            write_json(raw / "estado.json", status)
            if ssh.get_transport() and ssh.get_transport().is_active():
                capture(ssh, raw / "estado-final.log",
                        "date -u; cat /proc/sys/kernel/random/boot_id; uptime; free -k; vcgencmd get_throttled; pg_lsclusters")
                capture(ssh, raw / "kernel.log",
                        "sudo -k -S -p '' journalctl -k -b --no-pager --grep='out of memory|oom-kill|under.?voltage|throttl|I/O error'",
                        password)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", default="rasp")
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--diagnostic", action="store_true", help="Contraste 4/16 MiB y planes a 50,000 pedidos.")
    parser.add_argument("--resume", type=Path, help="Captura previa cuyas corridas completas se conservan.")
    args = parser.parse_args()
    warnings.filterwarnings("error", category=GetPassWarning)
    experiment(args, getpass("Contraseña SSH (entrada oculta): "))
