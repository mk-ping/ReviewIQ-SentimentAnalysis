"""Offline checks for the distribution helpers. Run: python -m tests.check_distribution"""
from app.services.distribution import GAP_BUCKETS, fold, gap_bucket

assert [gap_bucket(g) for g in (-2.5, -2, -1.5, -1, -0.7, -0.5, -0.4, 0, 0.4, 0.5, 0.9, 1, 1.9, 2, 3)] == [0, 0, 1, 1, 2, 2, 3, 3, 3, 4, 4, 5, 5, 6, 6]
assert len(GAP_BUCKETS) == 7

rows = [(5, "pos", 8), (5, "neg", 2), (1, "neg", 3), (1, "neu", 1), (3, "weird", 9), (5, "neu", 0)]
out = fold(rows)
assert [d["key"] for d in out] == [5, 1]                # biggest first; the unknown label is ignored
assert out[0]["n"] == 10 and out[0]["pos_share"] == 0.8 and out[0]["neg_share"] == 0.2
assert out[1]["neg"] == 3 and out[1]["neu"] == 1 and out[1]["pos"] == 0
assert len(fold(rows, keep=1)) == 1
assert fold([]) == []
print("distribution checks passed")
