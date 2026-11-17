"""Executive PDF report: cover band, summary, key numbers, rating and sentiment charts, priorities with next steps,
product watchlist, product table and notes. build(data) is pure; gather() reads the database."""
import io
from datetime import date
from xml.sax.saxutils import escape

from app.services.report_text import headlines, product_status, date_span

VIOLET, CYAN, INK, MUTE = "#5b4bd6", "#0891b2", "#1b1d2a", "#6b7080"
GOOD, BAD, WARN, LINE = "#16a34a", "#dc2626", "#d97706", "#d9dbe5"
TONE = {"good": GOOD, "bad": BAD, "neutral": MUTE}
LEVEL = {"high": ("High risk", BAD), "watch": ("Watch", WARN), "ok": ("On track", GOOD)}


def _latin(t: str) -> bool:
    try:
        t.encode("latin-1")
        return True
    except UnicodeEncodeError:
        return False


def build(d: dict) -> bytes:
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    C = colors.HexColor
    base = getSampleStyleSheet()["BodyText"]
    body = ParagraphStyle("b", parent=base, fontSize=9.5, leading=13.5, textColor=C(INK))
    small = ParagraphStyle("s", parent=body, fontSize=8, leading=11, textColor=C(MUTE))
    h1 = ParagraphStyle("h1", parent=body, fontName="Helvetica-Bold", fontSize=15, leading=19, spaceBefore=14, spaceAfter=6, textColor=C(INK))
    bullet = ParagraphStyle("bl", parent=body, leftIndent=12, bulletIndent=0, spaceAfter=3)
    cell = ParagraphStyle("c", parent=body, fontSize=8.5, leading=11)
    P = lambda t, st=body: Paragraph(escape(str(t)), st)
    s, dist = d["summary"], d["dist"]
    f = lambda x, k=2: "n/a" if x is None else f"{x:.{k}f}"
    W = A4[0] - 36 * mm

    def head(c, doc):
        c.saveState()
        c.setFillColor(C(VIOLET)); c.rect(0, A4[1] - 14 * mm, A4[0], 14 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 12); c.drawString(18 * mm, A4[1] - 9 * mm, "ReviewIQ")
        c.setFont("Helvetica", 9); c.drawRightString(A4[0] - 18 * mm, A4[1] - 9 * mm, "Customer review report")
        c.setFillColor(C(MUTE)); c.setFont("Helvetica", 8)
        c.drawString(18 * mm, 10 * mm, f"Generated {d['generated']}  |  Confidential")
        c.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        c.restoreState()

    story = [Spacer(1, 6), P("Customer review report", ParagraphStyle("t", parent=h1, fontSize=22, leading=26, spaceBefore=4)),
             P(date_span(d.get("date_from"), d.get("date_to")) or f"Generated {d['generated']}", small), Spacer(1, 8)]

    story += [P("Summary", h1)]
    for line in headlines(d):
        story.append(Paragraph(escape(line), bullet, bulletText="\u2022"))

    tiles = [("Reviews", f"{s['reviews']:,}"), ("Average rating", f(s["average_rating"])),
             ("Net sentiment", f(s["net_sentiment"])), ("Negative", "n/a" if s["percent_negative"] is None else f"{s['percent_negative']:.0f}%")]
    tile = ParagraphStyle("tile", parent=body, leading=24)
    t = Table([[Paragraph(f'<font size="8" color="{MUTE}">{escape(a)}</font><br/><font size="17" color="{INK}"><b>{escape(b)}</b></font>', tile) for a, b in tiles]],
              colWidths=[W / 4] * 4)
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, C(LINE)), ("INNERGRID", (0, 0), (-1, -1), 0.5, C(LINE)),
                           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("BACKGROUND", (0, 0), (-1, -1), C("#f6f6fb"))]))
    story += [Spacer(1, 8), t]

    # charts: rating distribution and sentiment split
    hist = dist.get("histogram") or []
    dr = Drawing(W / 2 - 4, 120)
    if hist and sum(b["count"] for b in hist):
        ch = VerticalBarChart(); ch.x, ch.y, ch.width, ch.height = 22, 20, W / 2 - 40, 78
        ch.data = [[b["count"] for b in hist]]; ch.categoryAxis.categoryNames = [f"{b['stars']} star" for b in hist]
        ch.bars[0].fillColor = C(VIOLET); ch.bars[0].strokeColor = None; ch.valueAxis.valueMin = 0; ch.categoryAxis.labels.fontSize = 7; ch.valueAxis.labels.fontSize = 7; ch.categoryAxis.labels.fontName = ch.valueAxis.labels.fontName = "Helvetica"
        ch.valueAxis.strokeColor = C(LINE); ch.categoryAxis.strokeColor = C(LINE)
        dr.add(String(0, 108, "Rating distribution", fontSize=9, fontName="Helvetica-Bold", fillColor=C(INK)))
        dr.add(ch)
    sd = Drawing(W / 2 - 4, 120)
    sp = d.get("split") or {}
    tot = sum(sp.values())
    sd.add(String(0, 108, "What the text says", fontSize=9, fontName="Helvetica-Bold", fillColor=C(INK)))
    if tot:
        x, bw = 0, W / 2 - 14
        for key, col, lab in (("pos", GOOD, "Positive"), ("neu", "#94a3b8", "Neutral"), ("neg", BAD, "Negative")):
            w = bw * sp.get(key, 0) / tot
            if w > 0:
                sd.add(Rect(x, 62, w, 22, fillColor=C(col), strokeColor=None))
            x += w
        for i, (key, col, lab) in enumerate((("pos", GOOD, "Positive"), ("neu", "#94a3b8", "Neutral"), ("neg", BAD, "Negative"))):
            sd.add(Rect(0, 38 - i * 14, 8, 8, fillColor=C(col), strokeColor=None))
            sd.add(String(14, 38 - i * 14, f"{lab}: {sp.get(key, 0):,} ({100 * sp.get(key, 0) / tot:.0f}%)", fontSize=8, fontName="Helvetica", fillColor=C(INK)))
    t = Table([[dr, sd]], colWidths=[W / 2, W / 2]); t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [Spacer(1, 10), t]

    # priorities
    story.append(P("What to fix first", h1))
    if d["issues"]:
        rows = [[P(h, cell) for h in ("Problem", "Reviews", "Priority", "What to do", "Owner")]]
        for name, asp, n, score, sev, hid, act, team in d["issues"]:
            rows.append([Paragraph(f"<b>{escape(name)}</b><br/><font size=7 color='{MUTE}'>{escape(asp)}</font>", cell),
                         P(n, cell), P(f"{score:.0f}", cell), P(act, cell), P(team, cell)])
        t = Table(rows, colWidths=[W * .23, W * .09, W * .09, W * .39, W * .20], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), C("#ececf8")), ("LINEBELOW", (0, 0), (-1, -1), 0.4, C(LINE)),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        story.append(t)
        quotes = [(n, q) for n, q in d.get("quotes", []) if q and _latin(q)][:3]
        if quotes:
            story += [Spacer(1, 6), P("In customers' words", ParagraphStyle("q", parent=body, fontName="Helvetica-Bold"))]
            for n, q in quotes:
                story.append(Paragraph(escape(f"\u201c{q[:220]}\u201d  ({n})"), ParagraphStyle("qq", parent=small, leftIndent=10, textColor=C(INK))))
    else:
        story.append(P("No problems have been identified yet. Problems appear after the analysis has run on enough reviews."))

    # watchlist
    if d.get("watch"):
        story.append(P("Products to watch", h1))
        rows = [[P(h, cell) for h in ("Product", "Risk", "Status", "Why", "Next step")]]
        for w in d["watch"][:8]:
            lab, col = LEVEL[w["level"]]
            rows.append([P(w["product"], cell), P(w["score"], cell), Paragraph(f"<font color='{col}'><b>{lab}</b></font>", cell),
                         P(" ".join(w["reasons"][:2]) or "No warning signs.", cell), P(w["action"], cell)])
        t = Table(rows, colWidths=[W * .17, W * .08, W * .12, W * .35, W * .28], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), C("#ececf8")), ("LINEBELOW", (0, 0), (-1, -1), 0.4, C(LINE)),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        story += [t, P("Risk runs from 0 to 100. 60 or more is high risk. It combines the share of negative reviews, recent change, safety or legal mentions, hidden complaints and how concentrated the complaints are.", small)]

    # strengths
    if s.get("top_strengths"):
        story.append(P("What customers like", h1))
        for x in s["top_strengths"][:5]:
            story.append(Paragraph(escape(f"{x['aspect'].capitalize()}: {x['positive_mentions']} positive mentions"), bullet, bulletText="\u2022"))

    # products
    if d["products"]:
        story.append(P("Shown rating versus what customers write", h1))
        rows = [[P(h, cell) for h in ("Product", "Reviews", "Shown", "Text-based", "Reading")]]
        for p in d["products"]:
            lab, tone = product_status(p)
            rows.append([P(p["product"][:40], cell), P(p["n"], cell), P(f(p["shown_avg"]), cell), P(f(p["true_rating"]), cell),
                         Paragraph(f"<font color='{TONE[tone]}'>{escape(lab)}</font>", cell)])
        t = Table(rows, colWidths=[W * .30, W * .10, W * .10, W * .13, W * .37], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), C("#ececf8")), ("LINEBELOW", (0, 0), (-1, -1), 0.4, C(LINE)),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        story += [t, P("Text-based is the rating the written reviews support, adjusted so that products with few reviews are not over-read.", small)]

    story += [Spacer(1, 14), P("About this report", ParagraphStyle("ab", parent=body, fontName="Helvetica-Bold")),
              P("Figures come from automated analysis of review text and ratings and are estimates. Reviews flagged as spam are excluded. "
                "Where a product has only a few reviews, its figures are labelled as an early read.", small)]
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, title="ReviewIQ customer review report", author="ReviewIQ",
                      leftMargin=18 * mm, rightMargin=18 * mm, topMargin=22 * mm, bottomMargin=18 * mm).build(story, onFirstPage=head, onLaterPages=head)
    return buf.getvalue()


