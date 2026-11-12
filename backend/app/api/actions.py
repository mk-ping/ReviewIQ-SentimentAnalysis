from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.action_rules import rule_for
from app.db.session import get_session
from app.models import Action, Aspect, Issue, IssuePriority, IssueReview, Workspace
from app.services.actions import impact

router = APIRouter(tags=["actions"])
Status = Literal["todo", "in_progress", "done", "dropped"]
Effort = Literal["low", "medium", "high"]


class ActionCreate(BaseModel):
    issue_id: int
    owner: str | None = None
    effort: Effort | None = None


class ActionPatch(BaseModel):
    status: Status | None = None
    owner: str | None = None
    effort: Effort | None = None
    impact_note: str | None = None
    done_at: date | None = None


async def _ws(session: AsyncSession) -> int:
    return await session.scalar(select(func.min(Workspace.workspace_id))) or 1


def _view(a: Action, aspect: str, imp: dict | None = None) -> dict:
    return {"action_id": a.action_id, "aspect": aspect, "issue": a.issue_name, "keywords": a.keywords,
            "suggested_action": a.suggested_action, "owner": a.owner, "effort": a.effort, "status": a.status,
            "done_at": a.done_at, "impact_note": a.impact_note, "impact": imp}


def _same_issue(a: Action, aspect_id: int, kws: list) -> bool:
    return a.aspect_id == aspect_id and (not kws or not a.keywords or bool({k.lower() for k in kws} & {k.lower() for k in a.keywords}))


@router.get("/recommendations")
async def recommendations(session: AsyncSession = Depends(get_session)):
    ws = await _ws(session)
    rows = (
        await session.execute(
            select(Issue.issue_id, Issue.name, Issue.aspect_id, Aspect.name, Issue.keywords, Issue.n_reviews,
                   IssuePriority.priority_score, IssuePriority.rating_gain)
            .join(IssuePriority, IssuePriority.issue_id == Issue.issue_id)
            .join(Aspect, Aspect.aspect_id == Issue.aspect_id)
            .where(Issue.workspace_id == ws)
            .order_by(IssuePriority.priority_score.desc())
        )
    ).all()
    acts = (await session.execute(select(Action).where(Action.workspace_id == ws, Action.status != "dropped"))).scalars().all()
    ev: dict[int, list] = {}
    if rows:
        quotes = (
            await session.execute(
                select(IssueReview.issue_id, IssueReview.review_id, IssueReview.evidence_span)
                .where(IssueReview.issue_id.in_([r[0] for r in rows])).order_by(IssueReview.sentiment)
            )
        ).all()
        for iid, rid, span in quotes:
            if len(ev.setdefault(iid, [])) < 3:
                ev[iid].append({"review_id": rid, "quote": span})
    out = []
    for iid, name, aid, aspect, kws, n, score, gain in rows:
        text, team = rule_for(aspect)
        existing = next((a.action_id for a in acts if _same_issue(a, aid, kws)), None)
        out.append({"issue_id": iid, "issue": name, "aspect": aspect, "reviews": n, "priority_score": score,
                    "estimated_gain": round(gain, 3), "suggested_action": text, "owner_team": team,
                    "existing_action_id": existing, "evidence": ev.get(iid, [])})
    return {"recommendations": out,
            "note": "Actions come from a fixed rule table, not free generation. Gains are estimates and overlap between issues."}


@router.post("/actions")
async def create_action(body: ActionCreate, session: AsyncSession = Depends(get_session)):
    ws = await _ws(session)
    row = (
        await session.execute(
            select(Issue.name, Issue.aspect_id, Issue.keywords, Aspect.name)
            .join(Aspect, Aspect.aspect_id == Issue.aspect_id)
            .where(Issue.issue_id == body.issue_id, Issue.workspace_id == ws)
        )
    ).first()
    if row is None:
        raise HTTPException(404, "Issue not found. Issue ids change when issues are rebuilt; call GET /recommendations for current ids.")
    name, aid, kws, aspect = row
    open_acts = (await session.execute(select(Action).where(Action.workspace_id == ws, Action.status.in_(("todo", "in_progress"))))).scalars().all()
    dup = next((a for a in open_acts if _same_issue(a, aid, kws)), None)
    if dup is not None:
        raise HTTPException(409, f"An open action for this issue already exists (action {dup.action_id}).")
    text, team = rule_for(aspect)
    a = Action(workspace_id=ws, aspect_id=aid, issue_name=name, keywords=kws, suggested_action=text,
               owner=body.owner or team, effort=body.effort)
    session.add(a)
    await session.commit()
    return _view(a, aspect)


@router.patch("/actions/{action_id}")
async def patch_action(action_id: int, body: ActionPatch, session: AsyncSession = Depends(get_session)):
    a = await session.get(Action, action_id)
    if a is None:
        raise HTTPException(404, "Action not found.")
    if body.owner is not None:
        a.owner = body.owner
    if body.effort is not None:
        a.effort = body.effort
    if body.impact_note is not None:
        a.impact_note = body.impact_note
    if body.status is not None:
        a.status = body.status
        a.done_at = (body.done_at or a.done_at or date.today()) if body.status == "done" else None
    elif body.done_at is not None and a.status == "done":
        a.done_at = body.done_at
    a.updated_at = func.now()
    await session.commit()
    aspect = await session.scalar(select(Aspect.name).where(Aspect.aspect_id == a.aspect_id))
    return _view(a, aspect, await impact(session, a.workspace_id, a))


@router.get("/actions")
async def list_actions(status: Status | None = None, session: AsyncSession = Depends(get_session)):
    ws = await _ws(session)
    q = select(Action, Aspect.name).join(Aspect, Aspect.aspect_id == Action.aspect_id).where(Action.workspace_id == ws)
    if status:
        q = q.where(Action.status == status)
    rows = (await session.execute(q.order_by(Action.action_id))).all()
    return {"actions": [_view(a, asp, await impact(session, ws, a) if a.status == "done" else None) for a, asp in rows]}
