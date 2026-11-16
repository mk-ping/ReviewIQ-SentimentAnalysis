"""Trains the TF-IDF + Logistic Regression baseline (the only model we train) and saves it.
Reads only public data: ../ml/data/train.jsonl (from ml/reviewiq_train.py build) and CSVs in ../data/external/.
Run from backend:  python -m scripts.train_tfidf"""
import csv
import json
import random
import re
from collections import Counter
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline

from app.core.config import settings


def label3(star: float) -> str:
    s = round(star)
    return "neg" if s <= 2 else "neu" if s == 3 else "pos"


def jsonl_rows():
    p = Path("../ml/data/train.jsonl")
    out = []
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if len(r["text"].split()) < 2:
            continue
        if r["star"] >= 0:
            out.append((r["text"], label3(r["star"] + 1)))
        elif r["pol"] >= 0:
            out.append((r["text"], ("neg", "neu", "pos")[r["pol"]]))
    print(f"ml/data/train.jsonl: {len(out)} rows")
    return out


def external_rows():
    out = []
    for p in sorted(Path("../data/external").glob("*.csv")):
        rows = list(csv.DictReader(p.open(encoding="utf-8-sig", errors="replace", newline="")))
        if not rows:
            continue
        cols, sample = list(rows[0]), rows[:200]
        tcol = max(cols, key=lambda c: sum(len(r.get(c) or "") for r in sample))
        rcol = next((c for c in cols if c != tcol and
                     sum(bool(re.fullmatch(r"[1-5](\.0)?", (r.get(c) or "").strip())) for r in sample) > 0.95 * max(len(sample), 1)), None)
        if not rcol:
            print(f"skip {p.name}: no 1-5 rating column")
            continue
        n = 0
        for r in rows:
            t, v = (r.get(tcol) or "").strip(), (r.get(rcol) or "").strip()
            if len(t.split()) >= 2 and re.fullmatch(r"[1-5](\.0)?", v):
                out.append((t, label3(float(v))))
                n += 1
        print(f"{p.name}: {n} rows (text={tcol}, rating={rcol})")
    return out


def make_pipe():
    # the token pattern splits on spaces and punctuation, so Hindi (Devanagari) words are not cut at their vowel signs
    return make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_features=50000, token_pattern=r"[^\s.,!?;:()\[\]\"]+"),
        LogisticRegression(max_iter=1000, class_weight="balanced"),
    )


rows = jsonl_rows() + external_rows()
print(f"training rows: {len(rows)}   labels: {dict(Counter(y for _, y in rows))}")
if len(rows) < 50:
    print("Too few training rows. Run 'python reviewiq_train.py build' in the ml folder, or put review CSVs in data/external/.")
    raise SystemExit(1)

random.Random(7).shuffle(rows)
X, y = [t for t, _ in rows], [l for _, l in rows]
xa, xb, ya, yb = train_test_split(X, y, test_size=0.1, random_state=7, stratify=y if min(Counter(y).values()) >= 2 else None)
check = make_pipe().fit(xa, ya)
pred = check.predict(xb)
print(f"sanity check on 10% of the public data: macro F1 {f1_score(yb, pred, average='macro'):.3f}, accuracy {accuracy_score(yb, pred):.3f}")
print("(this is NOT a reported score; the reported scores come from the held-out reviews in your database)")

pipe = make_pipe().fit(X, y)
out = Path(settings.tfidf_path)
out.parent.mkdir(parents=True, exist_ok=True)
joblib.dump(pipe, out)
print("saved", out)
