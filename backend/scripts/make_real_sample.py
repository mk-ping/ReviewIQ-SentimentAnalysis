import csv
import json
from pathlib import Path

rows = [json.loads(x) for x in Path("../ml/data/test_unseen.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
rows = [r for r in rows if r["star"] >= 0][:600]
with open("../data/real_sample.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["Product", "Rating", "Review"])
    for r in rows:
        w.writerow([r["src"].split(":")[-1], r["star"] + 1, r["text"]])
print("wrote", len(rows), "reviews")
