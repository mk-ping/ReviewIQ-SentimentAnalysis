
"""Tune the mismatch thresholds on the gold set. Needs reviews labelled with a mismatch yes or no (Label page).
The text score is recovered from the stored fused stars, so scoring must have run.
Run from backend:  python -m scripts.tune_thresholds [--write]    (--write saves docs/thresholds_tuned.md)"""
import argparse
import asyncio
from datetime import date
from pathlib import Path

from sqlalchemy import text

from app.core import thresholds as T
from app.db.session import SessionLocal
from app.services import tuning as U


def _fmt(x):
    return "-" if x is None else f"{x:.2f}"


async def main(write: bool) -> None:
    async with SessionLocal() as s:
        rows = (await s.execute(text("""
            SELECT g.mismatch_label, s.fused_stars, r.rating_norm, s.confidence
            FROM gold_label g JOIN review r ON r.review_id = g.review_id JOIN review_score s ON s.review_id = g.review_id
            WHERE g.source = 'gold' AND g.mismatch_label IS NOT NULL
              AND s.fused_stars IS NOT NULL AND r.rating_norm IS NOT NULL"""))).all()
    data = [(bool(m), U.text_score_from_fused(f, st, c, T.FUSION_W_MIN, T.FUSION_W_MAX), (st - 3) / 2, c) for m, f, st, c in rows]
    res = U.tune(data)
    if not res["ok"]:
        print(res["reason"])
        return
    cur, best = res["current"], res["best"]
    lines = [f"Mismatch threshold tuning on {res['n']} gold reviews ({res['positives']} real mismatches), {date.today()}",
             f"Current (diff {T.MISMATCH_DIFF}, conf {T.MISMATCH_MIN_CONF}): flagged {cur['flagged']}, precision {_fmt(cur['precision'])}, recall {_fmt(cur['recall'])}, F1 {_fmt(cur['f1'])}",
             f"Best    (diff {best['diff']}, conf {best['conf']}): flagged {best['flagged']}, precision {_fmt(best['precision'])}, recall {_fmt(best['recall'])}, F1 {_fmt(best['f1'])}",
             "" if res["precision_goal_met"] else f"No setting reached precision {U.MIN_PRECISION}; the best F1 is shown instead.",
             "Top 5:"] + [f"  diff {g['diff']} conf {g['conf']}: flagged {g['flagged']}, precision {_fmt(g['precision'])}, recall {_fmt(g['recall'])}, F1 {_fmt(g['f1'])}" for g in res["top"]]
    lines.append("Only change core/thresholds.py if the gain is clear. With under ~100 labels it is within noise; the document says so.")
    print("\n".join(l for l in lines if l))
    if write:
        Path("../docs/thresholds_tuned.md").write_text("# Tuned thresholds\n\n```\n" + "\n".join(l for l in lines if l) + "\n```\n", encoding="utf-8")
        print("wrote ../docs/thresholds_tuned.md")


ap = argparse.ArgumentParser()
ap.add_argument("--write", action="store_true")
asyncio.run(main(ap.parse_args().write))
