from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ScoringJob

STALE_AFTER = timedelta(minutes=5)
MAX_ATTEMPTS = 3
ACTIVE = ("queued", "running")


async def enqueue(session: AsyncSession, batch_id: int, stage: str = "score") -> tuple[int, bool]:
    """Returns (job_id, created). If an active job exists for this batch and stage, returns it."""
    active = (
        await session.execute(
            select(ScoringJob.job_id).where(
                ScoringJob.batch_id == batch_id, ScoringJob.stage == stage, ScoringJob.status.in_(ACTIVE)
            )
        )
    ).scalar_one_or_none()
    if active is not None:
        return active, False
    job = ScoringJob(batch_id=batch_id, stage=stage)
    session.add(job)
    try:
        await session.commit()
    except IntegrityError:  # two requests raced; the unique index let only one win
        await session.rollback()
        active = (
            await session.execute(
                select(ScoringJob.job_id).where(
                    ScoringJob.batch_id == batch_id, ScoringJob.stage == stage, ScoringJob.status.in_(ACTIVE)
                )
            )
        ).scalar_one()
        return active, False
    return job.job_id, True


async def claim_next(session: AsyncSession):
    """Atomically claim the oldest queued job. Returns (job_id, batch_id, stage) or None.
    FOR UPDATE SKIP LOCKED means two workers never take the same row and never wait on each other."""
    job = (
        await session.execute(
            select(ScoringJob)
            .where(ScoringJob.status == "queued")
            .order_by(ScoringJob.job_id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
    ).scalar_one_or_none()
    if job is None:
        await session.rollback()
        return None
    claimed = (job.job_id, job.batch_id, job.stage)
    job.status = "running"
    job.attempts = job.attempts + 1
    job.started_at = func.now()
    job.heartbeat_at = func.now()
    await session.commit()
    return claimed


async def requeue_stale(session: AsyncSession) -> None:
    """A running job whose heartbeat stopped belongs to a dead worker: retry it, or fail it after 3 attempts."""
    cutoff = func.now() - STALE_AFTER
    await session.execute(
        update(ScoringJob)
        .where(ScoringJob.status == "running", ScoringJob.heartbeat_at < cutoff, ScoringJob.attempts >= MAX_ATTEMPTS)
        .values(status="failed", error="Worker stopped repeatedly", finished_at=func.now())
    )
    await session.execute(
        update(ScoringJob)
        .where(ScoringJob.status == "running", ScoringJob.heartbeat_at < cutoff)
        .values(status="queued")
    )
    await session.commit()


async def set_progress(session: AsyncSession, job_id: int, pct: int) -> None:
    await session.execute(
        update(ScoringJob).where(ScoringJob.job_id == job_id).values(progress=max(0, min(100, pct)), heartbeat_at=func.now())
    )
    await session.commit()


async def finish(session: AsyncSession, job_id: int) -> None:
    await session.execute(
        update(ScoringJob).where(ScoringJob.job_id == job_id).values(status="done", progress=100, finished_at=func.now(), error=None)
    )
    await session.commit()


async def fail(session: AsyncSession, job_id: int, message: str) -> None:
    await session.rollback()
    await session.execute(
        update(ScoringJob).where(ScoringJob.job_id == job_id).values(status="failed", error=message[:1000], finished_at=func.now())
    )
    await session.commit()
