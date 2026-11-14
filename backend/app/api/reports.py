import io
from datetime import date
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from openpyxl import Workbook
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dashboard import _ws, distribution, summary
from app.core import thresholds as T
from app.core.action_rules import rule_for
from app.db.session import get_session
from app.services.true_rating import true_rating

router = APIRouter(prefix="/reports", tags=["reports"])
MAX_ROWS = 50000


def _safe(v):
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        return "'" + v
    return v


async def _issues(session: AsyncSession, ws: int):
    return (await session.execute(text("""
        SELECT i.name, a.name, i.n_reviews, ip.priority_score, ip.severity, ip.hidden_share
        FROM issue i JOIN issue_priority ip ON ip.issue_id = i.issue_id JOIN aspect a ON a.aspect_id = i.aspect_id
        WHERE i.workspace_id = :ws ORDER BY ip.priority_score DESC"""), {"ws": ws})).all()


@router.get("/export.xlsx")
async def export_xlsx(session: AsyncSession = Depends(get_session)):
    ws_id = await _ws(session)
    s = await summary(None, None, None, session)
    wb = Workbook()
    sh = wb.active
    sh.title = "Summary"
    for k, v in [("Generated", date.today().isoformat()), ("Reviews", s["reviews"]), ("Rated reviews", s["rated_reviews"]),
                 ("Average rating", s["average_rating"]), ("Weighted rating", s["weighted_rating"]),
                 ("Net sentiment", s["net_sentiment"]), ("Percent negative", s["percent_negative"]),
                 ("Mismatch rate", s["mismatch_rate"]),
                 ("Note", "Estimates. Thresholds are starting values until tuned on the gold set.")]:
        sh.append([k, v])

    sh = wb.create_sheet("Issues")
    sh.append(["Issue", "Aspect", "Reviews", "Priority (top = 100)", "Severity", "Hidden share", "Suggested action", "Owner team"])
    for name, asp, n, score, sev, hid in await _issues(session, ws_id):
        act, team = rule_for(asp)
        sh.append([_safe(name), asp, n, score, sev, hid, act, team])

    sh = wb.create_sheet("Aspects")
    sh.append(["Aspect", "Mentions", "Average sentiment", "Negative", "Positive"])
    for row in (await session.execute(text("""
        SELECT a.name, count(*), avg(ra.sentiment), count(*) FILTER (WHERE ra.sentiment <= :neg),
               count(*) FILTER (WHERE ra.sentiment >= :pos)
        FROM review_aspect ra JOIN aspect a ON a.aspect_id = ra.aspect_id JOIN review r ON r.review_id = ra.review_id
        WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND ra.confidence >= :conf GROUP BY a.name ORDER BY count(*) DESC"""),
        {"ws": ws_id, "neg": T.NEG_MENTION, "pos": -T.NEG_MENTION, "spam": T.SPAM_MAX, "conf": T.ASPECT_MIN_CONF})).all():
        sh.append([row[0], row[1], None if row[2] is None else round(float(row[2]), 2), row[3], row[4]])

    sh = wb.create_sheet("Reviews")
    sh.append(["review_id", "product", "stars", "date", "language", "spam_score", "text_label", "fused_stars", "mismatch", "text"])
    for r in (await session.execute(text("""
        SELECT r.review_id, p.name, r.rating_norm, r.review_date, r.language, r.spam_score,
               s.text_label, s.fused_stars, s.mismatch_type, r.text_clean
        FROM review r JOIN product p ON p.product_id = r.product_id LEFT JOIN review_score s ON s.review_id = r.review_id
        WHERE r.workspace_id = :ws ORDER BY r.review_id LIMIT :lim"""), {"ws": ws_id, "lim": MAX_ROWS})).all():
        sh.append([_safe(v) if isinstance(v, str) else v for v in r])

    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=reviewiq_report.xlsx"})


@router.get("/summary.pdf")
async def summary_pdf(session: AsyncSession = Depends(get_session)):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ws_id = await _ws(session)
    s = await summary(None, None, None, session)
    d = await distribution(None, None, None, session)
    tr = await true_rating(session, ws_id)
    issues = (await _issues(session, ws_id))[:5]
    st = getSampleStyleSheet()
    f = lambda x: "n/a" if x is None else f"{x:.2f}"
    P = lambda t, style="BodyText": Paragraph(escape(t), st[style])

    story = [P("ReviewIQ report", "Title"), P(f"Generated {date.today().isoformat()}"), Spacer(1, 10)]
    story.append(P(f"{s['reviews']} reviews. Customers are {d['audience'] or 'not yet rated'}."
                   + (f" Stars and text disagree on {s['mismatch_rate'] * 100:.0f}% of scored reviews." if s["mismatch_rate"] is not None else "")))
    if s["low_sample"]:
        story.append(P("Warning: fewer than 30 reviews, so treat these numbers as a first look."))
    story.append(Spacer(1, 8))
    kpi = [["Average rating", "Weighted rating", "Net sentiment", "Negative"],
           [f(s["average_rating"]), f(s["weighted_rating"]), f(s["net_sentiment"]),
            "n/a" if s["percent_negative"] is None else f"{s['percent_negative']}%"]]
    t = Table(kpi)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke)]))
    story += [t, Spacer(1, 12), P("What to fix first", "Heading2")]
    if issues:
        for name, asp, n, score, sev, hid in issues:
            act, team = rule_for(asp)
            story.append(P(f"{name}: {n} reviews, priority {score:.0f}. Suggested: {act} (team: {team})."))
    else:
        story.append(P("No issues built yet."))
    story += [Spacer(1, 12), P("True Rating: shown versus what the text supports", "Heading2")]
    rows = [["Product", "Reviews", "Shown", "True", "Verdict"]]
    for p in tr:
        rows.append([p["product"][:30], p["n"], f(p["shown_avg"]), f(p["true_rating"]),
                     "clear difference" if p["clear_difference"] else "too few reviews" if p["low_sample"] else "no clear difference"])
    t = Table(rows)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke)]))
    story += [t, Spacer(1, 12),
              P("These figures are estimates from one sentiment model with uncalibrated confidence. "
                "Thresholds are starting values until tuned on a hand-labelled gold set.", "Italic")]
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, title="ReviewIQ report").build(story)
    return Response(buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=reviewiq_report.pdf"})
