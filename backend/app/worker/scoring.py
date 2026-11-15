import asyncio

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core import thresholds as T
from app.db.session import SessionLocal
from app.models import MLModel, Prediction, Review
from app.services import sentiment
from app.services.fusion import score_batch
from app.services.queue import set_progress
from app.services.routing import MEMBERS, group_of

CHUNK = 32


async def _model_id(s, cfg: dict) -> int:
    await s.execute(
        pg_insert(MLModel).values(name=cfg["name"], version=cfg["version"], kind=cfg["kind"])
        .on_conflict_do_nothing(index_elements=["name", "version"])
    )
    await s.commit()
    return (await s.execute(select(MLModel.model_id).where(MLModel.name == cfg["name"], MLModel.version == cfg["version"]))).scalar_one()


async def handle_score_all(job_id: int, batch_id: int) -> None:
    reg = sentiment.registry()
    todo = []
    async with SessionLocal() as s:
        revs = (await s.execute(select(Review.review_id, Review.text_clean, Review.language)
                                .where(Review.batch_id == batch_id, Review.spam_score <= T.SPAM_MAX).order_by(Review.review_id))).all()
        if not revs:
            raise RuntimeError("This batch has no reviews to score.")
        for key, cfg in reg.items():
            if not sentiment.available(key):
                continue
            mid = await _model_id(s, cfg)
            have = set((await s.execute(
                select(Prediction.review_id).join(Review, Review.review_id == Prediction.review_id)
                .where(Review.batch_id == batch_id, Prediction.model_id == mid))).scalars().all())
            pending = [(rid, t) for rid, t, lang in revs if key in MEMBERS[group_of(lang)] and rid not in have]
            if pending:
                todo.append((key, mid, pending))

    total = sum(len(p) for _, _, p in todo)
    done = ran = 0
    for key, mid, pending in todo:
        try:
            await asyncio.to_thread(sentiment.get_scorer, key)
        except Exception as e:
            print(f"[score] skipping {key}: {type(e).__name__}: {str(e)[:200]}")
            continue
        ran += 1
        for i in range(0, len(pending), CHUNK):
            part = pending[i : i + CHUNK]
            results = await asyncio.to_thread(sentiment.predict, [t for _, t in part], CHUNK, key)
            rows = [{"review_id": rid, "model_id": mid, "p_neg": a, "p_neu": b, "p_pos": c, "expected_stars": e}
                    for (rid, _), (a, b, c, e) in zip(part, results)]
            async with SessionLocal() as s:
                await s.execute(pg_insert(Prediction).on_conflict_do_nothing(index_elements=["review_id", "model_id"]), rows)
                await s.commit()
                done += len(part)
                await set_progress(s, job_id, int(100 * done / max(total, 1)))
    if todo and ran == 0:
        raise RuntimeError("No sentiment model could be loaded.")
    async with SessionLocal() as s:
        await score_batch(s, batch_id)
