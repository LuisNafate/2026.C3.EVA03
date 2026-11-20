"""Consolida la ampliación EVA02 y coteja cada corrida con sus operaciones."""

import argparse
from collections import defaultdict
import csv
from datetime import datetime
import json
from math import ceil, isclose
from pathlib import Path
from statistics import median, quantiles


MOMENTS = ("latency_p50_ms", "latency_p95_ms", "latency_p99_ms")
CELL = ("engine", "phase", "document_count", "query_id", "concurrency", "window_s")


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def verify(directory, row):
    ops = read_csv(directory / (row["run_id"] + ".csv"))
    latencies = []
    for op in ops:
        if op["valid"] == "1" and op["inside_window"] == "1":
            elapsed = 1000 * (float(op["end_monotonic_s"]) - float(op["start_monotonic_s"]))
            if not isclose(elapsed, float(op["latency_ms"]), rel_tol=1e-8, abs_tol=1e-5):
                raise ValueError(f"Latencia incoherente en {row['run_id']}.")
            latencies.append(elapsed)
    latencies.sort()
    candidate = (len(latencies), sum(op["inside_window"] == "0" for op in ops))
    if candidate != (int(row["operations_completed"]), int(row["operations_crossing_end"])):
        raise ValueError(f"Operaciones incoherentes en {row['run_id']}.")
    if not isclose(len(latencies) / float(row["window_s"]), float(row["throughput_qps"])):
        raise ValueError(f"QPS incoherente en {row['run_id']}.")
    for percentile, field in zip((0.50, 0.95, 0.99), MOMENTS):
        if latencies and not isclose(latencies[ceil(len(latencies) * percentile) - 1], float(row[field]), abs_tol=1e-5):
            raise ValueError(f"Percentil incoherente en {row['run_id']}.")
    if row["status"] == "completed" and (row["result_validation"] != "match" or any(op["valid"] != "1" for op in ops)):
        raise ValueError(f"Validación incoherente en {row['run_id']}.")


def meta(directory):
    status = json.loads((directory / "estado.json").read_text(encoding="utf-8"))
    if not status.get("ended_utc"):
        raise ValueError(f"El bloque está en curso: {directory.name}")
    elapsed = datetime.fromisoformat(status["ended_utc"]) - datetime.fromisoformat(status["started_utc"])
    return {"session": directory.name, **status, "elapsed_s": round(elapsed.total_seconds(), 1)}


def summarize(valid, field):
    numbers = [float(row[field]) for row in valid if row[field]]
    return median(numbers) if numbers else None


def analyze(sources, output):
    output.mkdir(parents=True, exist_ok=True)
    groups = defaultdict(list)
    sessions = []
    for directory in sources:
        session = meta(directory)
        table = directory / "corridas.csv"
        rows = read_csv(table) if table.exists() else []
        for row in rows:
            verify(directory, row)
            groups[(directory.name, *(row[field] for field in CELL))].append(row)
        complete = [row for row in rows if row["status"] == "completed"]
        if (len(rows), len(complete)) != (session["attempted"], session["completed"]):
            raise ValueError(f"El estado no coincide con las corridas exportadas de {directory.name}.")
        cooldown_path = directory / "enfriamiento.csv"
        recoveries = read_csv(cooldown_path) if cooldown_path.exists() else []
        if not {row["run_id"] for row in recoveries} <= {row["run_id"] for row in complete}:
            raise ValueError(f"El enfriamiento contiene corridas no conciliadas de {directory.name}.")
        telem = directory / "telemetria.csv"
        samples = read_csv(telem) if telem.exists() else []
        session.update(
            validated_operations=sum(int(row["operations_completed"]) for row in complete),
            pilot_valid=sum(row["phase"].startswith("piloto") for row in complete),
            final_valid=sum(row["phase"] == "ampliacion" for row in complete),
            telemetry_samples=len(samples),
            min_available_mib=round(min(int(row["available_kib"]) for row in samples) / 1024, 1) if samples else None,
            max_soc_c=max(float(row["soc_c"]) for row in samples) if samples else None,
            cooldowns_logged=len(recoveries),
            cooldowns_recovered=sum(row["within_baseline_plus_3c"] == "1" for row in recoveries),
            median_cooldown_s=summarize(recoveries, "cooldown_s"),
            longest_cooldown_s=max((float(row["cooldown_s"]) for row in recoveries), default=None),
        )
        sessions.append(session)

    with (output / "resumen_celdas.csv").open("w", encoding="utf-8", newline="") as stream:
        fields = ("session", *CELL, "attempted", "valid", "incomplete", "observations_p99_low_sample",
                  "p50_median_ms", "p95_median_ms", "p95_q1_ms", "p95_q3_ms", "p99_median_ms", "qps_median")
        writer = csv.writer(stream)
        writer.writerow(fields)
        for key, rows in groups.items():
            valid = [row for row in rows if row["status"] == "completed"]
            p95 = [float(row["latency_p95_ms"]) for row in valid]
            quartiles = quantiles(p95, n=4, method="inclusive") if len(p95) > 1 else (None, None, None)
            writer.writerow((*key, len(rows), len(valid), len(rows) - len(valid),
                             sum(row["p99_low_sample"] == "True" for row in valid), summarize(valid, MOMENTS[0]),
                             summarize(valid, MOMENTS[1]), quartiles[0], quartiles[2], summarize(valid, MOMENTS[2]),
                             summarize(valid, "throughput_qps")))
    (output / "sesiones.json").write_text(json.dumps(sessions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sessions", type=Path, nargs="+")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    analyze(args.sessions, args.out)
