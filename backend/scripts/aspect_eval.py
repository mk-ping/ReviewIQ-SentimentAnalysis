"""Scores the model's aspects against your hand labels in data/aspect_labels.csv.
Gold format in the 'gold' column: category:score pairs separated by ';', for example
   packaging:-1; scent:1        (score from -1 to 1; only the sign band matters)
   none                         (the review has no specific opinion)
A blank gold cell means 'not labelled yet' and is skipped."""
import csv
from pathlib import Path

from app.core import thresholds as T
from app.core.aspect_config import CATEGORIES

SRC = Path("../data/aspect_labels.csv")


def band(x: float) -> str:
    return "neg" if x <= T.NEG_MENTION else "pos" if x >= -T.NEG_MENTION else "neu"


def parse(cell: str) -> dict[str, float]:
    out = {}
    for part in cell.split(";"):
        part = part.strip()
        if not part or part.lower() == "none":
            continue
        cat, _, val = part.rpartition(":")
        out[cat.strip().lower()] = float(val)
    return out


tp = fp = fn = 0
sent_ok = sent_n = labelled = 0
bad = []
for row in csv.DictReader(SRC.open(encoding="utf-8-sig", newline="")):
    g = (row["gold"] or "").strip()
    if not g:
        continue
    try:
        gold, pred = parse(g), parse(row["predicted"])
    except ValueError:
        bad.append(row["review_id"])
        continue
    unknown = [c for c in gold if c not in CATEGORIES]
    if unknown:
        bad.append(f"{row['review_id']} (unknown category {unknown})")
        continue
    labelled += 1
    gs, ps = set(gold), set(pred)
    tp += len(gs & ps)
    fp += len(ps - gs)
    fn += len(gs - ps)
    for c in gs & ps:
        sent_n += 1
        sent_ok += band(gold[c]) == band(pred[c])

if bad:
    print("could not read these rows:", bad)
if labelled == 0:
    print("No labelled rows yet. Fill the 'gold' column first.")
    raise SystemExit
p = tp / (tp + fp) if tp + fp else None
r = tp / (tp + fn) if tp + fn else None
f1 = 2 * p * r / (p + r) if p and r else None
fmt = lambda x: "n/a" if x is None else f"{x:.3f}"
print(f"reviews labelled: {labelled}" + ("  (the plan asks for about 200)" if labelled < 200 else ""))
print(f"aspect category: precision {fmt(p)}  recall {fmt(r)}  F1 {fmt(f1)}   (tp {tp}, fp {fp}, fn {fn})")
print(f"aspect sentiment (negative / neutral / positive) correct on matched aspects: {sent_ok}/{sent_n} = {fmt(sent_ok / sent_n if sent_n else None)}")
print("Categories:", ", ".join(CATEGORIES))
