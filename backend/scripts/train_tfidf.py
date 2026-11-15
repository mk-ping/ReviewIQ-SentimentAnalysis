"""Trains the TF-IDF + Logistic Regression baseline (the only model we train), saves it, then computes
validation macro F1 for every model per route group and writes model_weight.
Run from backend:  python -m scripts.train_tfidf
Extra training data: put CSV files with a text column and a 1-5 rating column in ../data/external/."""
import asyncio
import csv
import json
import re
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sqlalchemy import text

from app.core import thresholds as T
from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.services import evaluation as E
from app.services import sentiment
from app.services.routing import MEMBERS, group_of


def star_label(x):
    return None if x is None else E.stars_to_label(x)


def external_rows():
    out = []
    for p in sorted(Path("../data/external").glob("*.csv")):
        rows = list(csv.DictReader(p.open(encoding="utf-8-sig", errors="replace", newline="")))
        if not rows:
            continue
        cols = list(rows[0])
        sample = rows[:200]
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
                out.append((t, E.stars_to_label(float(v))))
                n += 1
        print(f"{p.name}: {n} rows (text={tcol}, rating={rcol})")
    return out


def jsonl_rows():
    """Training rows built by ml/reviewiq_train.py build: stars map to neg/neu/pos, polarity rows keep their label."""
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
            out.append((r["text"], E.stars_to_label(r["star"] + 1)))
        elif r["pol"] >= 0:
            out.append((r["text"], ("neg", "neu", "pos")[r["pol"]]))
    print(f"ml/data/train.jsonl: {len(out)} rows")
    return out


async def main():
    async with SessionLocal() as s:
        mine = (await s.execute(text("""
            SELECT text_clean, rating_norm FROM review WHERE split = 'test' AND rating_norm IS NOT NULL AND spam_score <= :sp"""),
            {"sp": T.SPAM_MAX})).all()
        val = (await s.execute(text("""
            SELECT review_id, text_clean, rating_norm, language FROM review
            WHERE split = 'validation' AND rating_norm IS NOT NULL AND spam_score <= :sp"""), {"sp": T.SPAM_MAX})).all()
    # Per the document: validation sets the weights, test is the reported set. Training uses neither.
    # So the database contributes no training rows; only external files train the model.
    train = external_rows() + jsonl_rows()
    print(f"training rows from data/external: {len(train)}   (database reviews are held out)")
    if len(train) < 50:
        print("Too few training rows. Put at least a few hundred labelled reviews in ../data/external/ and run again.")
        await engine.dispose()
        return
    pipe = make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_features=50000, sublinear_tf=True),
        LogisticRegression(max_iter=1000, class_weight="balanced"),
    )
    pipe.fit([t for t, _ in train], [y for _, y in train])
    out = Path(settings.tfidf_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, out)
    print("saved", out)

    # validation macro F1 per route group and model
    by_group: dict[str, list] = {}
    for rid, t, st, lang in val:
        by_group.setdefault(group_of(lang), []).append((rid, t, E.stars_to_label(st)))
    async with SessionLocal() as s:
        mids = {k: (await s.execute(text("SELECT model_id FROM model WHERE name = :n AND version = :v"),
                                    {"n": c["name"], "v": c["version"]})).scalar()
                for k, c in sentiment.registry().items()}
        for g, rows in by_group.items():
            print(f"\ngroup {g}: {len(rows)} validation reviews" + ("  (< 100: weights stay equal)" if len(rows) < T.MIN_VAL_PER_GROUP else ""))
            gold = [y for _, _, y in rows]
            for k in MEMBERS[g]:
                if k == "tfidf":
                    pred = list(pipe.predict([t for _, t, _ in rows]))
                else:
                    if not sentiment.available(k):
                        continue
                    pr = await asyncio.to_thread(sentiment.predict, [t for _, t, _ in rows], 32, k)
                    pred = [E.argmax_label(a, b, c) for a, b, c, _ in pr]
                f1 = E.macro_f1(gold, pred)
                print(f"  {k:8} macro F1 {'n/a' if f1 is None else format(f1, '.3f')}")
                if f1 and f1 > 0 and mids.get(k):
                    await s.execute(text("""
                        INSERT INTO model_weight (route_group, model_id, weight, n_val) VALUES (:g, :m, :w, :n)
                        ON CONFLICT (route_group, model_id) DO UPDATE SET weight = EXCLUDED.weight, n_val = EXCLUDED.n_val, updated_at = now()"""),
                        {"g": g, "m": mids[k], "w": f1, "n": len(rows)})
        await s.commit()
    await engine.dispose()


asyncio.run(main())
