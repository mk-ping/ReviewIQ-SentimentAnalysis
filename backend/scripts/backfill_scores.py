import asyncio

from sqlalchemy import select

from app.db.session import SessionLocal, engine
from app.models import Review
from app.services.fusion import score_batch


async def main():
    async with SessionLocal() as s:
        ids = (await s.execute(select(Review.batch_id).distinct().order_by(Review.batch_id))).scalars().all()
        for b in ids:
            n = await score_batch(s, b)
            print(f"batch {b}: {n} scored")
    await engine.dispose()


asyncio.run(main())
