"""Is any public polarity source labelled in the wrong order? Runs the pretrained multilingual model on the polarity rows
and prints, per source, how its votes line up with the dataset labels. Mirrored counts mean the labels are swapped.
Run from backend:  python -m scripts.label_order_check [--cap 200]"""
import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from app.services import evaluation as E
from app.services import sentiment

DATA = Path("../ml/data")
NAMES = ("neg", "neu", "pos")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, default=200)
    a = ap.parse_args()
    rows = []
    for f in ("val.jsonl", "test_seen.jsonl"):
        p = DATA / f
        if p.exists():
            rows += [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    by = defaultdict(list)
    for r in rows:
        if r["star"] < 0:
            by[r["src"]].append(r)
    if not by:
        print("No polarity rows in ml/data. Build the data first (ml/reviewiq_train.py build).")
        return
    rng = random.Random(7)
    for src, rs in sorted(by.items()):
        rng.shuffle(rs)
        rs = rs[: a.cap]
        if len(rs) < 20:
            continue
        votes = sentiment.predict([r["text"] for r in rs], 32, "xlmr")
        conf = {g: Counter() for g in NAMES}
        for r, p in zip(rs, votes):
            conf[NAMES[r["pol"]]][E.argmax_label(*p[:3])] += 1
        same = conf["neg"]["neg"] + conf["pos"]["pos"]
        flip = conf["neg"]["pos"] + conf["pos"]["neg"]
        verdict = ("MIRRORED: negative and positive look swapped" if flip > 1.5 * same
                   else "labels agree with the model" if same > 1.5 * flip else "unclear")
        print(f"\n{src}  n={len(rs)}  -> {verdict}")
        print("  dataset label -> model vote (neg / neu / pos)")
        for g in NAMES:
            print(f"  {g:4s} -> " + " / ".join(f"{conf[g][p]:3d}" for p in NAMES))


if __name__ == "__main__":
    main()
