"""Offline checks for the PDF report wording and layout. Run: python -m tests.check_report"""
from datetime import date

from app.services.report_pdf import build
from app.services.report_text import headlines, product_status

assert product_status({"n": 10, "low_sample": True})[0] == "Early read (10 reviews)"
assert "less happy" in product_status({"n": 80, "low_sample": False, "clear_difference": True, "true_rating": 3.1, "shown_avg": 4.2})[0]
assert "happier" in product_status({"n": 80, "low_sample": False, "clear_difference": True, "true_rating": 4.5, "shown_avg": 4.0})[0]
assert product_status({"n": 80, "low_sample": False, "clear_difference": False})[1] == "good"
for lab in ("too few", "Too few"):
    assert lab not in product_status({"n": 3, "low_sample": True})[0]

D = {"generated": "17 Nov 2026", "date_from": date(2026, 1, 1), "date_to": date(2026, 11, 1), "n_products": 3,
     "summary": {"reviews": 1200, "average_rating": 3.9, "percent_negative": 22.0, "net_sentiment": 0.31, "mismatch_rate": 0.21,
                 "top_strengths": [{"aspect": "scent", "positive_mentions": 300, "avg_sentiment": 0.7}], "low_sample": False},
     "dist": {"audience": "lukewarm", "histogram": [{"stars": s, "count": c} for s, c in zip(range(1, 6), (80, 60, 120, 300, 640))]},
     "products": [{"product": "Cream", "n": 700, "low_sample": False, "shown_avg": 4.3, "true_rating": 3.6, "clear_difference": True},
                  {"product": "Soap", "n": 12, "low_sample": True, "shown_avg": 4.0, "true_rating": 3.9, "clear_difference": False}],
     "issues": [("pump stops working", "packaging", 140, 100.0, 0.7, 0.2, "Review the closure or pump design", "Packaging and supplier quality")],
     "split": {"pos": 700, "neu": 230, "neg": 270}, "quotes": [("pump stops working", "The pump stopped working after a week.")],
     "watch": [{"product": "Cream", "score": 72, "level": "high", "reasons": ["30% of reviews are negative."], "action": "Start with packaging."}],
     "severe_n": 4}
lines = headlines(D)
assert any("pump stops working" in x for x in lines) and any("Cream (risk 72)" in x for x in lines) and any("4 reviews mention" in x for x in lines)
assert any("disagree on 21%" in x for x in lines) and len(lines) <= 8
pdf = build(D)
assert pdf[:4] == b"%PDF" and len(pdf) > 3000

tiny = dict(D, summary=dict(D["summary"], reviews=8), issues=[], watch=[], quotes=[], products=[], split={}, severe_n=0,
            dist={"audience": None, "histogram": []})
assert any("early read based on 8 reviews" in x for x in headlines(tiny))
assert build(tiny)[:4] == b"%PDF"

from app.services.replies import draft_reply, draft_thanks

base = draft_reply([], "packaging", "en")
assert base.startswith("Thank you for your honest feedback.") and base.endswith("put this right.")
assert "Cream" in draft_reply([], "packaging", "en", product="Cream")
w = draft_reply([], "packaging", "en", tone="warm")
b = draft_reply([], "packaging", "en", tone="brief")
assert w != base and b != base and len(b) < len(base) < len(w)
assert draft_reply([], "packaging", "en", tone="nonsense") == base
sig = draft_reply([], "price", "en", signature="Priya, Customer Care")
assert sig.endswith("Priya, Customer Care") and "\n\n" in sig
assert draft_reply(["safety"], None, "hi", tone="brief").startswith("[Review language: hi.")
th = draft_thanks("scent", "en", product="Soap")
assert "Soap" in th and "scent" in th and "sorry" not in th.lower()
assert "scent" not in draft_thanks("scent", "en", tone="brief") and draft_thanks(None).startswith("Thank you")
print("report checks passed")
