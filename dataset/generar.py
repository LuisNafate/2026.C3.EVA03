"""Genera prefijos JSONL y un manifiesto de pedidos sintéticos."""

import argparse
from contextlib import ExitStack
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import random

SIZES = (1000, 5000, 10000, 25000, 50000)
SEED = 202603
FROM_DATE = "2025-03-01"
TO_DATE = "2025-12-01"


def generate(directory):
    directory.mkdir(parents=True, exist_ok=False)
    rng = random.Random(SEED)
    countries = ("MX", "CO", "CL", "AR")
    categories = ("casa", "libros", "oficina", "tecnologia")
    hashes = {size: hashlib.sha256() for size in SIZES}
    item_counts = dict.fromkeys(SIZES, 0)
    qualified = dict.fromkeys(SIZES, 0)
    sizes_bytes = dict.fromkeys(SIZES, 0)
    with ExitStack() as stack:
        streams = {n: stack.enter_context((directory / f"orders-{n}.jsonl").open("xb")) for n in SIZES}
        for order_id in range(1, max(SIZES) + 1):
            timestamp = (date(2025, 1, 1) + timedelta(days=rng.randrange(365))).isoformat()
            status = rng.choices(("completed", "pending", "cancelled"), weights=(8, 1, 1))[0]
            items = []
            cents = 0
            for _ in range(rng.randint(1, 5)):
                qty, price_cents = rng.randint(1, 5), rng.randint(1000, 15000)
                items.append({"category": rng.choice(categories), "qty": qty, "price": price_cents / 100})
                cents += qty * price_cents
            order = {
                "order_id": order_id, "timestamp": timestamp, "status": status,
                "customer": {"country": rng.choice(countries), "geo": {
                    "lat": rng.randint(-45000, 32000) / 1000, "lon": rng.randint(-118000, -55000) / 1000,
                }},
                "items": items, "payment": {"final_total": cents / 100, "currency": "MXN"},
                "metadata": {"synthetic": True, "schema_version": 1},
            }
            line = (json.dumps(order, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")
            for size, stream in streams.items():
                if order_id <= size:
                    stream.write(line)
                    hashes[size].update(line)
                    sizes_bytes[size] += len(line)
                    item_counts[size] += len(items)
                    qualified[size] += status == "completed" and FROM_DATE <= timestamp < TO_DATE
    manifest = [
        {"dataset_id": f"orders-{n}", "seed": SEED, "documents": n, "items": item_counts[n],
         "q2_qualified": qualified[n], "bytes_jsonl": sizes_bytes[n], "sha256": hashes[n].hexdigest()}
        for n in SIZES
    ]
    (directory / "manifiesto.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    generate(parser.parse_args().directory)
