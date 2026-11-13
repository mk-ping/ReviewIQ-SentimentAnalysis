import csv
import io
import random
import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8010"
SRC = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "amazon_sample.csv"


def to_csv(rows) -> bytes:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue().encode("utf-8")


def variants():
    raw = SRC.read_bytes()
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    rng = random.Random(7)
    order = list(range(len(rows[0])))
    rng.shuffle(order)
    yield "fuzz_shuffled.csv", to_csv([[r[i] for i in order] for r in rows])
    yield "fuzz_no_header.csv", to_csv(rows[1:])
    yield "fuzz_blank_header.csv", to_csv([[""] * len(rows[0])] + rows[1:])
    for n in range(3):
        b = bytearray(raw)
        for _ in range(8):
            b[rng.randrange(len(b))] = rng.randrange(256)
        yield f"fuzz_corrupt{n}.csv", bytes(b)
    yield "fuzz_truncated.csv", raw[: len(raw) // 2]
    yield "fuzz_random.bin", bytes(rng.randrange(256) for _ in range(500))


def main() -> int:
    failures = []
    with httpx.Client(base_url=BASE, timeout=300) as c:
        for name, data in variants():
            u = c.post("/uploads", files={"file": (name, data)})
            line = f"{name:24} upload {u.status_code}"
            if u.status_code >= 500:
                failures.append(f"{name}: upload gave {u.status_code}")
            elif u.status_code == 200:
                m = c.get(f"/uploads/{u.json()['batch_id']}/mapping")
                line += f"  mapping {m.status_code}"
                if m.status_code >= 500:
                    failures.append(f"{name}: mapping gave {m.status_code}")
            print(line)
    if failures:
        print("FAILURES:")
        for f in failures:
            print(" -", f)
        return 1
    print("fuzz checks passed: nothing crashed")
    return 0


sys.exit(main())
