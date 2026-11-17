"""Offline checks for the metric suite, compared with scikit-learn when it is installed. Run: python -m tests.check_metrics"""
import random

from app.services import metrics as M

g = ["pos"] * 6 + ["neg"] * 3 + ["neu"] * 3
p = ["pos"] * 5 + ["neu"] + ["neg"] * 2 + ["pos"] + ["neu"] * 2 + ["neg"]
r = M.report(g, p)
assert M.confusion_matrix(g, p) == [[2, 0, 1], [1, 2, 0], [0, 1, 5]]
assert r["n"] == 12 and abs(r["accuracy"] - 9 / 12) < 1e-9
perfect = M.report(g, g)
assert perfect["accuracy"] == 1 and perfect["macro_f1"] == 1 and abs(perfect["mcc"] - 1) < 1e-9 and abs(perfect["kappa"] - 1) < 1e-9
assert abs(perfect["quadratic_kappa"] - 1) < 1e-9 and perfect["opposite_error_rate"] == 0
flip = M.report(["neg", "pos"] * 5, ["pos", "neg"] * 5)
assert flip["opposite_error_rate"] == 1 and flip["mcc"] < 0 and flip["quadratic_kappa"] < 0
mc = M.mcnemar(["a"] * 20, ["a"] * 20, ["b"] * 20)
assert mc["only_a"] == 20 and mc["p_value"] < 0.001
assert M.mcnemar(["a"] * 4, ["a", "a", "b", "b"], ["b", "b", "a", "a"])["p_value"] == 1.0
s = M.star_metrics([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
assert s["mae"] == 0 and abs(s["spearman"] - 1) < 1e-9 and s["within_one_star"] == 1
s = M.star_metrics([5, 5, 1], [4, 5, 3])
assert abs(s["mae"] - 1.0) < 1e-9 and abs(s["within_one_star"] - 2 / 3) < 1e-9
assert M.bootstrap_ci(M.f_acc, g, p) is not None and M.bootstrap_ci(M.f_acc, g[:5], p[:5]) is None

# random data: compare with scikit-learn
rng = random.Random(3)
L = list(M.LABELS)
gold = [rng.choice(L) for _ in range(400)]
probs = []
for y in gold:
    v = [rng.random() for _ in range(3)]
    v[L.index(y)] += rng.random() * 0.9
    t = sum(v)
    probs.append(tuple(x / t for x in v))
pred = [L[max(range(3), key=lambda k: pr[k])] for pr in probs]
mine = M.report(gold, pred, probs)
assert 0 < mine["accuracy"] < 1 and 0 < mine["auc_ovr"] < 1 and mine["calibration"]["ece"] is not None
try:
    from sklearn import metrics as sk
    yi = [M.IDX[x] for x in gold]
    assert abs(mine["accuracy"] - sk.accuracy_score(gold, pred)) < 1e-9
    assert abs(mine["macro_f1"] - sk.f1_score(gold, pred, average="macro")) < 1e-9
    assert abs(mine["weighted_f1"] - sk.f1_score(gold, pred, average="weighted")) < 1e-9
    assert abs(mine["balanced_accuracy"] - sk.balanced_accuracy_score(gold, pred)) < 1e-9
    assert abs(mine["mcc"] - sk.matthews_corrcoef(gold, pred)) < 1e-9
    assert abs(mine["kappa"] - sk.cohen_kappa_score(gold, pred)) < 1e-9
    assert abs(mine["quadratic_kappa"] - sk.cohen_kappa_score(yi, [M.IDX[x] for x in pred], weights="quadratic")) < 1e-9
    assert abs(mine["auc_ovr"] - sk.roc_auc_score(yi, probs, multi_class="ovr", average="macro")) < 1e-9
    assert abs(mine["log_loss"] - sk.log_loss(yi, probs, labels=[0, 1, 2])) < 1e-9
    print("matches scikit-learn")
except ImportError:
    print("scikit-learn not installed: skipped the cross-check")
print("metrics checks passed")
