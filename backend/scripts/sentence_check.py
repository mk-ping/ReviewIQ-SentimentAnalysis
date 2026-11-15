"""Hand-check of aspect tags (document section 14: about 100 sentences).
  python -m scripts.sentence_check export   -> ../data/sentence_check.csv (refuses to overwrite your labels)
  python -m scripts.sentence_check score    -> precision per aspect from the filled 'correct' column (1 yes, 0 no)"""
import asyncio
import csv
import sys
from pathlib import Path

from sqlalchemy import text

from app.db.session import SessionLocal

PATH = Path("../data/sentence_check.csv")


async def export(n: int = 100):
    if PATH.exists():
        print(f"{PATH} already exists. Rename or delete it yourself for a fresh export."); return
    async with SessionLocal() as s:
        rows = (await s.execute(text("""SELECT sent_id, aspect, method, round(sim::numeric,3), sentence FROM sentence_aspect
            WHERE aspect <> 'general' ORDER BY md5(sent_id::text) LIMIT :n"""), {"n": n})).all()
    PATH.parent.mkdir(parents=True, exist_ok=True)
    with PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["sent_id", "aspect", "method", "sim", "sentence", "correct"])
        w.writerows([list(r) + [""] for r in rows])
    print(f"wrote {len(rows)} sentences to {PATH}. Fill the 'correct' column with 1 or 0, then run: score")


def score():
    by: dict[str, list[int]] = {}
    for r in csv.DictReader(PATH.open(encoding="utf-8")):
        if r["correct"].strip() in ("0", "1"):
            by.setdefault(r["aspect"], []).append(int(r["correct"]))
    allv = [v for vs in by.values() for v in vs]
    if not allv:
        print("No labelled rows yet."); return
    for a, vs in sorted(by.items()):
        print(f"{a:12s} n={len(vs):3d} precision={sum(vs)/len(vs):.2f}")
    print(f"overall      n={len(allv):3d} precision={sum(allv)/len(allv):.2f}  (tags checked by hand, not recall)")


if __name__ == "__main__":
    asyncio.run(export()) if sys.argv[1:] == ["export"] else score()
