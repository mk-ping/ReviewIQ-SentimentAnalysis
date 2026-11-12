import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8010"
FIX = Path(__file__).resolve().parents[2] / "data" / "fixtures"
EXPECT_TEXT = {
    "amazon_sample.csv": "review_text",
    "flipkart_semicolon.csv": "Review",
    "mixed_formats.csv": "Comment",
}


def detail(r):
    try:
        d = r.json().get("detail")
    except Exception:
        d = r.text
    return d.get("message") if isinstance(d, dict) else str(d)


def main() -> int:
    failures, table = [], []
    with httpx.Client(base_url=BASE, timeout=300) as c:
        for f in sorted(FIX.iterdir()):
            if not f.is_file():
                continue
            with f.open("rb") as fh:
                u = c.post("/uploads", files={"file": (f.name, fh)})
            if u.status_code >= 500:
                failures.append(f"{f.name}: upload gave {u.status_code}")
                continue
            if u.status_code != 200:
                table.append((f.name, "rejected cleanly", str(u.status_code), detail(u)[:60]))
                continue
            bid = u.json()["batch_id"]

            m = c.get(f"/uploads/{bid}/mapping")
            if m.status_code >= 500:
                failures.append(f"{f.name}: mapping gave {m.status_code}")
                continue
            if m.status_code != 200:
                table.append((f.name, "asks user to pick text", str(m.status_code), detail(m)[:60]))
                continue
            roles = {x["role"]: x["column"] for x in m.json()["mapping"] if x["column"]}
            want = EXPECT_TEXT.get(f.name)
            if want and roles.get("text") != want:
                failures.append(f"{f.name}: text column is {roles.get('text')!r}, expected {want!r}")

            p = c.put(f"/uploads/{bid}/mapping")
            if p.status_code >= 500:
                failures.append(f"{f.name}: ingest gave {p.status_code}: {detail(p)}")
                continue
            if p.status_code != 200:
                table.append((f.name, "ingest refused cleanly", str(p.status_code), detail(p)[:60]))
                continue
            rep = p.json()
            if not rep["adds_up"]:
                failures.append(f"{f.name}: accepted+repaired+rejected != total ({rep})")
            table.append((f.name, "ok" if rep["adds_up"] else "BAD COUNTS", "200",
                          f"total={rep['rows_total']} ok={rep['accepted']} fixed={rep['repaired']} rej={rep['rejected']} saved={rep['reviews_saved']}"))

    for row in table:
        print(" | ".join(row))
    if failures:
        print("\nFAILURES:")
        for x in failures:
            print(" -", x)
        return 1
    print("ingest checks passed")
    return 0


sys.exit(main())
