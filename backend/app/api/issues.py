from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import thresholds as T
from app.db.session import get_session
from app.models import Aspect, Issue, IssuePriority, IssueReview, Workspace
from app.services.issues import what_if

router = APIRouter(tags=["issues"])


async def _ws(session: AsyncSession) -> int:
    return await session.scalar(select(func.min(Workspace.workspace_id))) or 1


@router.get("/issues")
async def list_issues(session: AsyncSession = Depends(get_session)):
    ws = await _ws(session)
    rows = (
        await session.execute(
            select(Issue.issue_id, Issue.name, Aspect.name, Issue.keywords, Issue.n_reviews,
                   IssuePriority.frequency, IssuePriority.severity, IssuePriority.growth,
                   IssuePriority.rating_gain, IssuePriority.hidden_share, IssuePriority.priority_score)
            .join(IssuePriority, IssuePriority.issue_id == Issue.issue_id)
            .join(Aspect, Aspect.aspect_id == Issue.aspect_id)
            .where(Issue.workspace_id == ws)
            .order_by(IssuePriority.priority_score.desc())
        )
    ).all()
    ev: dict[int, list] = {}
    if rows:
        quotes = (
            await session.execute(
                select(IssueReview.issue_id, IssueReview.review_id, IssueReview.evidence_span)
                .where(IssueReview.issue_id.in_([r[0] for r in rows]))
                .order_by(IssueReview.sentiment)
            )
        ).all()
        for iid, rid, span in quotes:
            if len(ev.setdefault(iid, [])) < 3:
                ev[iid].append({"review_id": rid, "quote": span})
    return {"issues": [
        {"issue_id": i, "name": n, "aspect": a, "keywords": kw, "reviews": nr, "low_sample": nr < T.LOW_SAMPLE,
         "frequency": f, "severity": s, "growth": g, "rating_gain": rg, "hidden_share": hs,
         "priority_score": ps, "evidence": ev.get(i, [])}
        for i, n, a, kw, nr, f, s, g, rg, hs, ps in rows
    ]}


@router.get("/what-if")
async def get_what_if(k: int = Query(3, ge=1, le=10), session: AsyncSession = Depends(get_session)):
    return await what_if(session, await _ws(session), k)
