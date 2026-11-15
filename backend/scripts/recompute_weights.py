
"""Recompute ensemble weights against the hand-labelled gold set instead of stars (document section 5).
Needs 200+ gold labels. Dry run by default; add --apply to write model_weight.
A group with fewer than 100 gold reviews is stored but fusion keeps equal weights for it (MIN_VAL_PER_GROUP).
Run from backend:  python -m scripts.recompute_weights [--apply]"""
import argparse
import asyncio

from sqlalchemy import text

from app.core import thresholds as T
from app.db.session import SessionLocal
from app.services import sentiment
from app.services.routing import group_of
from app.services.weights import MIN_GOLD_TOTAL, model_weights


async def main(apply: bool) -> None:
    key_of = {(c["name"], c["version"]): k for k, c in sentiment.registry().items()}
    async with SessionLocal() as s:
        gold_rows = (await s.execute(text("""
            SELECT g.review_id, g.label, r.language FROM gold_label g JOIN review r ON r.review_id = g.review_id
            WHERE g.source = 'gold'"""))).all()
        if len(gold_rows) < MIN_GOLD_TOTAL:
            print(f"{len(gold_rows)} gold labels; {MIN_GOLD_TOTAL} are needed. Keep labelling on the Label page.")
            return
        gold = {r[0]: r[1] for r in gold_rows}
        groups = {r[0]: group_of(r[2]) for r in gold_rows}
        preds: dict[str, dict[int, tuple]] = {}
        mids: dict[str, int] = {}
        for rid, mid, n, v, pn, pu, pp in (await s.execute(text("""
            SELECT p.review_id, m.model_id, m.name, m.version, p.p_neg, p.p_neu, p.p_pos FROM prediction p
            JOIN model m ON m.model_id = p.model_id JOIN gold_label g ON g.review_id = p.review_id AND g.source = 'gold'"""))).all():
            k = key_of.get((n, v))
            if k:
                preds.setdefault(k, {})[rid] = (pn, pu, pp)
                mids[k] = mid
        result = model_weights(gold, groups, preds)
        for g, d in result.items():
            use = "used" if d["n"] >= T.MIN_VAL_PER_GROUP else f"stored, but equal weights stay in force (under {T.MIN_VAL_PER_GROUP})"
            print(f"{g:9s} gold={d['n']:4d}  {d['weights']}  [{use}]")
        if not apply:
            print("Dry run. Add --apply to write these to model_weight.")
            return
        for g, d in result.items():
            for k, w in d["weights"].items():
                if k in mids:
                    await s.execute(text("""
                        INSERT INTO model_weight (route_group, model_id, weight, n_val) VALUES (:g, :m, :w, :n)
                        ON CONFLICT (route_group, model_id) DO UPDATE SET weight = :w, n_val = :n, updated_at = now()"""),
                        {"g": g, "m": mids[k], "w": w, "n": d["n"]})
        await s.commit()
        print("model_weight updated. Re-run scoring (or scripts.backfill_scores) to apply the new weights.")


ap = argparse.ArgumentParser()
ap.add_argument("--apply", action="store_true")
asyncio.run(main(ap.parse_args().apply))
