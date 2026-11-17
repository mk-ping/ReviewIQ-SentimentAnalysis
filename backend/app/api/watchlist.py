from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dashboard import _ws
from app.core import thresholds as T
from app.core.severe_terms import PREFILTER, severe_hits
from app.db.session import get_session
from app.services.watchlist import risk, trend_word

router = APIRouter(tags=["watchlist"])

RECENT_DAYS, EARLIER_DAYS = 30, 60
BASE = "FROM review r JOIN product p ON p.product_id = r.product_id WHERE r.workspace_id = :ws AND r.spam_score <= :spam"


@router.get("/watchlist")
async def watchlist(session: AsyncSession = Depends(get_session)):
    """Every product ranked by a 0-100 risk score, with the reasons, its worst aspect and its top issue."""
    ws = await _ws(session)
    ex = session.execute
    a = {"ws": ws, "spam": T.SPAM_MAX}
    last = (await ex(text(f"SELECT max(r.review_date) {BASE}"), a)).scalar()
    if last is None:
        return {"products": [], "n_products": 0, "as_of": None, "note": "No reviews yet."}
    last = last if isinstance(last, date) else date.fromisoformat(str(last))
    recent_from, earlier_from = last - timedelta(days=RECENT_DAYS), last - timedelta(days=RECENT_DAYS + EARLIER_DAYS)
    w = dict(a, rf=recent_from, ef=earlier_from)

    base = (await ex(text(f"""
        SELECT p.product_id, p.name, count(*),
          count(*) FILTER (WHERE s.text_label = 'neg'),
          count(*) FILTER (WHERE r.review_date > :rf), count(*) FILTER (WHERE r.review_date > :rf AND s.text_label = 'neg'),
          avg(r.rating_norm) FILTER (WHERE r.review_date > :rf),
          count(*) FILTER (WHERE r.review_date > :ef AND r.review_date <= :rf),
          count(*) FILTER (WHERE r.review_date > :ef AND r.review_date <= :rf AND s.text_label = 'neg'),
          avg(r.rating_norm) FILTER (WHERE r.review_date > :ef AND r.review_date <= :rf)
        {BASE.replace('WHERE', 'JOIN review_score s ON s.review_id = r.review_id WHERE')} AND s.text_label IS NOT NULL
        GROUP BY 1, 2"""), w)).all()

    hid = {pid: (n, k) for pid, n, k in (await ex(text(f"""
        SELECT r.product_id, count(*), count(*) FILTER (WHERE EXISTS (
          SELECT 1 FROM review_aspect ra WHERE ra.review_id = r.review_id AND ra.sentiment <= :neg AND ra.confidence >= :conf))
        {BASE} AND r.rating_norm >= :stars GROUP BY 1"""), dict(a, neg=T.NEG_MENTION, conf=T.ASPECT_MIN_CONF, stars=T.HIDDEN_MIN_STARS))).all()}

    asp: dict[int, tuple[str, int]] = {}
    for pid, name, k in (await ex(text(f"""
        SELECT r.product_id, x.name, count(DISTINCT r.review_id)
        FROM review r JOIN review_aspect ra ON ra.review_id = r.review_id JOIN aspect x ON x.aspect_id = ra.aspect_id
        WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND ra.sentiment <= :neg AND ra.confidence >= :conf
        GROUP BY 1, 2 ORDER BY 3 DESC"""), dict(a, neg=T.NEG_MENTION, conf=T.ASPECT_MIN_CONF))).all():
        asp.setdefault(pid, (name, k))

    severe: dict[int, list] = {}
    for pid, rid, txt in (await ex(text(f"""
        SELECT r.product_id, r.review_id, r.text_clean {BASE} AND r.text_clean ~* :rx ORDER BY r.review_date DESC LIMIT 3000"""),
            dict(a, rx=PREFILTER))).all():
        cats = severe_hits(txt)
        if cats:
            severe.setdefault(pid, []).append({"review_id": rid, "categories": cats, "text": (txt or "")[:200]})

    top_issue = {}
    for pid, name, asp_name, score, k in (await ex(text("""
        SELECT r.product_id, i.name, x.name, coalesce(ip.priority_score, 0), count(*)
        FROM issue_review ir JOIN issue i ON i.issue_id = ir.issue_id JOIN aspect x ON x.aspect_id = i.aspect_id
        JOIN review r ON r.review_id = ir.review_id LEFT JOIN issue_priority ip ON ip.issue_id = i.issue_id
        WHERE r.workspace_id = :ws GROUP BY 1, 2, 3, 4 ORDER BY 4 DESC, 5 DESC"""), {"ws": ws})).all():
        top_issue.setdefault(pid, {"issue": name, "aspect": asp_name, "reviews": k})

    out = []
    for pid, name, n, neg, rn, rneg, ravg, en, eneg, eavg in base:
        hn, hk = hid.get(pid, (0, 0))
        asp_name, asp_k = asp.get(pid, (None, 0))
        m = {"n": n, "neg_share": neg / n if n else 0,
             "recent_n": rn, "recent_neg": rneg / rn if rn else None, "recent_avg": float(ravg) if ravg is not None else None,
             "earlier_n": en, "earlier_neg": eneg / en if en else None, "earlier_avg": float(eavg) if eavg is not None else None,
             "severe_n": len(severe.get(pid, [])), "hidden_share": hk / hn if hn >= 5 else None,
             "top_aspect": asp_name, "top_aspect_share": asp_k / n if n else 0}
        r = risk(m)
        out.append({"product_id": pid, "product": name, "n": n, "neg_share": round(m["neg_share"], 3),
                    "avg_rating_recent": round(m["recent_avg"], 2) if m["recent_avg"] is not None else None,
                    "trend": trend_word(m), "top_aspect": asp_name, "top_issue": top_issue.get(pid),
                    "severe": severe.get(pid, [])[:3], **r})
    out.sort(key=lambda d: (-d["score"], -d["n"]))
    return {"products": out, "n_products": len(out), "as_of": str(last),
            "windows": {"recent_days": RECENT_DAYS, "earlier_days": EARLIER_DAYS},
            "note": "Risk score runs 0 to 100. 60 or more is High, 35 to 59 is Watch. Each score lists the reasons behind it."}
