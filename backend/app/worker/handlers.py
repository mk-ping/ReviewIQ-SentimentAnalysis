import asyncio

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import MLModel, Prediction, Review
from app.services import sentiment
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
        mid = await _model_id(s)
        pending = (
            await s.execute(
                select(Review.review_id, Review.text_clean)
                .outerjoin(Prediction, and_(Prediction.review_id == Review.review_id, Prediction.model_id == mid))
                .where(Review.batch_id == batch_id, Prediction.review_id.is_(None))
                .order_by(Review.review_id)
            )
        ).all()

    total = len(pending)
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


HANDLERS = {"score": handle_score}
