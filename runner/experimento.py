"""Ejecuta y guarda el caso de estudio PostgreSQL JSONB desde la laptop."""

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import csv
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from getpass import GetPassWarning, getpass
import hashlib
import json
from math import ceil
from pathlib import Path
import random
import runpy
from statistics import median
import subprocess
from threading import Barrier, Event, Thread
from time import monotonic, perf_counter, sleep
import warnings

import paramiko

ROOT = Path(__file__).resolve().parents[1]
dataset = runpy.run_path(str(ROOT / "dataset/generar.py"))
base = runpy.run_path(str(ROOT / "telemetry/preparar_pi.py"))
QUERIES = {name: (ROOT / f"workloads/postgresql/{name}.sql").read_text() for name in ("q1", "q2")}
SAMPLE = base["SAMPLER"].replace(
    "    printf 'EDGE",
    "    rss=$(ps -C postgres -o rss= | awk '{total+=$1} END {print total+0}')\n    printf 'EDGE",
).replace("%s %s\\n'", "%s %s %s\\n'").replace('"${flags#throttled=}" ||', '"${flags#throttled=}" "$rss" ||').replace(
    "    sleep 5", "    sleep 1"
)
END = "__EDGE_QUERY_END__"


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def metric(values, percentile):
    return sorted(values)[ceil(len(values) * percentile) - 1] if values else None


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def expected(path):
    groups, passing = defaultdict(list), []
    for line in path.read_text(encoding="ascii").splitlines():
        order = json.loads(line, parse_float=Decimal)
        for item in order["items"]:
            if item["price"] > 50:
                groups[order["customer"]["country"], item["category"]].append(item["qty"] * item["price"])
        if order["status"] == "completed" and dataset["FROM_DATE"] <= order["timestamp"] < dataset["TO_DATE"]:
            passing.append((order["order_id"], order["payment"]["final_total"]))
    q1 = []
    for (country, category), values in sorted(groups.items()):
        total = sum(values)
        avg = (total / len(values)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        q1.append(f"{country}|{category}|{total:.2f}|{avg:.2f}|{len(values)}")
    q2 = [f"{i}|{total:.2f}" for i, total in sorted(passing, key=lambda row: (-row[1], row[0]))[:1000]]
    return {"q1": q1, "q2": q2}, len(passing)


class Psql:
    def __init__(self, ssh, password, db):
        self.stream = base["channel"](
            ssh, f"sudo -k -S -p '' -u postgres psql -X -qAt -F '|' -v ON_ERROR_STOP=1 -d {db}", 25
        )
        self.stream.sendall((password + "\n").encode())
        self.reader = self.stream.makefile("r")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.stream.close()

    def read_rows(self):
        rows = []
        for line in self.reader:
            line = line.rstrip("\r\n")
            if line == END:
                return rows
            rows.append(line)
        raise RuntimeError("psql interrumpido: " + " / ".join(rows[-8:]))

    def execute(self, sql):
        self.stream.sendall((sql.rstrip() + "\n\\echo " + END + "\n").encode())
        return self.read_rows()

    def load(self, table, path):
        self.execute(f"CREATE TABLE {table} (order_id integer PRIMARY KEY, payload jsonb NOT NULL);")
        self.stream.sendall(f"COPY {table} FROM STDIN;\n".encode())
        with path.open("rb") as data:
            chunk = bytearray()
            for index, line in enumerate(data, 1):
                chunk.extend(f"{index}\t".encode("ascii"))
                chunk.extend(line)
                if len(chunk) >= 65536:
                    self.stream.sendall(bytes(chunk))
                    chunk.clear()
            if chunk:
                self.stream.sendall(bytes(chunk))
        self.stream.sendall(("\\.\n\\echo " + END + "\n").encode())
        self.read_rows()
        self.execute(f"ANALYZE {table};")


class Telemetry:
    def __init__(self, ssh, path, process="postgres", timeout=8):
        self.path = path
        self.records = []
        self.stop = Event()
        self.incident = None
        self.process = process
        self.stream = base["channel"](ssh, SAMPLE.replace("-C postgres", f"-C {process}"), timeout)
        self.thread = Thread(target=self.collect, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.stream.close()
        self.thread.join(timeout=10)

    def collect(self):
        prev = None
        try:
            with self.path.open("x", encoding="utf-8", newline="") as output:
                writer = csv.writer(output)
                writer.writerow(("utc", "monotonic_s", "cpu_pct", "cpu_total", "cpu_idle", "ram_kib", "available_kib",
                                 "swap_kib", "swap_free_kib", "soc_c", "cpu0_khz", "read_sectors", "write_sectors",
                                 "throttled", f"{self.process}_rss_sum_kib"))
                for line in self.stream.makefile("r"):
                    if self.stop.is_set():
                        return
                    columns = line.split()
                    if len(columns) != 13 or columns[0] != "EDGE":
                        raise RuntimeError("Telemetría inválida: " + line.strip())
                    total, idle, ram, mem, swap, swap_free = map(int, columns[1:7])
                    temp = int(columns[7]) / 1000
                    freq, reads, writes = map(int, columns[8:11])
                    mask, rss = columns[11], int(columns[12])
                    now = monotonic()
                    cpu = None
                    if prev and total > prev[0]:
                        delta, idle_delta = total - prev[0], idle - prev[1]
                        if 0 <= idle_delta <= delta:
                            cpu = 100 * (1 - idle_delta / delta)
                    prev = total, idle
                    writer.writerow((utc(), now, cpu, total, idle, ram, mem, swap, swap_free, temp, freq, reads, writes, mask, rss))
                    output.flush()
                    self.records.append((now, cpu, mem, swap - swap_free, temp, freq, reads, writes, mask, rss))
                    if temp >= 70 or mem < 65536 or int(mask, 16) & 0xF:
                        self.incident = f"Criterio de parada: {temp} C, RAM disponible {mem} KiB, máscara {mask}."
                if not self.stop.is_set():
                    self.incident = "Se interrumpió la telemetría."
        except Exception as exc:
            if not self.stop.is_set():
                self.incident = f"Telemetría: {type(exc).__name__}: {exc}"


def run_cell(client, password, db, telem, raw, tag, size, query, concurrency, repetition, warm, window, reference, entry, synchronized=False, *, session_sql="", connect=None, statement=None, engine=("PostgreSQL", "17.12"), telemetry_gap_s=None):
    run_id = f"{'v2-' if synchronized else ''}{tag}-{size}-{query}-c{concurrency}-r{repetition}"
    operations = []
    row = {
        "run_id": run_id, "phase": tag, "timestamp_start": utc(), "device_id": "edge-db",
        "thermal_condition": "sin_disipador", "engine": engine[0], "engine_version": engine[1],
        "dataset_id": entry["dataset_id"], "dataset_hash": entry["sha256"], "document_count": size,
        "query_id": query, "concurrency": concurrency, "run_number": repetition,
    }
    sql = QUERIES[query].replace("__TABLE__", f"orders_{size}") if statement is None else statement
    starts, stops = None, None
    error = None
    with ExitStack() as opened:
        try:
            if telem.incident:
                raise RuntimeError(telem.incident)
            if connect is None:
                workers = [opened.enter_context(Psql(client, password, db)) for _ in range(concurrency)]
                for worker in workers:
                    worker.execute("SET statement_timeout='8s'; SET default_transaction_read_only=on;" + session_sql)
            else:
                workers = [opened.enter_context(connect()) for _ in range(concurrency)]
            starts = monotonic() + warm
            stops = starts + window

            def release():
                nonlocal starts, stops
                starts = monotonic()
                stops = starts + window

            barrier = Barrier(concurrency, action=release, timeout=26)
            warm_deadline = starts

            def worker_loop(number, psql):
                if synchronized:
                    while monotonic() < warm_deadline and not telem.incident:
                        if psql.execute(sql) != reference:
                            barrier.abort()
                            raise RuntimeError("La salida del calentamiento difiere de la referencia.")
                    barrier.wait()
                while monotonic() < stops and not telem.incident:
                    start = perf_counter()
                    measured = start >= starts
                    rows = psql.execute(sql)
                    stop = perf_counter()
                    valid = rows == reference
                    if measured:
                        operations.append((number, start, stop, (stop - start) * 1000, len(rows), int(valid), int(stop <= stops)))
                    if not valid:
                        raise RuntimeError("La salida difiere de la referencia independiente.")

            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = [pool.submit(worker_loop, num, psql) for num, psql in enumerate(workers, 1)]
                for future in futures:
                    future.result()
            if telem.incident:
                raise RuntimeError(telem.incident)
        except Exception as exc:
            error = str(exc)
    with (raw / f"{run_id}.csv").open("x", encoding="utf-8", newline="") as opfile:
        out = csv.writer(opfile)
        out.writerow(("client", "start_monotonic_s", "end_monotonic_s", "latency_ms", "rows", "valid", "inside_window"))
        out.writerows(sorted(operations, key=lambda item: item[1]))
    inside = [op[3] for op in operations if op[5] and op[6]]
    metrics = [s for s in telem.records if starts is not None and starts <= s[0] <= stops]
    cpu = [s[1] for s in metrics if s[1] is not None]
    if not inside or not metrics:
        error = error or "Ventana sin operaciones completas o sin telemetría."
    if telemetry_gap_s and starts is not None:
        timestamps = [starts, *(sample[0] for sample in metrics), stops]
        gap = max(right - left for left, right in zip(timestamps, timestamps[1:]))
        if gap > telemetry_gap_s:
            error = error or f"Brecha de telemetría de {gap:.1f} s dentro de la ventana."
    row.update(
        window_start_monotonic_s=starts, window_end_monotonic_s=stops,
        operations_completed=len(inside), operations_crossing_end=sum(not op[6] for op in operations),
        window_s=window, throughput_qps=len(inside) / window,
        latency_p50_ms=metric(inside, .50), latency_p95_ms=metric(inside, .95), latency_p99_ms=metric(inside, .99),
        p99_low_sample=len(inside) < 100, cpu_percent_mean=sum(cpu) / len(cpu) if cpu else None,
        cpu_percent_max=max(cpu, default=None), rss_sum_max_mib=max((s[9] / 1024 for s in metrics), default=None),
        available_memory_min_mib=min((s[2] / 1024 for s in metrics), default=None),
        swap_used_max_mib=max((s[3] / 1024 for s in metrics), default=None),
        io_read_bytes=(metrics[-1][6] - metrics[0][6]) * 512 if len(metrics) > 1 else None,
        io_write_bytes=(metrics[-1][7] - metrics[0][7]) * 512 if len(metrics) > 1 else None,
        temperature_max_c=max((s[4] for s in metrics), default=None),
        cpu_frequency_mean_mhz=sum(s[5] for s in metrics) / (1000 * len(metrics)) if metrics else None,
        throttling_flags=",".join(sorted({s[8] for s in metrics})), telemetry_samples=len(metrics),
        power_w_mean=None, energy_wh=None, energy_j_per_1000_docs=None, oom_killed=None, rebooted=None,
        error_count=int(error is not None), result_validation="match" if not error else "incomplete",
        status=("interrupted" if telem.incident else "failed") if error else "completed", error=error,
    )
    return row


def experiment(host, user, password, raw, data_dir):
    raw.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((data_dir / "manifiesto.json").read_text())
    entries = {e["documents"]: e for e in manifest}
    db = "edge_lab_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    with paramiko.SSHClient() as ssh:
        ssh.load_system_host_keys(str(Path.home() / ".ssh/known_hosts"))
        ssh.connect(host, username=user, password=password, timeout=10, allow_agent=False, look_for_keys=False)
        ssh.get_transport().set_keepalive(15)
        base["emit"](raw, f"Preparación de base aislada {db}.")
        capture = base["log_command"]
        capture(ssh, raw / "entorno.log",
                "date -u; uname -srmo; cat /proc/sys/kernel/random/boot_id; uptime; "
                "free -k; cat /proc/swaps; vcgencmd get_throttled; pg_lsclusters; psql --version")
        ping = subprocess.run(["ping", "-n", "5", "-w", "1000", host], capture_output=True, check=False)
        (raw / "rtt.log").write_bytes(ping.stdout + ping.stderr)
        local_before = utc()
        capture(ssh, raw / "reloj-remoto.log", "date -u +%FT%T.%NZ; timedatectl show -p NTPSynchronized")
        write_json(raw / "reloj-laptop.json", {"antes_consulta_utc": local_before, "despues_consulta_utc": utc()})
        with (raw / "referencias.json").open("x", encoding="utf-8") as refs:
            results = {}
            for n, entry in entries.items():
                path = data_dir / f"orders-{n}.jsonl"
                if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
                    raise RuntimeError(f"Hash incorrecto en {path.name}.")
                oracle, qualified = expected(path)
                if qualified != entry["q2_qualified"]:
                    raise RuntimeError(f"Selectividad inesperada en {path.name}.")
                results[n] = oracle
            json.dump(results, refs, indent=2)
        with Telemetry(ssh, raw / "reposo_motor.csv") as idle:
            still = monotonic()
            while monotonic() - still < 65 and not idle.incident:
                sleep(1)
            if idle.incident or len(idle.records) < 50:
                raise RuntimeError(idle.incident or "Línea base del motor incompleta.")
        base["emit"](raw, f"Reposo del motor: {len(idle.records)} muestras.")

        with Psql(ssh, password, "postgres") as postgres:
            version = postgres.execute("SHOW server_version;")[0]
            if not version.startswith("17.12"):
                raise RuntimeError("Cambió la versión del motor: " + version)
            postgres.execute(f"CREATE DATABASE {db} TEMPLATE template0 LC_COLLATE 'C' LC_CTYPE 'C';")
        stored = []
        with Psql(ssh, password, db) as loading:
            for n in entries:
                table = f"orders_{n}"
                loading.load(table, data_dir / f"orders-{n}.jsonl")
                count, size_bytes = loading.execute(f"SELECT count(*), pg_total_relation_size('{table}') FROM {table};")[0].split("|")
                if int(count) != n:
                    raise RuntimeError(f"Carga incompleta de {table}.")
                stored.append({**entries[n], "stored_bytes_with_pk": int(size_bytes)})
                for name, sql in QUERIES.items():
                    if loading.execute(sql.replace("__TABLE__", table)) != results[n][name]:
                        raise RuntimeError(f"Resultado incorrecto en {n}/{name}.")
                base["emit"](raw, f"{table}: inserción y Q1/Q2 verificadas.")
            config = loading.execute(
                "SELECT name, setting, unit, source FROM pg_settings WHERE name IN "
                "('server_version','shared_buffers','work_mem','jit','max_connections','max_parallel_workers_per_gather',"
                "'effective_cache_size','track_io_timing','synchronous_commit','fsync') ORDER BY name;"
            )
            (raw / "pg_settings.log").write_text("\n".join(config) + "\n", encoding="utf-8")
        write_json(raw / "tamanos_almacenados.json", stored)

        with Psql(ssh, password, "postgres") as admin:
            other = admin.execute("SELECT count(*) FROM pg_stat_activity "
                                  "WHERE backend_type='client backend' AND pid<>pg_backend_pid();")
        if other == ["0"]:
            code = capture(ssh, raw / "reinicio.log", "sudo -k -S -p '' pg_ctlcluster 17 main restart", password)
            if code:
                raise RuntimeError("No se verificó el reinicio controlado.")
            with Psql(ssh, password, db) as after:
                count = after.execute("SELECT count(*) FROM orders_1000;")
                result = after.execute(QUERIES["q1"].replace("__TABLE__", "orders_1000"))
                if count != ["1000"] or result != results[1000]["q1"]:
                    raise RuntimeError("La prueba de persistencia falló.")
            base["emit"](raw, "Persistencia de 1,000 documentos y Q1 confirmadas después de reiniciar el clúster.")
        else:
            base["emit"](raw, "Reinicio omitido: hay otra conexión de base de datos.")

        plans = {}
        with (raw / "corridas.csv").open("x", encoding="utf-8", newline="") as stream, Telemetry(ssh, raw / "telemetria.csv") as telem:
            writer = None

            def save(tag, n, q, c, rep, warm, window):
                nonlocal writer
                record = run_cell(ssh, password, db, telem, raw, tag, n, q, c, rep, warm, window, results[n][q], entries[n])
                if writer is None:
                    writer = csv.DictWriter(stream, fieldnames=record)
                    writer.writeheader()
                writer.writerow(record)
                stream.flush()
                if record["status"] != "completed":
                    raise RuntimeError(f"{record['run_id']}: {record['error']}")
                sleep(1)
                return record

            pilot = [save("piloto", 1000, q, 1, r, 1, 3) for r in range(1, 4) for q in QUERIES]
            slow = max(row["latency_p95_ms"] for row in pilot)
            window = 4 if slow <= 250 else min(10, ceil(slow * 16 / 1000))
            plan = {
                "db": db, "warm_s": 1, "window_s": window, "cool_s": 1, "piloto_p95_max_ms": slow,
                "sizes_c1": list(entries), "extra_concurrency_at_10000": [2, 5],
                "replicates": 5, "order_seed": 42, "thermal_stop_c": 70, "mem_available_stop_kib": 65536,
                "cache": "caliente, sin vaciar caches; reinicio antes del piloto",
                "energy": "no medida", "ambient_temperature": "no medida",
            }
            write_json(raw / "plan_final.json", plan)
            base["emit"](raw, f"Piloto completo. Matriz registrada antes de medir: ventana {window} s.")
            rng = random.Random(42)
            for n, c in [(n, 1) for n in entries] + [(10000, 2), (10000, 5)]:
                for r in range(1, 6):
                    order = list(QUERIES)
                    rng.shuffle(order)
                    for q in order:
                        save("final", n, q, c, r, 1, window)
                base["emit"](raw, f"Final completado: {n} documentos, {c} cliente(s).")
            for n in (1000, 10000, 50000):
                with Psql(ssh, password, db) as psql:
                    for name, sql in QUERIES.items():
                        plans[f"{n}-{name}"] = psql.execute(
                            "EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON) "
                            + sql.replace("__TABLE__", f"orders_{n}")
                        )
            write_json(raw / "planes.json", plans)
        capture(ssh, raw / "estado-final.log",
                "date -u; cat /proc/sys/kernel/random/boot_id; uptime; free -k; vcgencmd get_throttled; pg_lsclusters")
        capture(ssh, raw / "kernel.log",
                """sudo -k -S -p '' sh -c 'journalctl -k --since "-1 hour" --no-pager |
                grep -Ei "out of memory|oom-kill|under.?voltage|throttl|I/O error" || true'""", password)
        base["emit"](raw, "Matriz terminada y respaldada en la laptop.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.1.80")
    parser.add_argument("--user", default="rasp")
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    args = parser.parse_args()
    warnings.filterwarnings("error", category=GetPassWarning)
    try:
        experiment(args.host, args.user, getpass("Contraseña SSH (entrada oculta): "), args.raw, args.dataset)
    except Exception as error:
        if args.raw.is_dir():
            base["emit"](args.raw, f"Experimento interrumpido: {type(error).__name__}: {error}")
        raise
