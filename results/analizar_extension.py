"""Consolida el benchmark ampliado y coteja cada corrida con sus operaciones."""

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


def write_latex(combined, final_recoveries, output):
    lines = ["% Generado por results/analizar_extension.py."]
    cells = {}
    for (engine, phase, documents, query, clients, window), attempts in combined.items():
        if phase == "ampliacion" and window == "60":
            cells[engine, int(documents), int(clients), query] = attempts

    def macro(name, rows):
        lines.extend([fr"\newcommand{{\{name}}}{{%", *rows, "}"])

    def pair(fields):
        return " & ".join(str(value) for value in fields) + r" \\"

    def value(rows, field, precision=1, scale=1):
        number = summarize(rows, field)
        return "--" if number is None else f"{number / scale:.{precision}f}"

    budget_rows, tradeoff_rows, write_cost_rows = [], [], []
    for engine, prefix in (("PostgreSQL", "Pg"), ("MongoDB comunitario", "Mongo")):
        performance, resources = [], []
        for (_, documents, clients, query), rows in sorted((k, v) for k, v in cells.items() if k[0] == engine):
            valid = [row for row in rows if row["status"] == "completed"]
            if len(valid) != 5:
                raise ValueError(f"El artículo requiere cinco corridas válidas en {engine}, {documents}, {clients}, {query}.")
            key = (f"{documents:,}", query.upper(), clients)
            p95 = [float(row["latency_p95_ms"]) for row in valid]
            low, _, high = quantiles(p95, n=4, method="inclusive")
            performance.append(pair((*key, f"{len(valid)}/{len(rows)}", value(valid, "throughput_qps", 2),
                                     value(valid, MOMENTS[0]), f"{median(p95):.1f} [{low:.1f}, {high:.1f}]",
                                     value(valid, MOMENTS[2]), sum(row["p99_low_sample"] == "True" for row in valid))))
            resources.append(pair((*key, value(valid, "cpu_percent_mean"), value(valid, "rss_sum_max_mib"),
                                   value(valid, "available_memory_min_mib"), value(valid, "temperature_max_c"),
                                   value(valid, "io_read_bytes", scale=1048576), value(valid, "io_write_bytes", scale=1048576))))
        if len(performance) != 14:
            raise ValueError(f"Se esperaban 14 condiciones para {engine}.")
        macro(prefix + "Performance", performance)
        macro(prefix + "Resources", resources)
        for query, letter in (("q1", "One"), ("q2", "Two")):
            for measure, suffix, levels in (("latency_p95_ms", "Volume", (1000, 5000, 10000, 25000, 50000)),
                                             ("throughput_qps", "Clients", (1, 2, 5))):
                points = []
                for level in levels:
                    documents, clients = (level, 1) if suffix == "Volume" else (10000, level)
                    rows = cells[engine, documents, clients, query]
                    valid = [row for row in rows if row["status"] == "completed"]
                    points.append(f"({level},{value(valid, measure, 4)})")
                macro(prefix + letter + suffix, [" ".join(points)])

        at_50k = {
            query: [row for row in cells[engine, 50000, 1, query] if row["status"] == "completed"]
            for query in ("q1", "q2")
        }
        macro(prefix + "Writes", [value(at_50k["q1"], "io_write_bytes", scale=1048576)])
        write_cost = [float(row["io_write_bytes"]) / (1048576 * int(row["operations_completed"]))
                      for row in at_50k["q1"]]
        write_cost_rows.append(pair((engine, len(write_cost), f"{median(write_cost):.3f}",
                                      f"{min(write_cost):.3f}--{max(write_cost):.3f}")))
        q2_p95 = [float(row["latency_p95_ms"]) for row in at_50k["q2"]]
        budget_rows.append(pair((engine, f"{median(q2_p95):.1f}", f"{min(q2_p95):.1f}--{max(q2_p95):.1f}",
                                 f"{sum(p95 <= 500 for p95 in q2_p95)}/{len(q2_p95)}")))

        tradeoff_points = []
        for clients in (1, 2, 5):
            valid = [row for row in cells[engine, 10000, clients, "q2"] if row["status"] == "completed"]
            qps = summarize(valid, "throughput_qps")
            p95s = [float(row["latency_p95_ms"]) for row in valid]
            p95 = median(p95s)
            tradeoff_points.append(f"({qps:.4f},{p95:.3f}) [{clients}]")
            tradeoff_rows.append(pair((engine, clients, f"{qps:.2f}", f"{p95:.1f}",
                                       f"{sum(sample <= 200 for sample in p95s)}/{len(valid)}")))
        macro(prefix + "Tradeoff", [" ".join(tradeoff_points)])

        recoveries = final_recoveries[engine]
        recovered = [float(row["cooldown_s"]) for row in recoveries if row["within_baseline_plus_3c"] == "1"]
        at_limit = sum(float(row["cooldown_s"]) >= 300 and row["within_baseline_plus_3c"] == "0" for row in recoveries)
        on_time = sum(120 <= duration < 125 for duration in recovered)
        extended = sum(duration >= 125 for duration in recovered)
        macro(prefix + "Cooling", [f"(base,{on_time}) (extendida,{extended}) (limite,{at_limit})"])
        macro(prefix + "CoolingEvaluable", [str(on_time + extended + at_limit)])
        macro(prefix + "CoolingProlonged", [str(extended + at_limit)])
        macro(prefix + "CoolingUnrecovered", [str(at_limit)])
    macro("BudgetRows", budget_rows)
    macro("TradeoffRows", tradeoff_rows)
    macro("WriteCostRows", write_cost_rows)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def analyze(sources, output, latex=None):
    output.mkdir(parents=True, exist_ok=True)
    groups = defaultdict(list)
    combined = defaultdict(list)
    completed_ids = set()
    final_recoveries = defaultdict(list)
    sessions = []
    for directory in sources:
        session = meta(directory)
        table = directory / "corridas.csv"
        rows = read_csv(table) if table.exists() else []
        for row in rows:
            verify(directory, row)
            key = tuple(row[field] for field in CELL)
            groups[(directory.name, *key)].append(row)
            combined[key].append(row)
            if row["status"] == "completed":
                record = (row["engine"], row["run_id"])
                if record in completed_ids:
                    raise ValueError(f"Repetición válida duplicada: {record}.")
                completed_ids.add(record)
        complete = [row for row in rows if row["status"] == "completed"]
        if (len(rows), len(complete)) != (session["attempted"], session["completed"]):
            raise ValueError(f"El estado no coincide con las corridas exportadas de {directory.name}.")
        cooldown_path = directory / "enfriamiento.csv"
        recoveries = read_csv(cooldown_path) if cooldown_path.exists() else []
        if not {row["run_id"] for row in recoveries} <= {row["run_id"] for row in complete}:
            raise ValueError(f"El enfriamiento contiene corridas no conciliadas de {directory.name}.")
        final_engines = {row["run_id"]: row["engine"] for row in complete if row["phase"] == "ampliacion"}
        for row in recoveries:
            if row["run_id"] in final_engines:
                final_recoveries[final_engines[row["run_id"]]].append(row)
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

    for name, dataset, keys in (("resumen_celdas.csv", groups, ("session", *CELL)),
                                ("matriz_consolidada.csv", combined, CELL)):
        with (output / name).open("w", encoding="utf-8", newline="") as stream:
            fields = (*keys, "attempted", "valid", "incomplete", "observations_p99_low_sample",
                      "p50_median_ms", "p95_median_ms", "p95_q1_ms", "p95_q3_ms", "p99_median_ms", "qps_median")
            writer = csv.writer(stream)
            writer.writerow(fields)
            for key, rows in sorted(dataset.items()):
                valid = [row for row in rows if row["status"] == "completed"]
                p95 = [float(row["latency_p95_ms"]) for row in valid]
                quartiles = quantiles(p95, n=4, method="inclusive") if len(p95) > 1 else (None, None, None)
                writer.writerow((*key, len(rows), len(valid), len(rows) - len(valid),
                                 sum(row["p99_low_sample"] == "True" for row in valid), summarize(valid, MOMENTS[0]),
                                 summarize(valid, MOMENTS[1]), quartiles[0], quartiles[2], summarize(valid, MOMENTS[2]),
                                 summarize(valid, "throughput_qps")))
    (output / "sesiones.json").write_text(json.dumps(sessions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if latex is not None:
        write_latex(combined, final_recoveries, latex)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sessions", type=Path, nargs="+")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--latex", type=Path, help="Genera tablas y coordenadas para el artículo.")
    args = parser.parse_args()
    analyze(args.sessions, args.out, args.latex)
