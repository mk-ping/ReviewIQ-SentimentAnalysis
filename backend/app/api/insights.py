from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Product, Review, ReviewScore, Workspace
from app.services.true_rating import true_rating

router = APIRouter(tags=["insights"])


async def _workspace_id(session: AsyncSession) -> int:
    ws = await session.scalar(select(func.min(Workspace.workspace_id)))
    return ws or 1


@router.get("/true-rating")
async def get_true_rating(session: AsyncSession = Depends(get_session)):
    return {"products": await true_rating(session, await _workspace_id(session))}


@router.get("/mismatches")
async def get_mismatches(
    kind: str | None = Query(None, pattern="^(underrated|overrated|sarcasm)$"),
    limit: int = Query(50, ge=1, le=200),
    after_id: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    ws = await _workspace_id(session)
    base = (
        select(Review.review_id, Product.name, Review.rating_norm, ReviewScore.fused_stars, ReviewScore.pred_stars,
               ReviewScore.star_gap, ReviewScore.mismatch_type, ReviewScore.confidence, Review.text_clean)
        .join(Review, Review.review_id == ReviewScore.review_id)
        .join(Product, Product.product_id == Review.product_id)
        .where(Review.workspace_id == ws, ReviewScore.mismatch_type.is_not(None))
    )
    if kind:
        base = base.where(ReviewScore.mismatch_type == kind)
    total = await session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = (await session.execute(base.where(Review.review_id > after_id).order_by(Review.review_id).limit(limit))).all()
    items = [
        {"review_id": rid, "product": name, "stars": st, "fused_stars": fs, "predicted_stars": ps,
         "star_gap": sg, "type": mt, "confidence": cf, "text": tx}
        for rid, name, st, fs, ps, sg, mt, cf, tx in rows
    ]
    return {"total": total, "items": items, "next_after_id": items[-1]["review_id"] if len(items) == limit else None}
