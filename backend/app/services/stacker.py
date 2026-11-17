"""Learned combination of the sentiment models (a stacker), used instead of the plain weighted average only when it has
proved itself. A small multinomial logistic regression reads each model's log-probabilities and learns each model's
habits, for example that one model under-calls neutral. It is trained on the validation split, gated by cross-validation
against the weighted average, and saved as plain JSON (ml/out/stacker_<group>.json), so inference needs only the standard library."""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from app.services import metrics as M
from app.services.ablation import paired_bootstrap_diff

CLASSES = M.LABELS
OUT = Path(__file__).resolve().parents[3] / "ml" / "out"
MIN_ROWS = 200           # validation reviews needed before a stacker may be applied
MIN_GAIN = 0.005         # and its cross-validated macro F1 must beat the weighted average by this much, with the interval above zero
_cache: dict = {}


def features(members: list[str], probs: dict) -> list[float] | None:
    row: list[float] = []
    for k in members:
        if k not in probs:
            return None
        row += [math.log(max(float(x), 1e-6)) for x in probs[k][:3]]
    return row


def _softmax(z):
    m = max(z)
    e = [math.exp(v - m) for v in z]
    s = sum(e)
    return tuple(v / s for v in e)


def predict(model: dict, probs: dict) -> tuple[float, float, float] | None:
    x = features(model["members"], probs)
    if x is None:
        return None
    return _softmax([sum(w * v for w, v in zip(row, x)) + b for row, b in zip(model["W"], model["b"])])


def weighted_average(members: list[str], probs: dict, weights: dict) -> tuple[float, float, float]:
    tot = sum(weights[k] for k in members)
    return tuple(sum(weights[k] * probs[k][i] for k in members) / tot for i in range(3))


def load(group: str, folder: Path | None = None) -> dict | None:
    """The saved stacker for a route group, only when it was gated as better than the weighted average."""
    key = (group, str(folder or OUT))
    if key not in _cache:
        p = (folder or OUT) / f"stacker_{group}.json"
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
            _cache[key] = m if m.get("applied") else None
        except (OSError, ValueError):
            _cache[key] = None
    return _cache[key]


def refine(group: str, probs: dict, fallback: tuple, folder: Path | None = None) -> tuple:
    """Production hook: the stacker's probabilities when one is applied and every member model ran, else the fallback."""
    m = load(group, folder)
    if not m:
        return fallback
    out = predict(m, probs)
    return out if out else fallback


GRID = [(C, cw) for C in (0.1, 1.0, 10.0) for cw in (None, "balanced")]


def fit(X: list[list[float]], y: list[str], members: list[str], C: float = 1.0, class_weight=None) -> dict | None:
    from sklearn.linear_model import LogisticRegression

    if len(set(y)) < 3:
        return None
    clf = LogisticRegression(max_iter=3000, C=C, class_weight=class_weight).fit(X, y)
    order = [list(clf.classes_).index(c) for c in CLASSES]
    return {"members": members, "classes": list(CLASSES), "W": [clf.coef_[i].tolist() for i in order],
            "b": [float(clf.intercept_[i]) for i in order], "C": C, "class_weight": class_weight}


def cv_labels(X, y, members, folds: int = 5, seed: int = 7, C: float = 1.0, class_weight=None) -> list[str]:
    """Out-of-fold predictions: each review is scored by a stacker that never saw it."""
    from sklearn.model_selection import StratifiedKFold

    counts = {c: y.count(c) for c in set(y)}
    k = max(2, min(folds, min(counts.values())))
    out = [""] * len(y)
    for tr, te in StratifiedKFold(k, shuffle=True, random_state=seed).split(X, y):
        m = fit([X[i] for i in tr], [y[i] for i in tr], members, C, class_weight)
        for i in te:
            z = [sum(w * v for w, v in zip(row, X[i])) + b for row, b in zip(m["W"], m["b"])]
            out[i] = CLASSES[max(range(3), key=lambda c: z[c])]
    return out


def train_group(members: list[str], val_probs: dict, val_gold: list[str], weights: dict) -> dict:
    """val_probs[model] = list of (p_neg, p_neu, p_pos) per validation review. Returns the model plus the evidence for or against applying it."""
    n = len(val_gold)
    X = [features(members, {k: val_probs[k][i] for k in members}) for i in range(n)]
    base = [M.LABELS[max(range(3), key=lambda c: p[c])] for p in
            (weighted_average(members, {k: val_probs[k][i] for k in members}, weights) for i in range(n))]
    info = {"group_members": members, "n_val": n}
    if len(set(val_gold)) < 3 or n < 30:
        return {"model": None, "applied": False, "reason": "needs all three classes and at least 30 validation reviews", **info}
    # choose the regularisation and class weighting on one set of folds, then judge the choice on different folds
    best = max(GRID, key=lambda cfg: M.f_macro(val_gold, cv_labels(X, val_gold, members, 5, 7, *cfg)))
    model = fit(X, val_gold, members, *best)
    oof = cv_labels(X, val_gold, members, 5, 11, *best)
    d = paired_bootstrap_diff(dict(enumerate(val_gold)), dict(enumerate(oof)), dict(enumerate(base)))
    applied = bool(d) and n >= MIN_ROWS and d["lo"] > 0 and d["diff"] >= MIN_GAIN
    reason = ("beats the weighted average in cross-validation" if applied else
              f"only {n} validation reviews (need {MIN_ROWS})" if n < MIN_ROWS else
              f"no clear gain over the weighted average ({d['diff']:+.3f}, interval {d['lo']:+.3f} to {d['hi']:+.3f})" if d else "could not compare")
    model.update({"applied": applied, "reason": reason, "n_val": n, "cv_macro_f1_stacker": d["f1_a"] if d else None,
                  "cv_macro_f1_weighted_average": d["f1_b"] if d else None, "cv_diff": d["diff"] if d else None,
                  "cv_interval": [d["lo"], d["hi"]] if d else None,
                  "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return {"model": model, "applied": applied, "reason": reason, **info}


def compare(model: dict, members: list[str], probs: dict, gold: list[str], weights: dict) -> dict:
    """Weighted average against the stacker on one test set, with the full metric suite and significance tests."""
    n = len(gold)
    per = [{k: probs[k][i] for k in members} for i in range(n)]
    pb = [weighted_average(members, r, weights) for r in per]
    ps = [predict(model, r) for r in per]
    lb = [M.LABELS[max(range(3), key=lambda c: p[c])] for p in pb]
    ls = [M.LABELS[max(range(3), key=lambda c: p[c])] for p in ps]
    out = {"n": n, "weighted_average": M.report(gold, lb, pb), "stacker": M.report(gold, ls, ps), "mcnemar": M.mcnemar(gold, ls, lb)}
    for name, fn in (("accuracy", M.f_acc), ("macro_f1", M.f_macro), ("mcc", M.f_mcc)):
        out[f"ci_{name}"] = {"weighted_average": M.bootstrap_ci(fn, gold, lb), "stacker": M.bootstrap_ci(fn, gold, ls)}
    d = paired_bootstrap_diff(dict(enumerate(gold)), dict(enumerate(ls)), dict(enumerate(lb)))
    out["paired"] = d
    return out
