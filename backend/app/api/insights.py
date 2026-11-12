from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import thresholds as T
from app.db.session import get_session
from app.models import Aspect, Product, Review, ReviewAspect, ReviewAspectRun, ReviewScore, Workspace
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


@router.get("/aspects")
async def get_aspects(session: AsyncSession = Depends(get_session)):
    ws = await _workspace_id(session)
    rows = (
        await session.execute(
            select(
                Aspect.name,
                func.count(),
                func.count(func.distinct(ReviewAspect.review_id)),
                func.avg(ReviewAspect.sentiment),
                func.count().filter(ReviewAspect.sentiment <= T.NEG_MENTION),
                func.count().filter(ReviewAspect.sentiment >= -T.NEG_MENTION),
            )
            .select_from(ReviewAspect)
            .join(Aspect, Aspect.aspect_id == ReviewAspect.aspect_id)
            .join(Review, Review.review_id == ReviewAspect.review_id)
            .where(Review.workspace_id == ws, ReviewAspect.confidence >= T.ASPECT_MIN_CONF)
            .group_by(Aspect.name)
            .order_by(func.count().desc())
        )
    ).all()
    return {"aspects": [
        {"aspect": name, "mentions": n, "reviews": nr, "avg_sentiment": round(float(avg), 2),
         "negative": neg, "positive": pos, "neutral": n - neg - pos, "low_sample": n < T.LOW_SAMPLE}
        for name, n, nr, avg, neg, pos in rows
    ]}


# Skip wrongly starred reviews (overrated AND no positive aspect mention).
# Mixed reviews such as "great scent, but the pump broke" stay in.
NOT_OVERRATED = Review.review_id.not_in(
    select(ReviewScore.review_id).where(
        ReviewScore.mismatch_type == "overrated",
        ~exists().where(ReviewAspect.review_id == ReviewScore.review_id,
                        ReviewAspect.sentiment >= -T.NEG_MENTION),
    )
)


@router.get("/hidden-dissatisfaction")
async def get_hidden(
    limit: int = Query(50, ge=1, le=200),
    after_id: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    ws = await _workspace_id(session)
    neg = and_(
        ReviewAspect.sentiment <= T.NEG_MENTION,
        ReviewAspect.confidence >= T.ASPECT_MIN_CONF,
        ReviewAspect.evidence_span.is_not(None),
        ReviewAspect.evidence_span != "",
    )
    hidden_ids = (
        select(Review.review_id)
        .join(ReviewAspect, ReviewAspect.review_id == Review.review_id)
        .where(Review.workspace_id == ws, Review.rating_norm >= T.HIDDEN_MIN_STARS, neg, NOT_OVERRATED)
        .distinct()
    )
    hidden_total = await session.scalar(select(func.count()).select_from(hidden_ids.subquery())) or 0
    scanned = await session.scalar(
        select(func.count()).select_from(Review)
        .join(ReviewAspectRun, ReviewAspectRun.review_id == Review.review_id)
        .where(Review.workspace_id == ws, Review.rating_norm >= T.HIDDEN_MIN_STARS, NOT_OVERRATED)
    ) or 0

    blind = (
        await session.execute(
            select(Aspect.name, func.count(), func.count().filter(Review.rating_norm >= T.HIDDEN_MIN_STARS))
            .select_from(ReviewAspect)
            .join(Aspect, Aspect.aspect_id == ReviewAspect.aspect_id)
            .join(Review, Review.review_id == ReviewAspect.review_id)
            .where(Review.workspace_id == ws, Review.rating_norm.is_not(None), neg, NOT_OVERRATED)
            .group_by(Aspect.name)
        )
    ).all()
    blind_spots = sorted(
        [{"aspect": a, "negative_mentions": n, "in_4_5_star": h, "blind_spot_share": round(h / n, 2),
          "low_sample": n < T.LOW_SAMPLE} for a, n, h in blind],
        key=lambda d: (-d["blind_spot_share"], -d["negative_mentions"]),
    )

    page = (await session.execute(hidden_ids.where(Review.review_id > after_id).order_by(Review.review_id).limit(limit))).scalars().all()
    items = []
    if page:
        revs = (
            await session.execute(
                select(Review.review_id, Product.name, Review.rating_norm, Review.text_clean)
                .join(Product, Product.product_id == Review.product_id)
                .where(Review.review_id.in_(page)).order_by(Review.review_id)
            )
        ).all()
        ments = (
            await session.execute(
                select(ReviewAspect.review_id, Aspect.name, ReviewAspect.term, ReviewAspect.evidence_span, ReviewAspect.sentiment)
                .join(Aspect, Aspect.aspect_id == ReviewAspect.aspect_id)
                .where(ReviewAspect.review_id.in_(page), neg).order_by(ReviewAspect.review_id)
            )
        ).all()
        by_review: dict[int, list] = {}
        for rid, asp, term, ev, sent in ments:
            by_review.setdefault(rid, []).append({"aspect": asp, "term": term, "phrase": ev, "sentiment": sent})
        items = [{"review_id": rid, "product": name, "stars": st, "text": tx, "negative_mentions": by_review.get(rid, [])}
                 for rid, name, st, tx in revs]

    return {
        "hidden_reviews": hidden_total,
        "rated_4plus_analysed": scanned,
        "hidden_rate": round(hidden_total / scanned, 3) if scanned else None,
        "low_sample": scanned < T.LOW_SAMPLE,
        "blind_spots": blind_spots,
        "items": items,
        "next_after_id": items[-1]["review_id"] if len(items) == limit else None,
    }
