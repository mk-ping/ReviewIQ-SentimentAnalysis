"""Evaluation metrics for the hand-labelled gold set. Pure functions, so they are easy to test and to defend.

Labels are 'neg', 'neu', 'pos'. Every function skips nothing silently: empty input gives None, never a fake zero."""
import random

LABELS = ("neg", "neu", "pos")


def stars_to_label(stars: float | None) -> str | None:
    """What the star rating alone says: 1-2 negative, 3 neutral, 4-5 positive."""
    if stars is None:
        return None
    s = round(stars)
    return "neg" if s <= 2 else "neu" if s == 3 else "pos"


def argmax_label(p_neg: float, p_neu: float, p_pos: float) -> str:
    return max(zip((p_neg, p_neu, p_pos), LABELS), key=lambda t: t[0])[1]


def confusion(gold: list[str], pred: list[str]) -> dict[str, dict[str, int]]:
    out = {g: {p: 0 for p in LABELS} for g in LABELS}
    for g, p in zip(gold, pred):
        if g in out and p in out[g]:
            out[g][p] += 1
    return out


def per_class(gold: list[str], pred: list[str]) -> dict[str, dict]:
    out = {}
    for c in LABELS:
        tp = sum(1 for g, p in zip(gold, pred) if g == c and p == c)
        fp = sum(1 for g, p in zip(gold, pred) if g != c and p == c)
        fn = sum(1 for g, p in zip(gold, pred) if g == c and p != c)
        support = tp + fn
        out[c] = {
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / support if support else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if support else None,
            "support": support,
        }
    return out


def macro_f1(gold: list[str], pred: list[str]) -> float | None:
    """Mean F1 over classes that appear in the gold labels. None when there are no labels."""
    f1s = [v["f1"] for v in per_class(gold, pred).values() if v["f1"] is not None]
    return sum(f1s) / len(f1s) if f1s else None


def accuracy(gold: list[str], pred: list[str]) -> float | None:
    return sum(g == p for g, p in zip(gold, pred)) / len(gold) if gold else None


def bootstrap_macro_f1(gold: list[str], pred: list[str], n: int = 300, seed: int = 7) -> tuple[float, float] | None:
    """95% interval for macro F1 by resampling reviews. None when there are fewer than 10 labels."""
    if len(gold) < 10:
        return None
    rng = random.Random(seed)
    idx = range(len(gold))
    vals = []
    for _ in range(n):
        pick = [rng.choice(idx) for _ in idx]
        v = macro_f1([gold[i] for i in pick], [pred[i] for i in pick])
        if v is not None:
            vals.append(v)
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[min(int(0.975 * len(vals)), len(vals) - 1)]


def binary_precision_recall(gold: list[bool], flagged: list[bool]) -> dict:
    tp = sum(1 for g, f in zip(gold, flagged) if g and f)
    fp = sum(1 for g, f in zip(gold, flagged) if not g and f)
    fn = sum(1 for g, f in zip(gold, flagged) if g and not f)
    return {"n": len(gold), "true_mismatches": tp + fn, "flagged": tp + fp,
            "precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn) if tp + fn else None}


def calibration(confidences: list[float], correct: list[bool], bins: int = 10) -> dict:
    """Reliability table and expected calibration error: does '90% sure' mean right about 90% of the time?"""
    n = len(confidences)
    if n == 0:
        return {"n": 0, "ece": None, "bins": []}
    rows = []
    ece = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        members = [(c, k) for c, k in zip(confidences, correct) if lo <= c < hi or (b == bins - 1 and c == 1.0)]
        if not members:
            continue
        mc = sum(c for c, _ in members) / len(members)
        acc = sum(k for _, k in members) / len(members)
        ece += len(members) / n * abs(acc - mc)
        rows.append({"lo": lo, "hi": hi, "n": len(members), "mean_confidence": round(mc, 3), "accuracy": round(acc, 3)})
    return {"n": n, "ece": round(ece, 4), "bins": rows}
