"""Crea copias de evidencia textual sin identificadores de la red doméstica."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
TARGETS = (
    ("sesion-2026-11-18/inventario.log", "inventario-redactado.log", "utf-8"),
    ("benchmark-v1/rtt.log", "rtt-redactado.log", "cp850"),
)

if __name__ == "__main__":
    output = ROOT / "redacted"
    output.mkdir(exist_ok=True)
    for relative, name, encoding in TARGETS:
        content = (ROOT / "raw" / relative).read_text(encoding=encoding)
        content = re.sub(r"(?i)(?:\b[\da-f]{2}:){5}[\da-f]{2}\b", "[MAC retirada]", content)
        content = re.sub(r"\b(?:192\.168|10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b",
                         "[IP local retirada]", content)
        clean = "\n".join(line.rstrip() for line in content.splitlines()).rstrip()
        (output / name).write_text("Copia de publicación. Se retiraron IP local y/o MAC.\n\n" + clean + "\n", encoding="utf-8")
