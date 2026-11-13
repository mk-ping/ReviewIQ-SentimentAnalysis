import asyncio

import httpx
from sqlalchemy import and_, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.aspect_config import CATEGORIES
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import (
    Aspect, MLModel, Prediction, Review, ReviewAspect, ReviewAspectRun, UploadBatch,
)
from app.services import aspects, sentiment
from app.services.fusion import score_batch
from app.services.queue import set_progress

CHUNK = 32


async def _model_id(s) -> int:
    await s.execute(
        pg_insert(MLModel)
        .values(name=settings.sentiment_model, version="pretrained", kind="sentiment")
        .on_conflict_do_nothing(index_elements=["name", "version"])
    )
    await s.commit()
    return (
        await s.execute(select(MLModel.model_id).where(MLModel.name == settings.sentiment_model, MLModel.version == "pretrained"))
    ).scalar_one()


async def handle_score(job_id: int, batch_id: int) -> None:
    async with SessionLocal() as s:
        await set_progress(s, job_id, 0)
        mid = await _model_id(s)
        n_reviews = await s.scalar(select(func.count()).select_from(Review).where(Review.batch_id == batch_id)) or 0
        if n_reviews == 0:
            raise RuntimeError("This batch has no reviews to score.")
        pending = (
            await s.execute(
                select(Review.review_id, Review.text_clean)
                .outerjoin(Prediction, and_(Prediction.review_id == Review.review_id, Prediction.model_id == mid))
                .where(Review.batch_id == batch_id, Prediction.review_id.is_(None))
                .order_by(Review.review_id)
            )
        ).all()

    total = len(pending)
    if total:
        await asyncio.to_thread(sentiment.load)
        async with SessionLocal() as s:
            await set_progress(s, job_id, 1)
        for i in range(0, total, CHUNK):
            part = pending[i : i + CHUNK]
            results = await asyncio.to_thread(sentiment.predict, [t for _, t in part])
            rows = [
                {"review_id": rid, "model_id": mid, "p_neg": a, "p_neu": b, "p_pos": c, "expected_stars": e}
                for (rid, _), (a, b, c, e) in zip(part, results)
            ]
            async with SessionLocal() as s:
                await s.execute(pg_insert(Prediction).on_conflict_do_nothing(index_elements=["review_id", "model_id"]), rows)
                await s.commit()
                await set_progress(s, job_id, int(100 * min(i + CHUNK, total) / total))

    async with SessionLocal() as s:
        await score_batch(s, batch_id)


async def _aspect_ids(s, workspace_id: int) -> dict[str, int]:
    await s.execute(
        pg_insert(Aspect)
        .values([{"workspace_id": workspace_id, "name": n} for n in CATEGORIES])
        .on_conflict_do_nothing(index_elements=["workspace_id", "name"])
    )
    await s.commit()
    rows = (await s.execute(select(Aspect.name, Aspect.aspect_id).where(Aspect.workspace_id == workspace_id))).all()
    return {name: aid for name, aid in rows}


async def handle_aspects(job_id: int, batch_id: int) -> None:
    async with SessionLocal() as s:
        await set_progress(s, job_id, 0)
        ws = await s.scalar(select(UploadBatch.workspace_id).where(UploadBatch.batch_id == batch_id))
        ids = await _aspect_ids(s, ws)
        pending = (
            await s.execute(
                select(Review.review_id, Review.text_clean)
                .outerjoin(ReviewAspectRun, ReviewAspectRun.review_id == Review.review_id)
                .where(Review.batch_id == batch_id, ReviewAspectRun.review_id.is_(None))
                .order_by(Review.review_id)
            )
        ).all()

    total = len(pending)
    if total == 0:
        return  # every review in this batch was already analysed

    async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
        llm_ok = await aspects.llm_available(client)
        if not llm_ok:
            print(f"[aspects] LLM '{settings.llm_model}' not available at {settings.llm_url}; using the keyword fallback")
        async with SessionLocal() as s:
            await set_progress(s, job_id, 1)
        for i, (rid, text) in enumerate(pending, start=1):
            items, method = await aspects.extract(client if llm_ok else None, text)
            rows = [
                {"review_id": rid, "aspect_id": ids[it["category"]], "term": it["term"][:200],
                 "evidence_span": it["evidence_span"], "sentiment": it["sentiment"],
                 "confidence": it["confidence"], "method": method}
                for it in items
            ]
            async with SessionLocal() as s:
                if rows:
                    await s.execute(insert(ReviewAspect), rows)
                await s.execute(
                    pg_insert(ReviewAspectRun)
                    .values(review_id=rid, method=method, n_found=len(rows))
                    .on_conflict_do_nothing(index_elements=["review_id"])
                )
                await s.commit()
                await set_progress(s, job_id, int(100 * i / total))


async def handle_issues(job_id: int, batch_id: int) -> None:
    from app.services.issues import rebuild_issues

    async with SessionLocal() as s:
        ws = await s.scalar(select(UploadBatch.workspace_id).where(UploadBatch.batch_id == batch_id))
        await set_progress(s, job_id, 5)
    async with SessionLocal() as s:
        n = await rebuild_issues(s, ws)
    print(f"[issues] {n} issues built for workspace {ws}")


async def handle_embed(job_id: int, batch_id: int) -> None:
    """Embed review text for similar-review search. Idempotent: only reviews without a current embedding are processed."""
    from sqlalchemy import text as sql
    from app.core import thresholds as T
    from app.services.embeddings import embed

    async with SessionLocal() as s:
        await set_progress(s, job_id, 0)
        pending = (await s.execute(sql("""
            SELECT r.review_id, r.text_clean FROM review r
            LEFT JOIN review_embedding e ON e.review_id = r.review_id
            WHERE r.batch_id = :b AND (e.review_id IS NULL OR e.model <> :m) ORDER BY r.review_id"""),
            {"b": batch_id, "m": T.EMBED_MODEL})).all()
    total = len(pending)
    for i in range(0, total, CHUNK):
        part = pending[i : i + CHUNK]
        vectors = await asyncio.to_thread(embed, [t or "" for _, t in part])
        rows = [{"rid": rid, "m": T.EMBED_MODEL, "v": "[" + ",".join(f"{float(x):.6f}" for x in vec) + "]"}
                for (rid, _), vec in zip(part, vectors)]
        async with SessionLocal() as s:
            await s.execute(sql("""
                INSERT INTO review_embedding (review_id, model, embedding) VALUES (:rid, :m, CAST(:v AS vector))
                ON CONFLICT (review_id) DO UPDATE SET model = EXCLUDED.model, embedding = EXCLUDED.embedding, created_at = now()"""), rows)
            await s.commit()
            await set_progress(s, job_id, int(100 * min(i + CHUNK, total) / total))


HANDLERS = {"score": handle_score, "aspects": handle_aspects, "issues": handle_issues, "embed": handle_embed}
