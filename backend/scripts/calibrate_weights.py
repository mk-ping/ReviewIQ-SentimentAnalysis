"""Ensemble weights = macro F1 of each model on the validation reviews of each route group (study guide 5.11).
Dry run by default; add --apply to write model_weight. Run scoring first so the validation reviews have predictions.
A group with fewer than MIN_VAL_PER_GROUP validation reviews is stored, but fusion keeps equal weights for it.
Run from backend:  python -m scripts.calibrate_weights [--apply]"""
import argparse
import asyncio
from collections import defaultdict

from sqlalchemy import text

from app.core import thresholds as T
from app.db.session import SessionLocal, engine
from app.services import sentiment
from app.services.routing import MEMBERS, group_of

FLOOR = 0.01


def label_of(stars: float) -> str:
    s = round(stars)
    return "neg" if s <= 2 else "neu" if s == 3 else "pos"


def macro_f1(gold, pred):
    f1s = []
    for c in ("neg", "neu", "pos"):
        tp = sum(1 for g, p in zip(gold, pred) if g == c and p == c)
        fp = sum(1 for g, p in zip(gold, pred) if g != c and p == c)
        fn = sum(1 for g, p in zip(gold, pred) if g == c and p != c)
        if tp + fn:
            f1s.append(2 * tp / (2 * tp + fp + fn))
    return sum(f1s) / len(f1s) if f1s else None


async def main(apply: bool) -> None:
    key_of = {(c["name"], c["version"]): k for k, c in sentiment.registry().items()}
    async with SessionLocal() as s:
        rows = (await s.execute(text("""
            SELECT review_id, language, rating_norm FROM review
            WHERE split = 'validation' AND rating_norm IS NOT NULL AND spam_score <= :sp"""), {"sp": T.SPAM_MAX})).all()
        preds = (await s.execute(text("""
            SELECT p.review_id, p.model_id, m.name, m.version, p.p_neg, p.p_neu, p.p_pos FROM prediction p
            JOIN model m ON m.model_id = p.model_id JOIN review r ON r.review_id = p.review_id
            WHERE r.split = 'validation' AND r.rating_norm IS NOT NULL"""))).all()
        stars = {rid: st for rid, _, st in rows}
        groups: dict[str, list[int]] = defaultdict(list)
        for rid, lang, _ in rows:
            groups[group_of(lang)].append(rid)
        by_model: dict[str, dict[int, tuple]] = defaultdict(dict)
        mids: dict[str, int] = {}
        for rid, mid, name, ver, pn, pu, pp in preds:
            k = key_of.get((name, ver))
            if k:
                by_model[k][rid] = (pn, pu, pp)
                mids[k] = mid
        if not rows:
            print("No validation reviews with a star rating yet. Upload and score some rated reviews first.")
        result = []
        for g, ids in groups.items():
            for k in MEMBERS[g]:
                have = [i for i in ids if i in by_model.get(k, {})]
                if not have:
                    continue
                gold = [label_of(stars[i]) for i in have]
                pred = [("neg", "neu", "pos")[max(range(3), key=lambda j: by_model[k][i][j])] for i in have]
                f1 = macro_f1(gold, pred)
                if f1 is not None:
                    result.append((g, k, max(f1, FLOOR), len(ids), len(have)))
        print(f"{'group':9s} {'model':8s} {'weight':>7s} {'val reviews':>11s} {'scored':>7s}  status")
        for g, k, w, n, h in result:
            status = "used" if n >= T.MIN_VAL_PER_GROUP else f"stored; equal weights stay in force (under {T.MIN_VAL_PER_GROUP})"
            print(f"{g:9s} {k:8s} {w:7.3f} {n:11d} {h:7d}  {status}")
        if not apply:
            print("Dry run. Add --apply to write these to model_weight.")
        else:
            for g, k, w, n, _ in result:
                await s.execute(text("""
                    INSERT INTO model_weight (route_group, model_id, weight, n_val) VALUES (:g, :m, :w, :n)
                    ON CONFLICT (route_group, model_id) DO UPDATE SET weight = :w, n_val = :n, updated_at = now()"""),
                    {"g": g, "m": mids[k], "w": round(w, 4), "n": n})
            await s.commit()
            print("model_weight updated. Run python -m scripts.backfill_scores to apply the weights.")
    await engine.dispose()


ap = argparse.ArgumentParser()
ap.add_argument("--apply", action="store_true")
asyncio.run(main(ap.parse_args().apply))
