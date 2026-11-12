import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, get_session
from app.models import Review, ReviewAspect, ReviewAspectRun, ScoringJob, UploadBatch
from app.services.queue import enqueue

router = APIRouter(tags=["jobs"])


def _snap(j: ScoringJob) -> dict:
    return {"job_id": j.job_id, "batch_id": j.batch_id, "stage": j.stage, "status": j.status,
            "progress": j.progress, "attempts": j.attempts, "error": j.error}


async def _ready_batch(session: AsyncSession, batch_id: int) -> UploadBatch:
    batch = await session.get(UploadBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "Upload not found.")
    if batch.status != "done":
        raise HTTPException(409, f"This upload is '{batch.status}'. Confirm its column mapping first (PUT /uploads/{batch_id}/mapping).")
    n = await session.scalar(select(func.count()).select_from(Review).where(Review.batch_id == batch_id)) or 0
    if n == 0:
        raise HTTPException(409, "This upload has no reviews to score. Its rows were rejected or already exist from an earlier upload (see GET /uploads/{id}/report).")
    return batch


@router.post("/uploads/{batch_id}/score")
async def start_scoring(batch_id: int, session: AsyncSession = Depends(get_session)):
    await _ready_batch(session, batch_id)
    job_id, created = await enqueue(session, batch_id, "score")
    return {"job_id": job_id, "created": created, "events": f"/jobs/{job_id}/events"}


@router.post("/uploads/{batch_id}/aspects")
async def start_aspects(batch_id: int, redo_fallback: bool = False, session: AsyncSession = Depends(get_session)):
    await _ready_batch(session, batch_id)
    if redo_fallback:
        kw = (
            select(ReviewAspectRun.review_id)
            .join(Review, Review.review_id == ReviewAspectRun.review_id)
            .where(Review.batch_id == batch_id, ReviewAspectRun.method == "keyword")
        )
        await session.execute(delete(ReviewAspect).where(ReviewAspect.review_id.in_(kw)))
        await session.execute(delete(ReviewAspectRun).where(ReviewAspectRun.review_id.in_(kw)))
        await session.commit()
    job_id, created = await enqueue(session, batch_id, "aspects")
    return {"job_id": job_id, "created": created, "events": f"/jobs/{job_id}/events"}


@router.post("/uploads/{batch_id}/issues")
async def start_issues(batch_id: int, session: AsyncSession = Depends(get_session)):
    await _ready_batch(session, batch_id)
    job_id, created = await enqueue(session, batch_id, "issues")
    return {"job_id": job_id, "created": created, "events": f"/jobs/{job_id}/events"}


@router.get("/jobs/{job_id}")
async def get_job(job_id: int, session: AsyncSession = Depends(get_session)):
    job = await session.get(ScoringJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found.")
    return _snap(job)


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: int):
    async with SessionLocal() as s:
        if await s.get(ScoringJob, job_id) is None:
            raise HTTPException(404, "Job not found.")

    async def stream():
        last = None
        while True:
            async with SessionLocal() as s:
                job = await s.get(ScoringJob, job_id)
            if job is None:
                return
            snap = _snap(job)
            if snap != last:
                yield f"data: {json.dumps(snap)}\n\n"
                last = snap
            else:
                yield ": keep-alive\n\n"
            if job.status in ("done", "failed"):
                return
            await asyncio.sleep(1)

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
