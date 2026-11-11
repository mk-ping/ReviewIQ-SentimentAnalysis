import asyncio

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models import Review
from app.services.queue import set_progress

CHUNK = 2  # tiny on purpose so progress is visible on small test files


async def handle_score(job_id: int, batch_id: int) -> None:
    """Placeholder. Step 8 replaces the loop body with real sentiment scoring."""
    async with SessionLocal() as s:
        total = await s.scalar(select(func.count()).select_from(Review).where(Review.batch_id == batch_id)) or 0
    done = 0
    while done < total:
        await asyncio.sleep(0.7)
        done = min(total, done + CHUNK)
        async with SessionLocal() as s:
            await set_progress(s, job_id, int(100 * done / max(total, 1)))


HANDLERS = {"score": handle_score}
