import asyncio

from sqlalchemy import select, update

from app.db.session import SessionLocal, engine
from app.models import Review
from app.services.language import detect_language


async def main():
    async with SessionLocal() as s:
        rows = (await s.execute(select(Review.review_id, Review.text_clean, Review.extra).where(Review.language.is_(None)))).all()
        for rid, text, extra in rows:
            lang, script = detect_language(text)
            await s.execute(update(Review).where(Review.review_id == rid).values(language=lang, extra={**extra, "script": script}))
        await s.commit()
        print(f"backfilled {len(rows)} reviews")
    await engine.dispose()


asyncio.run(main())
