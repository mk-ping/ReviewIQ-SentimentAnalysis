import asyncio
from collections import Counter

from sqlalchemy import and_, delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import thresholds as T
from app.models import Aspect, Issue, IssuePriority, IssueReview, Review, ReviewAspect, ReviewAspectRun
from app.services.embeddings import embed


def cluster(texts: list[str]) -> list[int]:
    if len(texts) < 2:
        return [0] * len(texts)
    from sklearn.cluster import AgglomerativeClustering

    labels = AgglomerativeClustering(
        n_clusters=None, distance_threshold=T.ISSUE_DISTANCE, metric="cosine", linkage="average"
    ).fit_predict(embed(texts))
    return [int(x) for x in labels]


def lift(rated: dict[int, float], ids: set[int]):
    """Lift rated reviews in ids to the mean of the others, never lowering one.
    Returns (old_avg, new_avg, n_lifted) or None when nothing is rated."""
    if not rated:
        return None
    old = sum(rated.values()) / len(rated)
    others = [r for i, r in rated.items() if i not in ids]
    if not others:
        return old, old, 0
    m = sum(others) / len(others)
    new = sum(max(r, m) if i in ids else r for i, r in rated.items()) / len(rated)
    return old, new, sum(1 for i, r in rated.items() if i in ids and r < m)


def _growth(ids, dates, median, total_late, total_early) -> float:
    if median is None:
        return 1.0
    late = sum(1 for i in ids if i in dates and dates[i] > median)
    early = sum(1 for i in ids if i in dates and dates[i] <= median)
    g = ((late + 1) / (total_late + 2)) / ((early + 1) / (total_early + 2))
    return min(max(g, T.GROWTH_MIN), T.GROWTH_MAX)


async def analysed_reviews(session: AsyncSession, ws: int):
    """Non-spam reviews that went through aspect extraction: (review_id, rating_norm, review_date)."""
    return (
        await session.execute(
            select(Review.review_id, Review.rating_norm, Review.review_date)
            .join(ReviewAspectRun, ReviewAspectRun.review_id == Review.review_id)
            .where(Review.workspace_id == ws, Review.spam_score <= T.SPAM_MAX)
        )
    ).all()


async def rebuild_issues(session: AsyncSession, ws: int) -> int:
    neg = and_(
        ReviewAspect.sentiment <= T.NEG_MENTION, ReviewAspect.confidence >= T.ASPECT_MIN_CONF,
        ReviewAspect.evidence_span.is_not(None), ReviewAspect.evidence_span != "",
    )
    mentions = (
        await session.execute(
            select(ReviewAspect.review_id, ReviewAspect.aspect_id, ReviewAspect.term,
                   ReviewAspect.evidence_span, ReviewAspect.sentiment)
            .join(Review, Review.review_id == ReviewAspect.review_id)
            .where(Review.workspace_id == ws, Review.spam_score <= T.SPAM_MAX, neg)
            .order_by(ReviewAspect.review_id)
        )
    ).all()

    pop = await analysed_reviews(session, ws)
    total = len(pop)
    rated = {rid: float(r) for rid, r, _ in pop if r is not None}
    dates = {rid: d for rid, _, d in pop if d is not None}
    ordered = sorted(dates.values())
    median = ordered[len(ordered) // 2] if ordered else None
    total_late = sum(1 for d in dates.values() if median is not None and d > median)
    total_early = len(dates) - total_late

    by_aspect: dict[int, list] = {}
    for m in mentions:
        by_aspect.setdefault(m[1], []).append(m)

    found = []
    for aid, ms in by_aspect.items():
        labels = await asyncio.to_thread(cluster, [m[3] for m in ms])
        groups: dict[int, list] = {}
        for lab, m in zip(labels, ms):
            groups.setdefault(lab, []).append(m)
        for g in groups.values():
            best: dict[int, tuple] = {}
            for m in g:  # one mention per review: keep the most negative
                if m[0] not in best or m[4] < best[m[0]][4]:
                    best[m[0]] = m
            if len(best) >= T.ISSUE_MIN_REVIEWS:
                found.append((aid, list(best.values())))

    await session.execute(delete(Issue).where(Issue.workspace_id == ws))
    if not found or total == 0:
        await session.commit()
        return 0

    names = {aid: name for aid, name in
             ((a, n) for a, n in (await session.execute(select(Aspect.aspect_id, Aspect.name).where(Aspect.workspace_id == ws))).all())}

    built = []
    for aid, ms in found:
        ids = {m[0] for m in ms}
        kw = [t for t, _ in Counter(m[2].lower() for m in ms if m[2]).most_common(3)]
        label = f"{names[aid]}: {', '.join(kw[:2])}" if kw else names[aid]
        obj = Issue(workspace_id=ws, aspect_id=aid, name=label[:200], keywords=kw, n_reviews=len(ids))
        session.add(obj)
        res = lift(rated, ids)
        gain = (res[1] - res[0]) if res else 0.0
        issue_rated = [rated[i] for i in ids if i in rated]
        hidden = (sum(1 for r in issue_rated if r >= T.HIDDEN_MIN_STARS) / len(issue_rated)) if issue_rated else None
        severity = min(max(sum(-m[4] for m in ms) / len(ms), 0.0), 1.0)
        freq = len(ids) / total
        g = _growth(ids, dates, median, total_late, total_early)
        raw = freq * severity * g * max(gain, T.GAIN_FLOOR)
        built.append((obj, ms, freq, severity, g, gain, hidden, raw))
    await session.flush()

    top = max(b[7] for b in built) or 1.0
    await session.execute(insert(IssueReview), [
        {"issue_id": obj.issue_id, "review_id": m[0], "evidence_span": m[3], "sentiment": m[4]}
        for obj, ms, *_ in built for m in ms
    ])
    await session.execute(insert(IssuePriority), [
        {"issue_id": obj.issue_id, "frequency": round(freq, 4), "severity": round(sev, 3), "growth": round(g, 3),
         "rating_gain": round(gain, 4), "hidden_share": None if hid is None else round(hid, 3),
         "priority_score": round(100 * raw / top, 1)}
        for obj, ms, freq, sev, g, gain, hid, raw in built
    ])
    await session.commit()
    return len(built)


async def what_if(session: AsyncSession, ws: int, k: int) -> dict:
    top = (
        await session.execute(
            select(Issue.issue_id, Issue.name)
            .join(IssuePriority, IssuePriority.issue_id == Issue.issue_id)
            .where(Issue.workspace_id == ws)
            .order_by(IssuePriority.priority_score.desc())
            .limit(k)
        )
    ).all()
    ids: set[int] = set()
    if top:
        ids = set((await session.execute(select(IssueReview.review_id).where(IssueReview.issue_id.in_([t[0] for t in top])))).scalars().all())
    pop = await analysed_reviews(session, ws)
    rated = {rid: float(r) for rid, r, _ in pop if r is not None}
    res = lift(rated, ids)
    return {
        "issues": [t[1] for t in top],
        "reviews_affected": len(ids),
        "rated_reviews": len(rated),
        "current_avg": round(res[0], 2) if res else None,
        "estimated_avg": round(res[1], 2) if res else None,
        "estimated_gain": round(res[1] - res[0], 2) if res else None,
        "low_sample": len(rated) < T.LOW_SAMPLE,
        "assumption": "Estimate, not a prediction: reviews that mention these issues are lifted to the average "
                      "of the reviews that do not, and no review is lowered. Each review is counted once.",
    }
