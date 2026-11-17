"""Offline checks for the product risk score. Run: python -m tests.check_watchlist"""
from app.services.watchlist import HIGH, WATCH, WEIGHTS, risk, trend_word

assert sum(WEIGHTS.values()) == 100

calm = {"n": 200, "neg_share": 0.05, "recent_n": 40, "earlier_n": 80, "recent_neg": 0.05, "earlier_neg": 0.05,
        "recent_avg": 4.6, "earlier_avg": 4.6, "severe_n": 0, "hidden_share": 0.02, "top_aspect": "price", "top_aspect_share": 0.03}
r = risk(calm)
assert r["level"] == "ok" and r["score"] < WATCH and r["reasons"] == [] and not r["low_sample"]

bad = {"n": 300, "neg_share": 0.45, "recent_n": 50, "earlier_n": 90, "recent_neg": 0.60, "earlier_neg": 0.30,
       "recent_avg": 2.4, "earlier_avg": 3.8, "severe_n": 4, "hidden_share": 0.3, "top_aspect": "packaging", "top_aspect_share": 0.3}
b = risk(bad)
assert b["score"] == 100 and b["level"] == "high" and b["score"] >= HIGH
assert b["parts"]["negative"] == 30 and b["parts"]["severe"] == 15
assert len(b["reasons"]) == 6 and "packaging" in b["action"]

mid = dict(bad, recent_n=3)                       # too few recent reviews: the trend and the rating drop are not judged
m = risk(mid)
assert m["parts"]["trend"] == 0 and m["parts"]["rating_drop"] == 0 and len(m["not_judged"]) == 2
assert 0 < m["score"] < b["score"]
assert trend_word(mid) == "not enough recent reviews" and trend_word(bad) == "rising" and trend_word(calm) == "steady"

tiny = risk({"n": 5, "neg_share": 0.6})
assert tiny["low_sample"] and tiny["parts"]["trend"] == 0 and tiny["score"] == 30
empty = risk({"n": 0})
assert empty["score"] == 0 and empty["action"] == "No scored reviews yet."
assert risk({"n": 100, "neg_share": 0.2})["score"] == 15
print("watchlist checks passed")
