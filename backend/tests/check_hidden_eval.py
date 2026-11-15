"""Offline checks for the hidden-dissatisfaction precision maths. Run: python -m tests.check_hidden_eval"""
from app.services.hidden_eval import summarise, wilson

lo, hi = wilson(80, 100)
assert 0.70 < lo < 0.80 < hi < 0.88, (lo, hi)
assert wilson(0, 0) is None
lo, hi = wilson(0, 10)
assert lo == 0.0 and 0.2 < hi < 0.35

rows = [{"flagged": True, "hidden": True}] * 8 + [{"flagged": True, "hidden": False}] * 2 \
     + [{"flagged": False, "hidden": True}] * 1 + [{"flagged": False, "hidden": False}] * 9
r = summarise(rows)
assert r["precision"] == 0.8 and r["miss_rate"] == 0.1 and r["recall_estimate"] is None
r = summarise(rows, flagged_pop=100, unflagged_pop=400)      # 80 true flagged; 40 missed among the unflagged
assert abs(r["recall_estimate"] - 80 / 120) < 1e-9, r
assert summarise([])["precision"] is None
print("hidden evaluation checks passed")
