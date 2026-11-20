"""Encadena los diagnósticos y el bloque MongoDB al ensayo PostgreSQL en curso."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
from getpass import getpass
import json
from pathlib import Path
import subprocess
import sys
from time import monotonic, sleep, time
from types import SimpleNamespace
import traceback

import extension_eva02
import extension_mongo
from experimento import ROOT, utc, write_json


def predecessor(path):
    deadline = monotonic() + 3 * 3600
    while monotonic() < deadline:
        try:
            record = json.loads((path / "estado.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            sleep(5)
            continue
        if record.get("ended_utc"):
            sleep(15)  # Da margen a la captura final del proceso anterior.
            return record
        if time() - (path / "telemetria.csv").stat().st_mtime > 180:
            raise RuntimeError("El primer ensayo dejó de escribir telemetría.")
        sleep(10)
    raise TimeoutError("El primer ensayo no confirmó su cierre en tres horas.")


def run(args, password):
    status = {"started_utc": utc(), "stage": "waiting_mongodb" if args.resume_from else "waiting_postgresql",
              "status": "running", "blocks": {}}
    state_path = args.raw / "estado.json"
    sibling = args.predecessor.parent
    write_json(state_path, status)
    try:
        first = predecessor(args.predecessor)
        previous = ROOT / "results/raw/benchmark-v1"
        diagnostic = ("postgresql-diagnostico", extension_eva02.experiment, {"previous": previous, "diagnostic": True})
        if args.resume_from:
            status["blocks"]["mongodb"] = first
            targets = [("postgresql-v2", extension_eva02.experiment, {
                "previous": previous, "diagnostic": False, "resume": args.resume_from,
            }), diagnostic]
        else:
            status["blocks"]["postgresql"] = first
            targets = [diagnostic] if first["status"] == "completed" else []
            targets.append(("mongodb", extension_mongo.experiment, {"dataset": ROOT / "dataset/generado-v1"}))
        for name, experiment, extra in targets:
            if name == "postgresql-diagnostico" and status["blocks"].get("postgresql-v2", first)["status"] != "completed":
                status["blocks"][name] = {"status": "skipped", "reason": "La matriz PostgreSQL se interrumpió antes de cerrar."}
                continue
            status.update(stage=name)
            write_json(state_path, status)
            sleep(90)  # Recuperación entre motores o bloques independientes.
            directory = sibling / f"extension-eva02-{name if name.endswith('-v2') else name + '-v1'}"
            try:
                experiment(SimpleNamespace(host=args.host, user=args.user, raw=directory, **extra), password)
            except Exception:
                traceback.print_exc()
            try:
                status["blocks"][name] = json.loads((directory / "estado.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                status["blocks"][name] = {"status": "failed", "reason": "No hay estado válido del bloque"}
        statuses = {block["status"] for block in status["blocks"].values()}
        status.update(stage="closed", status="completed" if statuses == {"completed"} else "partial")
    except Exception as exc:
        status.update(status="failed", error=str(exc))
        raise
    finally:
        status["ended_utc"] = utc()
        write_json(state_path, status)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", default="rasp")
    parser.add_argument("--predecessor", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--resume-from", type=Path, help="Reanuda PostgreSQL tras el cierre del bloque MongoDB.")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        secret = sys.stdin.readline().rstrip("\r\n")
        sys.stdin.close()
        with (args.raw / "supervision.log").open("x", encoding="utf-8", buffering=1) as log:
            with redirect_stdout(log), redirect_stderr(log):
                try:
                    run(args, secret)
                except Exception:
                    traceback.print_exc()
                    raise SystemExit(1)
    else:
        secret = getpass("Contraseña SSH (entrada oculta): ")
        args.raw.mkdir(parents=True, exist_ok=False)
        child = subprocess.Popen([sys.executable, __file__, *sys.argv[1:], "--worker"],
                                 stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
        with child.stdin:
            child.stdin.write((secret + "\n").encode())
        print(f"Supervisor iniciado. PID {child.pid}.")
