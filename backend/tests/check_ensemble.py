from app.services.fusion import ensemble, fuse
from app.services.routing import MEMBERS, group_of

# document section 4: weights 0.68, 0.61, 0.67 and P(pos) 0.60, 0.80, 0.75 give 0.714
_, _, p = ensemble([(0, 0, 0.60), (0, 0, 0.80), (0, 0, 0.75)], [0.68, 0.61, 0.67])
assert round(p, 3) == 0.714, p

# section 7: 3 stars, 'very nice', P(pos) 0.93 and P(neg) 0.02 -> text 0.91, fused stars 4.64, under-rated
f = fuse(0.02, 0.05, 0.93, None, 3)
assert f["mismatch_type"] == "underrated" and abs(f["fused_stars"] - 4.64) < 0.01, f
assert f["star_gap"] is None, "no nlptown, so no star gap"

# expected stars = sum(probability x star): 0.1,0.1,0.1,0.3,0.4 -> 3.8
assert abs(sum(i * p for i, p in enumerate([0.1, 0.1, 0.1, 0.3, 0.4], 1)) - 3.8) < 1e-9

# an uncertain review is never flagged
assert fuse(0.4, 0.3, 0.3, 3.0, 5)["mismatch_type"] is None

assert group_of("en") == "english" and group_of("es") == "european"
assert all(group_of(x) == "multi" for x in ("hi", "hinglish", "und", "pt"))
assert "nlptown" in MEMBERS["english"] and "nlptown" not in MEMBERS["multi"]
print("ensemble and routing checks passed")
