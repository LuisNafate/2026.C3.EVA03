"""Mide el riel interno del VC4 en reposo y bajo Q1, sin inferir los 5 V."""

import argparse
from contextlib import ExitStack
import csv
from getpass import GetPassWarning, getpass
import json
from pathlib import Path
import re
from statistics import median
from threading import Event, Thread
from time import monotonic, sleep
import warnings

import paramiko

from experimento import Psql, QUERIES, base, utc, write_json

SAMPLER = r"""
export LC_ALL=C
while :; do
    core=$(vcgencmd measure_volts core)
    freq=$(vcgencmd measure_clock arm)
    flags=$(vcgencmd get_throttled)
    read -r temp < /sys/class/thermal/thermal_zone0/temp
    printf '%s\t%s\t%s\t%s\n' "$core" "$freq" "$flags" "$temp" || exit 0
    sleep 1
done
"""


def diagnose(args, password):
    args.output.mkdir(parents=True, exist_ok=False)
    plan = json.loads((args.benchmark / "plan_final.json").read_text(encoding="utf-8"))
    db = plan["db"]
    if not re.fullmatch(r"edge_lab_\d{8}_\d{6}", db):
        raise ValueError("El nombre de la base no corresponde al ensayo.")
    reference = json.loads((args.benchmark / "referencias.json").read_text(encoding="utf-8"))["10000"]["q1"]
    samples, errors, queries = [], [], []
    stopped = Event()
    phase = "inicio"
    start = monotonic()

    with paramiko.SSHClient() as ssh:
        ssh.load_system_host_keys(str(Path.home() / ".ssh/known_hosts"))
        ssh.connect(args.host, username=args.user, password=password, timeout=8, allow_agent=False, look_for_keys=False)
        code = base["log_command"](
            ssh, args.output / "capacidades.log",
            "tr -d '\\000' </proc/device-tree/model; echo; uname -srmo; vcgencmd version; "
            "vcgencmd commands; vcgencmd pmic_read_adc EXT5V_V; echo adc_exit=$?; vcgencmd get_throttled"
        )
        if code:
            raise RuntimeError("No se pudo verificar el firmware.")

        with ExitStack() as files:
            trace = files.enter_context((args.output / "telemetria.csv").open("x", encoding="utf-8", newline=""))
            raw = files.enter_context((args.output / "salida-firmware.log").open("x", encoding="utf-8"))
            qlog = files.enter_context((args.output / "operaciones.csv").open("x", encoding="utf-8", newline=""))
            sql = files.enter_context(Psql(ssh, password, db))
            sql.execute("SET default_transaction_read_only=on; SET statement_timeout='8s';")
            stream = files.enter_context(base["channel"](ssh, SAMPLER, 10))
            writer = csv.writer(trace)
            writer.writerow(("timestamp_utc", "elapsed_s", "phase", "vc4_core_v", "arm_clock_mhz",
                             "soc_temp_c", "firmware_flags", "input_5v_v"))
            operations = csv.writer(qlog)
            operations.writerow(("timestamp_utc", "elapsed_s", "latency_ms", "rows", "result_validation"))

            def collect():
                try:
                    for line in stream.makefile("r"):
                        if stopped.is_set():
                            return
                        timestamp = utc()
                        current = phase
                        print(timestamp, current, line.rstrip(), file=raw, flush=True)
                        volts, freq, flags, thermal = line.rstrip().split("\t")
                        v = float(volts.removeprefix("volt=").removesuffix("V"))
                        mhz = int(freq.split("=")[-1]) / 1e6
                        mask = flags.removeprefix("throttled=")
                        temp = int(thermal) / 1000
                        writer.writerow((timestamp, round(monotonic() - start, 3), current, v, mhz, temp, mask, None))
                        trace.flush()
                        samples.append((current, v, mhz, temp, mask))
                        if temp >= 70 or int(mask, 16) & 0xF:
                            errors.append(f"Parada preventiva: {temp} °C, máscara {mask}.")
                            return
                    if not stopped.is_set():
                        errors.append("El flujo del firmware se interrumpió.")
                except Exception as exc:
                    if not stopped.is_set():
                        errors.append(str(exc))

            def wait_phase(seconds):
                until = monotonic() + seconds
                while monotonic() < until and not errors:
                    sleep(0.2)

            phase = "reposo"
            worker = Thread(target=collect, daemon=True)
            worker.start()
            try:
                wait_phase(25)
                phase = "carga"
                deadline = monotonic() + 25
                statement = QUERIES["q1"].replace("__TABLE__", "orders_10000")
                while monotonic() < deadline and not errors:
                    started = monotonic()
                    result = sql.execute(statement)
                    valid = result == reference
                    elapsed = monotonic() - started
                    operations.writerow((utc(), round(started - start, 3), round(elapsed * 1000, 3), len(result), valid))
                    qlog.flush()
                    if not valid:
                        raise RuntimeError("Q1 difiere de la referencia.")
                    queries.append(elapsed)
                phase = "recuperacion"
                wait_phase(15)
            finally:
                stopped.set()
                stream.close()
                worker.join(timeout=10)
    summary = {"status": "interrupted" if errors else "completed", "errors": errors,
               "input_5v": "no medido", "energy": "no medida", "q1_valid_queries": len(queries), "phases": {}}
    for condition in ("reposo", "carga", "recuperacion"):
        rows = [row for row in samples if row[0] == condition]
        if rows:
            summary["phases"][condition] = {
                "samples": len(rows), "vc4_core_v_min": min(r[1] for r in rows),
                "vc4_core_v_median": median(r[1] for r in rows), "vc4_core_v_max": max(r[1] for r in rows),
                "arm_mhz": sorted({r[2] for r in rows}), "soc_temp_c_max": max(r[3] for r in rows),
                "firmware_flags": sorted({r[4] for r in rows}),
            }
    if not errors and (len(summary["phases"]) != 3 or not queries):
        summary["status"] = "incomplete"
    write_json(args.output / "resumen.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    if summary["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    warnings.filterwarnings("error", category=GetPassWarning)
    diagnose(args, getpass("Contraseña SSH (entrada oculta): "))
