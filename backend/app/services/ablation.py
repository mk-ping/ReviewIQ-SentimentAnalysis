
"""Does a model earn its place? Pure functions over gold labels, so they can be tested without a database.

Systems are dicts {review_id: 'neg'|'neu'|'pos'}. Everything is compared on the reviews both systems cover,
and a model only 'beats' another when the paired bootstrap interval of the macro-F1 difference is above zero."""
import random

from app.services import evaluation as E


def common_ids(gold: dict[int, str], *systems: dict[int, str]) -> list[int]:
    return sorted(i for i in gold if all(i in s for s in systems))


def mean_fusion(preds: dict[int, list[tuple[float, float, float]]], skip: int | None = None) -> dict[int, str]:
    """What the pipeline does: average the models' probabilities, take the top label. skip drops one model by position."""
    out = {}
    for rid, ps in preds.items():
        use = [p for k, p in enumerate(ps) if k != skip]
        if use:
            n, u, p = (sum(x[i] for x in use) / len(use) for i in range(3))
            out[rid] = E.argmax_label(n, u, p)
    return out


def paired_bootstrap_diff(gold: dict[int, str], a: dict[int, str], b: dict[int, str], n: int = 500, seed: int = 7) -> dict | None:
    """Macro-F1 of a minus b on shared reviews, with a 95% interval. None under 10 shared reviews."""
    ids = common_ids(gold, a, b)
    if len(ids) < 10:
        return None
    rng = random.Random(seed)
    g, pa, pb = [gold[i] for i in ids], [a[i] for i in ids], [b[i] for i in ids]
    diffs = []
    for _ in range(n):
        pick = [rng.randrange(len(ids)) for _ in ids]
        fa = E.macro_f1([g[i] for i in pick], [pa[i] for i in pick])
        fb = E.macro_f1([g[i] for i in pick], [pb[i] for i in pick])
        if fa is not None and fb is not None:
            diffs.append(fa - fb)
    diffs.sort()
    lo, hi = diffs[int(0.025 * len(diffs))], diffs[min(int(0.975 * len(diffs)), len(diffs) - 1)]
    return {"n": len(ids), "f1_a": E.macro_f1(g, pa), "f1_b": E.macro_f1(g, pb), "diff": E.macro_f1(g, pa) - E.macro_f1(g, pb),
            "lo": lo, "hi": hi, "verdict": "beats" if lo > 0 else "worse" if hi < 0 else "no clear difference"}


def stacker_features(stars: float | None, per_model: list[tuple[float, float, float] | None]) -> list[float]:
    """One row per review: each model's three probabilities (zeros plus a missing flag when it did not run), then the star score."""
    row: list[float] = []
    for p in per_model:
        row += list(p) + [0.0] if p else [0.0, 0.0, 0.0, 1.0]
    row += [0.0, 1.0] if stars is None else [(stars - 3) / 2, 0.0]
    return row


def stack_cv(X: list[list[float]], y: list[str], folds: int = 5, seed: int = 7) -> list[str]:
    """Out-of-fold predictions of a small logistic regression on the model outputs. Needs scikit-learn."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict

    counts = {c: y.count(c) for c in set(y)}
    k = max(2, min(folds, min(counts.values())))
    clf = LogisticRegression(max_iter=2000, class_weight="balanced", C=1.0)
    return list(cross_val_predict(clf, X, y, cv=StratifiedKFold(k, shuffle=True, random_state=seed)))
