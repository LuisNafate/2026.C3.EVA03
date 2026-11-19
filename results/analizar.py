"""Verifica la evidencia y genera resúmenes y datos para el artículo."""

import argparse
from collections import defaultdict
import csv
import json
from math import ceil
from pathlib import Path
import re
from statistics import mean, median, quantiles

METRICS = ("latency_p50_ms", "latency_p95_ms", "latency_p99_ms", "throughput_qps",
           "cpu_percent_mean", "available_memory_min_mib", "rss_sum_max_mib", "temperature_max_c")
SIZES = (1000, 5000, 10000, 25000, 50000)


def load(path):
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def nodes(plan):
    yield plan
    for child in plan.get("Plans", []):
        yield from nodes(child)


def analyze(raw, processed, report, continuation=None):
    processed.mkdir(parents=True, exist_ok=True)
    attempts = load(raw / "corridas.csv")
    if continuation:
        more = load(continuation / "corridas.csv")
        superseded = [r for r in attempts if r["phase"] == "final" and r["document_count"] == "50000"]
    else:
        more, superseded = [], []
    final = [r for r in attempts + more if r["phase"] == "final" and r["status"] == "completed" and r not in superseded]
    pilot = [r for r in attempts if r["phase"] == "piloto" and r["status"] == "completed"]
    plan = json.loads((raw / "plan_final.json").read_text(encoding="utf-8"))
    stored = json.loads((raw / "tamanos_almacenados.json").read_text(encoding="utf-8"))
    trace = load(raw / "telemetria.csv")
    trace_more = load(continuation / "telemetria.csv") if continuation else []
    idle = load(raw / "reposo_motor.csv")
    assert len({r["run_id"] for r in attempts + more}) == len(attempts + more), "run_id duplicado"
    selected_ids = {r["run_id"] for r in pilot + final}
    with (processed / "seleccion_corridas.csv").open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(("run_id", "source_folder", "phase", "status", "included", "reason"))
        for row in attempts + more:
            source = continuation if row in more else raw
            included = row["run_id"] in selected_ids
            writer.writerow((row["run_id"], source.name, row["phase"], row["status"], included,
                             "protocolo_enmendado_50k" if row in superseded else row["error"]))
    groups = defaultdict(list)
    for row in final:
        assert row["result_validation"] == "match"
        source = continuation if row in more else raw
        operations = load(source / (row["run_id"] + ".csv"))
        accepted = [float(o["latency_ms"]) for o in operations if o["inside_window"] == o["valid"] == "1"]
        assert len(accepted) == int(row["operations_completed"]) and accepted
        assert len(operations) - len(accepted) == int(row["operations_crossing_end"])
        for field, percent in zip(METRICS[:3], (.50, .95, .99)):
            assert abs(sorted(accepted)[ceil(len(accepted) * percent) - 1] - float(row[field])) < 1e-8
        assert abs(len(accepted) / float(row["window_s"]) - float(row["throughput_qps"])) < 1e-8
        groups[int(row["document_count"]), int(row["concurrency"]), row["query_id"]].append(row)
    expected_cells = {(n, 1, q) for n in plan["sizes_c1"] for q in ("q1", "q2")}
    expected_cells |= {(10000, c, q) for c in plan["extra_concurrency_at_10000"] for q in ("q1", "q2")}
    assert set(groups) == expected_cells, "matriz final incompleta"
    assert len(pilot) == 6
    assert all(len(rows) == plan["replicates"] for rows in groups.values())

    summaries = {}
    for key in sorted(groups):
        rows = groups[key]
        summary = {"documents": key[0], "clients": key[1], "query": key[2],
                   "replicates": len(rows), "operations_min": min(int(r["operations_completed"]) for r in rows),
                   "operations_total": sum(int(r["operations_completed"]) for r in rows),
                   "p99_low_sample_runs": sum(r["p99_low_sample"] == "True" for r in rows)}
        for field in METRICS:
            values = [float(r[field]) for r in rows]
            q1, _, q3 = quantiles(values, n=4, method="inclusive")
            summary.update({f"{field}_median": median(values), f"{field}_q1": q1, f"{field}_q3": q3})
        summaries[key] = summary
    with (processed / "resumen_celdas.csv").open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(next(iter(summaries.values()))))
        writer.writeheader()
        writer.writerows(summaries.values())

    last = continuation or raw
    raw_plans = json.loads((last / "planes.json").read_text(encoding="utf-8"))
    plans = {key: json.loads("\n".join(lines))[0] for key, lines in raw_plans.items()}
    (processed / "planes_normalizados.json").write_text(json.dumps(plans, indent=2) + "\n", encoding="utf-8")
    boot_pattern = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
    boot_start = re.findall(boot_pattern, (raw / "entorno.log").read_text(encoding="utf-8"))
    boot_end = re.findall(boot_pattern, (last / "estado-final.log").read_text(encoding="utf-8"))
    assert len(boot_start) == len(boot_end) == 1
    boot_ok = boot_start == boot_end
    kernel = (last / "kernel.log").read_text(encoding="utf-8")
    assert "exit_status=0" in kernel
    idle_duration = float(idle[-1]["monotonic_s"]) - float(idle[0]["monotonic_s"])
    facts = {
        "pilot_runs": len(pilot), "final_runs": len(final), "attempts": len(attempts + more),
        "failed": sum(r["status"] != "completed" for r in attempts + more),
        "superseded_completed": sum(r["status"] == "completed" for r in superseded),
        "low_p99": sum(r["p99_low_sample"] == "True" for r in final),
        "total_operations": sum(int(r["operations_completed"]) for r in final),
        "idle_samples": len(idle), "idle_duration": f"{idle_duration:.1f}",
        "idle_ram": f"{mean(float(r['available_kib']) / 1024 for r in idle):.1f}",
        "idle_rss": f"{max(float(r['postgres_rss_sum_kib']) / 1024 for r in idle):.1f}",
        "run_ram_min": f"{min(float(r['available_memory_min_mib']) for r in final):.1f}",
        "run_rss_max": f"{max(float(r['rss_sum_max_mib']) for r in final):.1f}",
        "run_temp_min": f"{min(float(r['temperature_max_c']) for r in final):.1f}",
        "run_temp_max": f"{max(float(r['temperature_max_c']) for r in final):.1f}",
        "run_cpu_max": f"{max(float(r['cpu_percent_max']) for r in final):.1f}",
        "run_swap_max": f"{max(float(r['swap_used_max_mib']) for r in final):.1f}",
        "run_read_max": max(int(r["io_read_bytes"] or 0) for r in final),
        "run_write_max": max(int(r["io_write_bytes"] or 0) for r in final),
        "trace_samples": len(trace + trace_more), "boot_check": "coincidió" if boot_ok else "cambió",
        "kernel_oom": "detectadas" if re.search(r"out of memory|oom-kill", kernel, flags=re.I) else "sin coincidencias",
        "flags": ", ".join(sorted({r["throttled"] for r in trace + trace_more})),
        "window": plan["window_s"], "warm": plan["warm_s"], "cool": plan["cool_s"],
    }
    for q in ("q1", "q2"):
        for n, c in ((1000, 1), (10000, 1), (10000, 2), (10000, 5), (50000, 1)):
            cell = summaries[n, c, q]
            prefix = f"{q}_{n}_{c}"
            facts[f"{prefix}_p95"] = f"{cell['latency_p95_ms_median']:.1f}"
            facts[f"{prefix}_qps"] = f"{cell['throughput_qps_median']:.1f}"
    for name in ("50000-q1", "50000-q2"):
        document = plans[name]
        tree = list(nodes(document["Plan"]))
        facts[f"{name}-nodes"] = ", ".join(dict.fromkeys(node["Node Type"] for node in tree))
        facts[f"{name}-sort"] = ", ".join(dict.fromkeys(node["Sort Method"] for node in tree if "Sort Method" in node)) or "sin método reportado"
        facts[f"{name}-temp"] = document["Plan"].get("Temp Written Blocks", 0)
        facts[f"{name}-sharedread"] = document["Plan"].get("Shared Read Blocks", 0)
        facts[f"{name}-sharedhit"] = document["Plan"].get("Shared Hit Blocks", 0)
        facts[f"{name}-ms"] = f"{document['Execution Time']:.1f}"
    if "50000-q1-jit-off" in plans:
        diagnostic = plans["50000-q1-jit-off"]
        facts["50000-q1-jit-off-ms"] = f"{diagnostic['Execution Time']:.1f}"
        facts["50000-q1-jit-functions"] = plans["50000-q1"].get("JIT", {}).get("Functions", 0)
    (processed / "hechos.json").write_text(json.dumps(facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    colors = {"q1": ("azul", "*"), "q2": ("verde", "square*")}
    lines = ["% Generado por results/analizar.py a partir del ensayo indicado.",
             r"\newcommand{\EdgeDato}[1]{\csname edge-#1\endcsname}"]
    for key, value in facts.items():
        lines.append(rf"\expandafter\def\csname edge-{key}\endcsname{{{value}}}")
    rows = []
    for n, c, q in sorted(summaries):
        s = summaries[n, c, q]
        rows.append(
            f"{n:,} & {c} & {q.upper()} & {s['operations_min']} & "
            f"{s['latency_p95_ms_median']:.1f} [{s['latency_p95_ms_q1']:.1f}, {s['latency_p95_ms_q3']:.1f}] & "
            f"{s['latency_p99_ms_median']:.1f} & {s['throughput_qps_median']:.1f}" + r" \\"
        )
    lines.append("\\newcommand{\\EdgeRows}{%\n" + "\n".join(rows) + "\n}")
    size_rows = [
        f"{v['documents']:,} & {v['items']:,} & {v['q2_qualified']:,} & "
        f"{v['bytes_jsonl'] / 1048576:.2f} & {v['stored_bytes_with_pk'] / 1048576:.2f}" + r" \\"
        for v in stored
    ]
    lines.append("\\newcommand{\\EdgeDatasetRows}{%\n" + "\n".join(size_rows) + "\n}")
    for chart, cells, x_index, key in (
        ("Latency", [(n, 1) for n in SIZES], 0, "latency_p95_ms_median"),
        ("Throughput", [(10000, c) for c in (1, 2, 5)], 1, "throughput_qps_median"),
    ):
        lines.append(rf"\newcommand{{\Edge{chart}}}{{%")
        for q in ("q1", "q2"):
            color, marker = colors[q]
            values = " ".join(f"({cell[x_index]},{summaries[*cell,q][key]:.3f})" for cell in cells)
            lines += [rf"\addplot[{color},thick,mark={marker}] coordinates {{{values}}};", rf"\addlegendentry{{{q.upper()}}}"]
        lines.append("}")
    start = float(trace[0]["monotonic_s"])
    for section, field, divisor in (
        ("Temperature", "soc_c", 1), ("Ram", "available_kib", 1024), ("Frequency", "cpu0_khz", 1000)
    ):
        lines.append(rf"\newcommand{{\Edge{section}}}{{%")
        for block in (trace, trace_more):
            if block:
                values = " ".join(
                    f"({(float(row['monotonic_s']) - start) / 60:.3f},{float(row[field]) / divisor:.3f})"
                    for row in block[::5]
                )
                lines.append(rf"\addplot[verde,thick] coordinates {{{values}}};")
        lines.append("}")
    (report / "resultados.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(facts, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("processed", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--continuation", type=Path)
    args = parser.parse_args()
    analyze(args.raw, args.processed, args.report, args.continuation)
