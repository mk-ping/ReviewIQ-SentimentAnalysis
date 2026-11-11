from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import thresholds as T
from app.core.config import settings
from app.models import MLModel, Prediction, Review, ReviewScore


def fuse(p_neg: float, p_neu: float, p_pos: float, expected: float | None, stars: float | None) -> dict:
    conf = max(p_neg, p_neu, p_pos)
    label = "neg" if conf == p_neg else ("neu" if conf == p_neu else "pos")
    out = {"text_label": label, "confidence": round(conf, 4), "fused_stars": None,
           "pred_stars": expected, "star_gap": None, "mismatch_type": None}
    if stars is None:
        return out
    text = p_pos - p_neg
    star_score = (stars - 3) / 2
    w = min(max(conf, T.FUSION_W_MIN), T.FUSION_W_MAX)
    out["fused_stars"] = round(3 + 2 * (w * text + (1 - w) * star_score), 3)
    if expected is not None:
        out["star_gap"] = round(expected - stars, 3)
    if conf >= T.MISMATCH_MIN_CONF and abs(text - star_score) >= T.MISMATCH_DIFF:
        out["mismatch_type"] = "underrated" if text > star_score else "overrated"
    return out


async def score_batch(session: AsyncSession, batch_id: int) -> int:
    rows = (
        await session.execute(
            select(Review.review_id, Review.rating_norm, Prediction.p_neg, Prediction.p_neu, Prediction.p_pos, Prediction.expected_stars)
            .join(Prediction, Prediction.review_id == Review.review_id)
            .join(MLModel, MLModel.model_id == Prediction.model_id)
            .where(Review.batch_id == batch_id, MLModel.name == settings.sentiment_model)
        )
    ).all()
    payload = [{"review_id": rid, **fuse(n, u, p, e, st)} for rid, st, n, u, p, e in rows]
    cols = ["text_label", "confidence", "fused_stars", "pred_stars", "star_gap", "mismatch_type"]
    for i in range(0, len(payload), 2000):
        stmt = pg_insert(ReviewScore)
        stmt = stmt.on_conflict_do_update(
            index_elements=["review_id"],
            set_={**{c: stmt.excluded[c] for c in cols}, "scored_at": func.now()},
        )
        await session.execute(stmt, payload[i : i + 2000])
    await session.commit()
    return len(payload)
