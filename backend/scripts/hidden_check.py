"""Hand-check of Hidden Dissatisfaction (document section 14: about 100 flagged and 100 unflagged reviews rated 4 or more).
  python -m scripts.hidden_check export   -> ../data/hidden_check.csv (refuses to overwrite your labels)
  python -m scripts.hidden_check score    -> precision, miss rate and an estimated recall from the filled 'hidden' column
Fill 'hidden' with 1 if the review really contains a complaint about the product, 0 if it does not."""
import asyncio
import csv
import sys
from pathlib import Path

from sqlalchemy import text

from app.core import thresholds as T
from app.db.session import SessionLocal
from app.services.hidden_eval import summarise

PATH = Path("../data/hidden_check.csv")
META = Path("../data/hidden_check_meta.txt")
BASE = """FROM review r JOIN review_aspect_run u ON u.review_id = r.review_id
          WHERE r.rating_norm >= :hid AND r.spam_score <= :spam"""
NEG = """EXISTS (SELECT 1 FROM review_aspect ra WHERE ra.review_id = r.review_id AND ra.sentiment <= :neg
        AND ra.confidence >= :conf AND ra.evidence_span IS NOT NULL AND ra.evidence_span <> '')"""


async def export(n: int = 100):
    if PATH.exists():
        print(f"{PATH} already exists. Rename or delete it yourself for a fresh export."); return
    a = {"hid": T.HIDDEN_MIN_STARS, "spam": T.SPAM_MAX, "neg": T.NEG_MENTION, "conf": T.ASPECT_MIN_CONF, "n": n}
    async with SessionLocal() as s:
        f_pop = await s.scalar(text(f"SELECT count(*) {BASE} AND {NEG}"), a)
        u_pop = await s.scalar(text(f"SELECT count(*) {BASE} AND NOT {NEG}"), a)
        flagged = (await s.execute(text(f"""
            SELECT r.review_id, r.rating_norm, r.text_clean,
                   (SELECT ra.evidence_span FROM review_aspect ra WHERE ra.review_id = r.review_id AND ra.sentiment <= :neg
                      AND ra.confidence >= :conf ORDER BY ra.sentiment LIMIT 1)
            {BASE} AND {NEG} ORDER BY md5(r.review_id::text) LIMIT :n"""), a)).all()
        unflagged = (await s.execute(text(f"""
            SELECT r.review_id, r.rating_norm, r.text_clean, NULL {BASE} AND NOT {NEG} ORDER BY md5(r.review_id::text) LIMIT :n"""), a)).all()
    rows = [(1, *r) for r in flagged] + [(0, *r) for r in unflagged]
    # shuffle so you cannot tell which are flagged while labelling
    rows.sort(key=lambda r: hash((r[1], "hidden")) )
    PATH.parent.mkdir(parents=True, exist_ok=True)
    with PATH.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh); w.writerow(["review_id", "flagged", "stars", "text", "flagged_phrase", "hidden"])
        w.writerows([[r[1], r[0], r[2], r[3], r[4] or "", ""] for r in rows])
    META.write_text(f"{f_pop} {u_pop}\n")
    print(f"wrote {len(rows)} reviews ({len(flagged)} flagged, {len(unflagged)} unflagged) to {PATH}")
    print("Judge the review text first. The 'flagged' column is there for scoring, so try not to peek.")


def score():
    rows = []
    for r in csv.DictReader(PATH.open(encoding="utf-8-sig")):
        if r["hidden"].strip() in ("0", "1"):
            rows.append({"flagged": r["flagged"] == "1", "hidden": r["hidden"].strip() == "1"})
    if not rows:
        print("No labelled rows yet."); return
    pops = META.read_text().split() if META.exists() else []
    res = summarise(rows, int(pops[0]) if pops else None, int(pops[1]) if len(pops) > 1 else None)
    fmt = lambda v: "n/a" if v is None else f"{v:.2f}"
    rng = lambda v: "n/a" if v is None else f"{v[0]:.2f}-{v[1]:.2f}"
    print(f"flagged reviews checked {res['flagged_checked']}: precision {fmt(res['precision'])} (95% range {rng(res['precision_range'])})")
    print(f"unflagged reviews checked {res['unflagged_checked']}: miss rate {fmt(res['miss_rate'])} (95% range {rng(res['miss_range'])})")
    print(f"estimated recall {fmt(res['recall_estimate'])}  (needs the population sizes saved at export)")
    print("Small samples give wide ranges. Quote the range, not just the point value.")


if __name__ == "__main__":
    asyncio.run(export()) if sys.argv[1:] == ["export"] else score()
