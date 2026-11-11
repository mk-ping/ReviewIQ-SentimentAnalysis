from app.services.fusion import fuse

# (p_neg, p_neu, p_pos, expected, stars) -> expected mismatch
a = fuse(0.04, 0.03, 0.93, 4.54, 1)
assert a["mismatch_type"] == "underrated" and a["star_gap"] == 3.54, a
b = fuse(0.92, 0.04, 0.03, 1.44, 5)
assert b["mismatch_type"] == "overrated", b
c = fuse(0.04, 0.03, 0.93, 4.54, 5)
assert c["mismatch_type"] is None, c
d = fuse(0.4, 0.3, 0.3, 3.0, 5)  # low confidence: no flag
assert d["mismatch_type"] is None and d["text_label"] == "neg", d
e = fuse(0.04, 0.03, 0.93, 4.54, None)  # no rating: fusion switched off
assert e["fused_stars"] is None and e["star_gap"] is None and e["text_label"] == "pos", e
print("fused stars for case a:", a["fused_stars"], "(text says 5, customer said 1)")
print("fusion checks passed")
