from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import thresholds as T
from app.db.session import get_session
from app.models import UploadBatch

try:
    from app.core.action_rules import rule_for
except ImportError:  # Step 12 not applied
    rule_for = None

router = APIRouter(tags=["results"])


def _f(x, nd=2):
    return None if x is None else round(float(x), nd)


async def _has(session: AsyncSession, name: str) -> bool:
    return bool(await session.scalar(text("SELECT to_regclass(:n) IS NOT NULL"), {"n": f"public.{name}"}))


@router.get("/uploads/{batch_id}/results")
async def batch_results(batch_id: int, session: AsyncSession = Depends(get_session)):
    batch = await session.get(UploadBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "Upload not found.")
    a = {"b": batch_id, "neg": T.NEG_MENTION, "pos": -T.NEG_MENTION, "conf": T.ASPECT_MIN_CONF,
         "hid": T.HIDDEN_MIN_STARS, "spam": T.SPAM_MAX}
    has_emb = await _has(session, "review_embedding")
    emb_join = "LEFT JOIN review_embedding e ON e.review_id = r.review_id" if has_emb else ""
    emb_col = "count(e.review_id)" if has_emb else "0"

    k = (await session.execute(text(f"""
        SELECT count(*) AS n, count(r.rating_norm) AS rated, avg(r.rating_norm) AS avg_rating,
               count(s.review_id) AS scored,
               avg(s.fused_stars) FILTER (WHERE r.rating_norm IS NOT NULL) AS avg_fused,
               count(*) FILTER (WHERE s.text_label = 'pos') AS pos,
               count(*) FILTER (WHERE s.text_label = 'neg') AS neg,
               count(*) FILTER (WHERE s.mismatch_type IS NOT NULL) AS mismatches,
               count(*) FILTER (WHERE r.spam_score > :spam) AS spam,
               count(u.review_id) AS aspects_done, {emb_col} AS embedded
        FROM review r
        LEFT JOIN review_score s ON s.review_id = r.review_id
        LEFT JOIN review_aspect_run u ON u.review_id = r.review_id
        {emb_join}
        WHERE r.batch_id = :b"""), a)).mappings().one()

    hist = (await session.execute(text("""
        SELECT round(rating_norm::numeric)::int AS stars, count(*) FROM review
        WHERE batch_id = :b AND rating_norm IS NOT NULL GROUP BY 1 ORDER BY 1"""), a)).all()
    counts = {s: c for s, c in hist}

    mm = (await session.execute(text("""
        SELECT r.review_id, r.rating_norm, s.fused_stars, s.star_gap, s.mismatch_type, r.text_clean
        FROM review r JOIN review_score s ON s.review_id = r.review_id
        WHERE r.batch_id = :b AND s.mismatch_type IS NOT NULL
        ORDER BY abs(s.star_gap) DESC NULLS LAST LIMIT 8"""), a)).all()

    asp = (await session.execute(text("""
        SELECT a.name, count(*), avg(ra.sentiment),
               count(*) FILTER (WHERE ra.sentiment <= :neg), count(*) FILTER (WHERE ra.sentiment >= :pos)
        FROM review_aspect ra JOIN aspect a ON a.aspect_id = ra.aspect_id JOIN review r ON r.review_id = ra.review_id
        WHERE r.batch_id = :b AND ra.confidence >= :conf GROUP BY a.name ORDER BY count(*) DESC"""), a)).all()

    neg_ok = "ra.sentiment <= :neg AND ra.confidence >= :conf AND ra.evidence_span IS NOT NULL AND ra.evidence_span <> ''"
    hidden_n = await session.scalar(text(f"""
        SELECT count(DISTINCT r.review_id) FROM review r JOIN review_aspect ra ON ra.review_id = r.review_id
        WHERE r.batch_id = :b AND r.rating_norm >= :hid AND {neg_ok}"""), a) or 0
    scanned = await session.scalar(text("""
        SELECT count(*) FROM review r JOIN review_aspect_run u ON u.review_id = r.review_id
        WHERE r.batch_id = :b AND r.rating_norm >= :hid"""), a) or 0
    hid_rows = (await session.execute(text(f"""
        SELECT r.review_id, r.rating_norm, r.text_clean, ra.evidence_span, a.name
        FROM review r JOIN review_aspect ra ON ra.review_id = r.review_id JOIN aspect a ON a.aspect_id = ra.aspect_id
        WHERE r.batch_id = :b AND r.rating_norm >= :hid AND {neg_ok} ORDER BY r.review_id LIMIT 6"""), a)).all()

    issues = []
    if await _has(session, "issue") and await _has(session, "issue_priority"):
        rows = (await session.execute(text("""
            SELECT i.name, a.name, i.n_reviews, p.priority_score, p.hidden_share
            FROM issue i JOIN issue_priority p ON p.issue_id = i.issue_id JOIN aspect a ON a.aspect_id = i.aspect_id
            WHERE i.workspace_id = :ws ORDER BY p.priority_score DESC LIMIT 5"""), {"ws": batch.workspace_id})).all()
        for name, asp_name, n_rev, score, hs in rows:
            act = rule_for(asp_name) if rule_for else None
            issues.append({"issue": name, "aspect": asp_name, "reviews": n_rev, "priority_score": score,
                           "hidden_share": _f(hs, 3), "suggested_action": act[0] if act else None,
                           "owner_team": act[1] if act else None})

    n, scored = k["n"], k["scored"]
    return {
        "batch_id": batch_id, "file_name": batch.file_name, "status": batch.status,
        "reviews": n, "rated_reviews": k["rated"], "scored_reviews": scored, "possible_spam": k["spam"],
        "low_sample": n < T.LOW_SAMPLE,
        "average_rating": _f(k["avg_rating"]), "text_adjusted_average": _f(k["avg_fused"]),
        "net_sentiment": _f((k["pos"] - k["neg"]) / scored) if scored else None,
        "percent_negative": _f(100 * k["neg"] / scored, 1) if scored else None,
        "mismatches": k["mismatches"],
        "histogram": [{"stars": s, "count": counts.get(s, 0)} for s in range(1, 6)],
        "stages": {"score": {"done": scored, "total": n}, "aspects": {"done": k["aspects_done"], "total": n},
                   "embed": {"done": k["embedded"], "total": n}, "issues": {"done": len(issues), "total": None}},
        "top_mismatches": [{"review_id": i, "stars": st, "text_stars": _f(fs), "star_gap": _f(sg), "type": mt, "text": tx}
                           for i, st, fs, sg, mt, tx in mm],
        "aspects": [{"aspect": nm, "mentions": c, "avg_sentiment": _f(av), "negative": ng, "positive": ps,
                     "low_sample": c < T.LOW_SAMPLE} for nm, c, av, ng, ps in asp],
        "hidden": {"reviews": hidden_n, "rated_4plus_analysed": scanned,
                   "rate": _f(hidden_n / scanned, 3) if scanned else None,
                   "examples": [{"review_id": i, "stars": st, "text": tx, "phrase": ev, "aspect": an}
                                for i, st, tx, ev, an in hid_rows]},
        "issues": issues,
        "notes": ["The text-adjusted average is not smoothed. GET /true-rating gives the smoothed version with an interval.",
                  "Issues cover the whole workspace, not only this upload.",
                  "Aspect results come from a local language model and are not yet measured against hand labels."],
    }
