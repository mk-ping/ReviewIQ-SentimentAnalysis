import asyncio

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import SessionLocal
from app.models import MLModel, Prediction, Review
from app.services import sentiment
from app.services.fusion import score_batch
from app.services.queue import set_progress

CHUNK = 32


async def _model_id(s, cfg: dict) -> int:
    await s.execute(
        pg_insert(MLModel)
        .values(name=cfg["name"], version=cfg["version"], kind="sentiment")
        .on_conflict_do_nothing(index_elements=["name", "version"])
    )
    await s.commit()
    return (await s.execute(select(MLModel.model_id).where(MLModel.name == cfg["name"], MLModel.version == cfg["version"]))).scalar_one()


async def handle_score_all(job_id: int, batch_id: int) -> None:
    cfgs = sentiment.configured()
    todo = []
    async with SessionLocal() as s:
        n_reviews = await s.scalar(select(func.count()).select_from(Review).where(Review.batch_id == batch_id)) or 0
        if n_reviews == 0:
            raise RuntimeError("This batch has no reviews to score.")
        for cfg in cfgs:
            mid = await _model_id(s, cfg)
            pending = (
                await s.execute(
                    select(Review.review_id, Review.text_clean)
                    .outerjoin(Prediction, and_(Prediction.review_id == Review.review_id, Prediction.model_id == mid))
                    .where(Review.batch_id == batch_id, Prediction.review_id.is_(None))
                    .order_by(Review.review_id)
                )
            ).all()
            todo.append((cfg, mid, pending))

    total = sum(len(p) for _, _, p in todo)
    done = 0
    for idx, (cfg, mid, pending) in enumerate(todo):
        if not pending:
            continue
        try:
            await asyncio.to_thread(sentiment.get_scorer, cfg)
        except Exception as e:
            if idx == 0:
                raise  # the primary model must work
            print(f"[score] skipping {cfg['name']}: {type(e).__name__}: {str(e)[:200]}")
            continue
        for i in range(0, len(pending), CHUNK):
            part = pending[i : i + CHUNK]
            results = await asyncio.to_thread(sentiment.predict, [t for _, t in part], CHUNK, cfg["name"])
            rows = [{"review_id": rid, "model_id": mid, "p_neg": a, "p_neu": b, "p_pos": c, "expected_stars": e}
                    for (rid, _), (a, b, c, e) in zip(part, results)]
            async with SessionLocal() as s:
                await s.execute(pg_insert(Prediction).on_conflict_do_nothing(index_elements=["review_id", "model_id"]), rows)
                await s.commit()
                done += len(part)
                await set_progress(s, job_id, int(100 * done / max(total, 1)))
    async with SessionLocal() as s:
        await score_batch(s, batch_id)
