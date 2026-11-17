"""Full metric suite for the final report. Pure Python, no scikit-learn, so every number can be checked by hand.
Labels are the strings neg, neu, pos (ordered: neg < neu < pos). Probabilities are (p_neg, p_neu, p_pos)."""
import math
import random

LABELS = ("neg", "neu", "pos")
IDX = {c: i for i, c in enumerate(LABELS)}


def confusion_matrix(gold, pred) -> list[list[int]]:
    m = [[0] * 3 for _ in range(3)]
    for g, p in zip(gold, pred):
        if g in IDX and p in IDX:
            m[IDX[g]][IDX[p]] += 1
    return m


def _prf(m):
    out = []
    for i in range(3):
        tp = m[i][i]
        fp = sum(m[r][i] for r in range(3)) - tp
        fn = sum(m[i]) - tp
        support = sum(m[i])
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f = 2 * p * r / (p + r) if p + r else 0.0
        out.append((p, r, f, support))
    return out


def mcc(m) -> float:
    """Multiclass Matthews correlation coefficient (Gorodkin). 1 is perfect, 0 is chance, below 0 is worse than chance."""
    n = sum(map(sum, m))
    if n == 0:
        return 0.0
    c = sum(m[i][i] for i in range(3))
    t = [sum(m[i]) for i in range(3)]
    p = [sum(m[r][i] for r in range(3)) for i in range(3)]
    num = c * n - sum(t[i] * p[i] for i in range(3))
    den = math.sqrt((n * n - sum(x * x for x in p)) * (n * n - sum(x * x for x in t)))
    return num / den if den else 0.0


def kappa(m, weights: str = "none") -> float:
    """Cohen's kappa. weights='quadratic' penalises neg-vs-pos errors more than neg-vs-neu errors."""
    n = sum(map(sum, m))
    if n == 0:
        return 0.0
    t = [sum(m[i]) for i in range(3)]
    p = [sum(m[r][i] for r in range(3)) for i in range(3)]
    w = lambda i, j: 0.0 if i == j else 1.0 if weights == "none" else ((i - j) ** 2) / 4.0
    obs = sum(w(i, j) * m[i][j] for i in range(3) for j in range(3)) / n
    exp = sum(w(i, j) * t[i] * p[j] for i in range(3) for j in range(3)) / (n * n)
    return 1 - obs / exp if exp else 0.0


def auc_ovr(gold, probs) -> float | None:
    """Macro one-vs-rest ROC AUC by the rank-sum formula, ties get the average rank."""
    aucs = []
    for k in range(3):
        pos = [probs[i][k] for i, g in enumerate(gold) if IDX.get(g) == k]
        neg = [probs[i][k] for i, g in enumerate(gold) if IDX.get(g) is not None and IDX[g] != k]
        if not pos or not neg:
            continue
        allv = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
        ranks, i = {}, 0
        rank_sum = 0.0
        while i < len(allv):
            j = i
            while j + 1 < len(allv) and allv[j + 1][0] == allv[i][0]:
                j += 1
            avg = (i + j) / 2 + 1
            rank_sum += avg * sum(lab for _, lab in allv[i:j + 1])
            i = j + 1
        aucs.append((rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))
    return sum(aucs) / len(aucs) if aucs else None


def calibration(conf, correct, bins: int = 10) -> dict:
    n = len(conf)
    rows, ece, mce = [], 0.0, 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        mem = [(c, k) for c, k in zip(conf, correct) if lo <= c < hi or (b == bins - 1 and c == 1.0)]
        if not mem:
            continue
        mc, acc = sum(c for c, _ in mem) / len(mem), sum(k for _, k in mem) / len(mem)
        ece += len(mem) / n * abs(acc - mc)
        mce = max(mce, abs(acc - mc))
        rows.append({"lo": lo, "hi": hi, "n": len(mem), "confidence": round(mc, 4), "accuracy": round(acc, 4)})
    return {"ece": round(ece, 4) if n else None, "mce": round(mce, 4) if n else None, "bins": rows}


