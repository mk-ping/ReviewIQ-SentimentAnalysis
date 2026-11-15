
"""Bulk-load hand labels from a CSV so you do not have to click through 200 reviews.
CSV columns: text,label   (label is neg, neu or pos; optional column mismatch = 1/0)
The reviews must already be uploaded; each text is matched to a review after the same cleaning the upload uses.
Run from backend:  python -m scripts.import_gold_labels path\\to\\labels.csv
Labels must be a person's judgement of the TEXT. Labels copied from star ratings would make stars look perfect."""
import asyncio
import csv
import sys

from sqlalchemy import text

from app.db.session import SessionLocal
from app.services.cleaning import clean_text

VALID = {"neg", "neu", "pos"}


async def main(path: str) -> None:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows or "text" not in rows[0] or "label" not in rows[0]:
        print("The CSV needs columns named text and label.")
        return
    saved = skipped_label = missing = 0
    async with SessionLocal() as s:
        for r in rows:
            label = (r["label"] or "").strip().lower()
            if label not in VALID:
                skipped_label += 1
                continue
            rid = (await s.execute(text("SELECT review_id FROM review WHERE text_clean = :t ORDER BY review_id LIMIT 1"),
                                   {"t": clean_text(r["text"] or "")})).scalar()
            if rid is None:
                missing += 1
                continue
            mm = r.get("mismatch")
            await s.execute(text("""
                INSERT INTO gold_label (review_id, label, mismatch_label, source) VALUES (:id, :l, :m, 'gold')
                ON CONFLICT (review_id) DO UPDATE SET label = EXCLUDED.label, mismatch_label = EXCLUDED.mismatch_label,
                    source = 'gold', labelled_at = now()"""),
                {"id": rid, "l": label, "m": None if mm in (None, "") else mm.strip() in ("1", "true", "True")})
            saved += 1
        await s.commit()
    print(f"saved {saved} labels; {skipped_label} rows had an invalid label; {missing} texts matched no uploaded review")


if len(sys.argv) != 2:
    print(__doc__)
else:
    asyncio.run(main(sys.argv[1]))
