from app.services.fusion import ensemble, fuse
from app.services.labels import parse_labels
from app.services.routing import MEMBERS, group_of

# study guide 5.11: weights 0.68, 0.61, 0.67 and P(pos) 0.60, 0.80, 0.75 give 0.714
_, _, p = ensemble([(0, 0, 0.60), (0, 0, 0.80), (0, 0, 0.75)], [0.68, 0.61, 0.67])
assert round(p, 3) == 0.714, p

# 5.12 example 1: 3 stars, 'very nice', P(pos) 0.93, P(neg) 0.02 -> fused stars 4.64, under-rated
f = fuse(0.02, 0.05, 0.93, None, 3)
assert f["mismatch_type"] == "underrated" and abs(f["fused_stars"] - 4.64) < 0.01 and f["star_gap"] is None, f

# 5.12 example 2: the ensemble of 5.11 with 3 stars -> fused stars 3.92, and NOT flagged (gap 0.646 < 0.7)
n, u, p = ensemble([(0.10, 0.30, 0.60), (0.05, 0.15, 0.80), (0.05, 0.20, 0.75)], [0.68, 0.61, 0.67])
f = fuse(n, u, p, None, 3)
assert abs(f["fused_stars"] - 3.92) < 0.01 and f["mismatch_type"] is None, f

# 5.13: 5 stars, 'terrible, never again', P(neg) 0.88 -> fused stars 1.76, over-rated
f = fuse(0.88, 0.08, 0.04, 1.44, 5)
assert f["mismatch_type"] == "overrated" and abs(f["fused_stars"] - 1.76) < 0.01 and f["star_gap"] == -3.56, f

# 5.9: expected stars = sum(probability x star) = 3.8
assert abs(sum(i * q for i, q in enumerate([0.1, 0.1, 0.1, 0.3, 0.4], 1)) - 3.8) < 1e-9

# an unsure review is never flagged, and no rating switches fusion off
assert fuse(0.4, 0.3, 0.3, 3.0, 5)["mismatch_type"] is None
e = fuse(0.04, 0.03, 0.93, 4.54, None)
assert e["fused_stars"] is None and e["star_gap"] is None and e["text_label"] == "pos", e

# routing
assert group_of("en") == "english" and group_of("es") == "european"
assert all(group_of(x) == "multi" for x in ("hi", "hinglish", "und", "pt", None))
assert "nlptown" in MEMBERS["english"] and "nlptown" not in MEMBERS["multi"] and "roberta" not in MEMBERS["european"]

# label parsing: stars, polarity, shuffled order, generic names, and a refusal
assert parse_labels({0: "1 star", 1: "2 stars", 2: "3 stars", 3: "4 stars", 4: "5 stars"}) == ("stars", [1, 2, 3, 4, 5])
assert parse_labels({0: "negative", 1: "neutral", 2: "positive"}) == ("polarity", [0, 1, 2])
assert parse_labels({0: "positive", 1: "negative", 2: "neutral"}) == ("polarity", [2, 0, 1])
assert parse_labels({0: "LABEL_0", 1: "LABEL_1", 2: "LABEL_2"}) == ("polarity", [0, 1, 2])
try:
    parse_labels({0: "a", 1: "b", 2: "c", 3: "d"})
    raise SystemExit("should have refused 4 classes")
except RuntimeError:
    pass
print("ensemble, fusion, routing and label checks passed")