def report(gold: list[str], pred: list[str], probs: list[tuple] | None = None) -> dict:
    """Everything a results table needs for one system on one test set."""
    m = confusion_matrix(gold, pred)
    n = sum(map(sum, m))
    prf = _prf(m)
    present = [x for x in prf if x[3] > 0]
    acc = sum(m[i][i] for i in range(3)) / n if n else None
    out = {
        "n": n, "accuracy": acc,
        "balanced_accuracy": sum(x[1] for x in present) / len(present) if present else None,
        "macro_precision": sum(x[0] for x in present) / len(present) if present else None,
        "macro_recall": sum(x[1] for x in present) / len(present) if present else None,
        "macro_f1": sum(x[2] for x in present) / len(present) if present else None,
        "weighted_f1": sum(x[2] * x[3] for x in present) / n if n else None,
        "mcc": mcc(m), "kappa": kappa(m), "quadratic_kappa": kappa(m, "quadratic"),
        "opposite_error_rate": (m[0][2] + m[2][0]) / n if n else None,   # called positive when negative, or the reverse
        "per_class": {c: {"precision": prf[i][0], "recall": prf[i][1], "f1": prf[i][2], "support": prf[i][3]} for i, c in enumerate(LABELS)},
        "confusion": m,
        "confusion_row_pct": [[(m[i][j] / sum(m[i]) if sum(m[i]) else 0.0) for j in range(3)] for i in range(3)],
    }
    if probs is not None and n:
        eps = 1e-12
        rows = [(IDX[g], p) for g, p in zip(gold, probs) if g in IDX]
        out["log_loss"] = -sum(math.log(max(p[i], eps)) for i, p in rows) / len(rows)
        out["brier"] = sum(sum((p[k] - (1.0 if k == i else 0.0)) ** 2 for k in range(3)) for i, p in rows) / len(rows)
        out["auc_ovr"] = auc_ovr(gold, probs)
        conf = [max(p) for p in probs]
        out["calibration"] = calibration(conf, [LABELS[max(range(3), key=lambda k: p[k])] == g for p, g in zip(probs, gold)])
    return out


def bootstrap_ci(fn, gold, pred, n: int = 500, seed: int = 7):
    """95% interval of fn(gold, pred) by resampling reviews. None under 10 labels."""
    if len(gold) < 10:
        return None
    rng = random.Random(seed)
    idx = range(len(gold))
    vals = sorted(fn([gold[i] for i in pick], [pred[i] for i in pick]) for pick in ([rng.choice(idx) for _ in idx] for _ in range(n)))
    return vals[int(0.025 * n)], vals[min(int(0.975 * n), n - 1)]


def f_acc(g, p): return sum(a == b for a, b in zip(g, p)) / len(g)
def f_macro(g, p): return report(g, p)["macro_f1"]
def f_mcc(g, p): return mcc(confusion_matrix(g, p))


def mcnemar(gold, pred_a, pred_b) -> dict:
    """Exact McNemar test on the reviews where exactly one system is right. p below 0.05 means the difference is not noise."""
    b = sum(1 for g, a, c in zip(gold, pred_a, pred_b) if a == g and c != g)   # only A right
    c = sum(1 for g, a, d in zip(gold, pred_a, pred_b) if a != g and d == g)   # only B right
    n = b + c
    if n == 0:
        return {"only_a": 0, "only_b": 0, "p_value": 1.0}
    k = min(b, c)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
    return {"only_a": b, "only_b": c, "p_value": p}


def star_metrics(actual: list[float], predicted: list[float]) -> dict:
    """How close a predicted star rating is to the real one (used for fused or text-predicted stars)."""
    n = len(actual)
    if n == 0:
        return {"n": 0}
    err = [p - a for a, p in zip(actual, predicted)]
    mae = sum(abs(e) for e in err) / n
    rmse = math.sqrt(sum(e * e for e in err) / n)

    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r

    def corr(x, y):
        mx, my = sum(x) / len(x), sum(y) / len(y)
        sx = math.sqrt(sum((a - mx) ** 2 for a in x))
        sy = math.sqrt(sum((b - my) ** 2 for b in y))
        return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy) if sx and sy else None

    return {"n": n, "mae": mae, "rmse": rmse, "within_half_star": sum(abs(e) <= 0.5 for e in err) / n,
            "within_one_star": sum(abs(e) <= 1.0 for e in err) / n, "bias": sum(err) / n,
            "pearson": corr(actual, predicted), "spearman": corr(rank(actual), rank(predicted))}
