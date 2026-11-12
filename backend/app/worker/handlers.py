import asyncio

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Review
from app.services.queue import set_progress

CHUNK = 5


async def handle_score(job_id: int, batch_id: int) -> None:
    """PLACEHOLDER. Walks the batch's reviews in chunks and reports progress.
    Step 8 replaces this with real sentiment scoring."""
    async with SessionLocal() as s:
        ids = (
            await s.execute(select(Review.review_id).where(Review.batch_id == batch_id).order_by(Review.review_id))
        ).scalars().all()
    total = len(ids)
    if total == 0:
        raise RuntimeError("This batch has no reviews to score.")
    for i in range(0, total, CHUNK):
        await asyncio.sleep(settings.job_demo_delay)
        async with SessionLocal() as s:
            await set_progress(s, job_id, int(100 * min(i + CHUNK, total) / total))


HANDLERS = {"score": handle_score}