async def gather(session, ws: int, summary_fn, distribution_fn, true_rating_fn, issues_fn) -> dict:
    from sqlalchemy import text
    from app.core import thresholds as T
    from app.core.action_rules import rule_for

    a = {"ws": ws, "spam": T.SPAM_MAX}
    s = await summary_fn(None, None, None, session)
    dist = await distribution_fn(None, None, None, session)
    tr = await true_rating_fn(session, ws)
    issues = []
    for name, asp, n, score, sev, hid in (await issues_fn(session, ws))[:6]:
        act, team = rule_for(asp)
        issues.append((name, asp, n, score, sev, hid, act, team))
    d1, d2, nprod = (await session.execute(text("""
        SELECT min(r.review_date), max(r.review_date), count(DISTINCT r.product_id) FROM review r
        WHERE r.workspace_id = :ws AND r.spam_score <= :spam"""), a)).one()
    split = {k: c for k, c in (await session.execute(text("""
        SELECT s.text_label, count(*) FROM review r JOIN review_score s ON s.review_id = r.review_id
        WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND s.text_label IS NOT NULL GROUP BY 1"""), a)).all()}
    quotes = [(n, q) for n, q in (await session.execute(text("""
        SELECT DISTINCT ON (i.issue_id) i.name, ir.evidence_span FROM issue i JOIN issue_priority ip ON ip.issue_id = i.issue_id
        JOIN issue_review ir ON ir.issue_id = i.issue_id
        WHERE i.workspace_id = :ws AND ir.evidence_span IS NOT NULL ORDER BY i.issue_id, ir.sentiment ASC"""), {"ws": ws})).all()]
    watch, severe_n = [], 0
    try:
        from app.api.watchlist import watchlist
        watch = (await watchlist(session))["products"]
    except Exception:
        watch = []
    try:
        from app.api.replies import severe
        severe_n = (await severe(limit=0, session=session))["total"]
    except Exception:
        severe_n = 0
    return {"generated": date.today().strftime("%d %b %Y"), "summary": s, "dist": dist, "products": tr, "issues": issues,
            "date_from": d1, "date_to": d2, "n_products": nprod or 0, "split": split, "quotes": quotes, "watch": watch, "severe_n": severe_n}
