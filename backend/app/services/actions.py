from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import thresholds as T
from app.models import Action, ReviewAspect
from app.services.issues import analysed_reviews


def share_change(hit: set, before: list, after: list) -> dict:
    """Share of reviews mentioning the issue before and after the completion date."""
    nb, na = len(before), len(after)
    if nb == 0 or na == 0:
        return {"available": False, "reviews_before": nb, "reviews_after": na,
                "reason": "Needs dated reviews on both sides of the completion date."}
    sb = sum(1 for r in before if r in hit) / nb
    sa = sum(1 for r in after if r in hit) / na
    return {"available": True, "reviews_before": nb, "reviews_after": na,
            "share_before": round(sb, 3), "share_after": round(sa, 3), "change": round(sa - sb, 3),
            "low_sample": min(nb, na) < T.LOW_SAMPLE,
            "note": "Shows association, not proof that the action caused the change."}


async def impact(session: AsyncSession, ws: int, a: Action) -> dict:
    if a.status != "done" or a.done_at is None:
        return {"available": False, "reason": "The action is not done yet."}
    pop = await analysed_reviews(session, ws)
    dated = {rid: d for rid, _, d in pop if d is not None}
    kws = {k.lower() for k in (a.keywords or [])}
    rows = (
        await session.execute(
            select(ReviewAspect.review_id, ReviewAspect.term).where(
                ReviewAspect.aspect_id == a.aspect_id,
                ReviewAspect.sentiment <= T.NEG_MENTION,
                ReviewAspect.confidence >= T.ASPECT_MIN_CONF,
                ReviewAspect.evidence_span.is_not(None),
            )
        )
    ).all()
    hit = {rid for rid, term in rows if not kws or (term and term.lower() in kws)}
    before = [rid for rid, d in dated.items() if d <= a.done_at]
    after = [rid for rid, d in dated.items() if d > a.done_at]
    return share_change(hit, before, after)
