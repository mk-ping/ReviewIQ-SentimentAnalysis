
import random

from app.services import ablation as A
from app.services import evaluation as E

rng = random.Random(1)
gold = {i: rng.choice(["neg", "neu", "pos"]) for i in range(120)}


def noisy(acc):
    return {i: g if rng.random() < acc else rng.choice(["neg", "neu", "pos"]) for i, g in gold.items()}


good, bad = noisy(0.9), noisy(0.4)
d = A.paired_bootstrap_diff(gold, good, bad)
assert d["verdict"] == "beats" and d["diff"] > 0.3, d
assert A.paired_bootstrap_diff(gold, bad, good)["verdict"] == "worse"
assert A.paired_bootstrap_diff(gold, good, dict(good))["verdict"] == "no clear difference"
assert A.paired_bootstrap_diff({1: "pos"}, {1: "pos"}, {1: "pos"}) is None

assert A.common_ids(gold, {1: "a", 2: "b"}, {2: "x"}) == [2]
mf = A.mean_fusion({1: [(0.9, 0.05, 0.05), (0.1, 0.1, 0.8)], 2: [(0.0, 0.0, 1.0)]})
assert mf == {1: "neg", 2: "pos"}, mf          # 0.5 neg vs 0.425 pos on average
assert A.mean_fusion({1: [(0.9, 0.05, 0.05), (0.1, 0.1, 0.8)]}, skip=0) == {1: "pos"}

row = A.stacker_features(5, [(0.1, 0.1, 0.8), None])
assert row == [0.1, 0.1, 0.8, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0], row
assert A.stacker_features(None, [])[-2:] == [0.0, 1.0]

try:
    import sklearn  # noqa: F401
except ImportError:
    print("ablation checks passed (stacker skipped: scikit-learn missing)")
else:
    ids = sorted(gold)
    X = [[(1.0 if gold[i] == "neg" else 0.0), (1.0 if gold[i] == "neu" else 0.0), (1.0 if gold[i] == "pos" else 0.0)] for i in ids]
    pred = A.stack_cv(X, [gold[i] for i in ids])
    assert E.accuracy([gold[i] for i in ids], pred) > 0.95
    print("ablation checks passed")
