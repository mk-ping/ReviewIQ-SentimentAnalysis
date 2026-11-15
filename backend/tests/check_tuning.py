
import random

from app.services import tuning as U
from app.services.fusion import fuse

# the inversion must recover the text score that fuse() used
for pn, pu, pp, stars in [(0.02, 0.05, 0.93, 3), (0.9, 0.05, 0.05, 5), (0.2, 0.3, 0.5, 2), (0.1, 0.1, 0.8, 4)]:
    out = fuse(pn, pu, pp, None, stars)
    got = U.text_score_from_fused(out["fused_stars"], stars, out["confidence"])
    assert abs(got - (pp - pn)) < 0.01, (got, pp - pn)

rng = random.Random(5)
rows = []
for _ in range(120):                      # real mismatches have a big gap and are confident
    rows.append((True, rng.choice([1, -1]) * rng.uniform(0.9, 1.0), 0.0, rng.uniform(0.75, 0.99)))  # text far from a 3-star score
for _ in range(180):                      # ordinary reviews agree, or are unsure
    t = rng.uniform(-1, 1)
    rows.append((False, t, t + rng.uniform(-0.3, 0.3), rng.uniform(0.4, 0.95)))
res = U.tune(rows)
assert res["ok"] and res["n"] == 300 and res["positives"] == 120
assert res["best"]["precision"] >= 0.7 and res["best"]["f1"] >= res["current"]["f1"] - 1e-9
assert len(res["top"]) == 5 and res["precision_goal_met"]

few = U.tune(rows[:20])
assert not few["ok"] and "Need" in few["reason"]
nopos = U.tune([(False, 0.1, 0.1, 0.9)] * 80)
assert not nopos["ok"]
e = U.evaluate([(True, 0.9, -0.9, 0.9), (False, 0.1, 0.1, 0.9)], 0.7, 0.7)
assert e["flagged"] == 1 and e["precision"] == 1.0 and e["recall"] == 1.0
assert U.evaluate([(False, 0.1, 0.1, 0.9)], 0.7, 0.7)["precision"] is None
print("tuning checks passed")
