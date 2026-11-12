from app.core.action_rules import RULES, rule_for
from app.core.aspect_config import CATEGORIES
from app.services.actions import share_change

assert set(RULES) == set(CATEGORIES), set(RULES) ^ set(CATEGORIES)
assert rule_for("nonsense")[1] == "Manager"

r = share_change({1, 2, 3}, [1, 2, 3, 4], [5, 6, 7, 8])
assert r["share_before"] == 0.75 and r["share_after"] == 0.0 and r["change"] == -0.75 and r["low_sample"], r
assert share_change({1}, [1, 2], [])["available"] is False
print("action checks passed")
