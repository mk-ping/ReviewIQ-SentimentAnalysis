"""Exports up to 200 analysed reviews with the model's aspects, for hand labelling.
Refuses to overwrite an existing file, so your labels are never lost."""
import asyncio
import csv
from pathlib import Path

from sqlalchemy import text

from app.db.session import SessionLocal, engine

OUT = Path("../data/aspect_labels.csv")


async def main(n: int = 200):
    if OUT.exists():
        print(f"{OUT} already exists. Rename or delete it yourself if you want a fresh export.")
        return
    async with SessionLocal() as s:
        rows = (await s.execute(text("""
            SELECT r.review_id, r.text_clean FROM review r
            JOIN review_aspect_run u ON u.review_id = r.review_id
            ORDER BY md5(r.review_id::text) LIMIT :n"""), {"n": n})).all()
        ids = [r[0] for r in rows]
        preds = (await s.execute(text("""
            SELECT ra.review_id, a.name, ra.sentiment FROM review_aspect ra
            JOIN aspect a ON a.aspect_id = ra.aspect_id
            WHERE ra.review_id = ANY(CAST(:ids AS bigint[]))"""), {"ids": ids})).all()
    by: dict[int, list[str]] = {}
    for rid, name, sent in preds:
        by.setdefault(rid, []).append(f"{name}:{sent:g}")
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["review_id", "text", "predicted", "gold"])
        for rid, t in rows:
            w.writerow([rid, t, "; ".join(by.get(rid, [])), ""])
    print(f"wrote {len(rows)} reviews to {OUT}")
    await engine.dispose()


asyncio.run(main())
