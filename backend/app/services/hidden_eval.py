"""Precision of Hidden Dissatisfaction from hand-checked reviews. Pure functions, so they test offline."""
import math


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% interval for a share k out of n."""
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def summarise(rows: list[dict], flagged_pop: int | None = None, unflagged_pop: int | None = None) -> dict:
    """rows: {'flagged': bool, 'hidden': bool}. Precision = flagged reviews that really hide a complaint.
    Miss rate = unflagged reviews that really hide one. Recall is estimated only when both population sizes are known."""
    f = [r["hidden"] for r in rows if r["flagged"]]
    u = [r["hidden"] for r in rows if not r["flagged"]]
    out = {"flagged_checked": len(f), "unflagged_checked": len(u),
           "precision": sum(f) / len(f) if f else None, "precision_range": wilson(sum(f), len(f)),
           "miss_rate": sum(u) / len(u) if u else None, "miss_range": wilson(sum(u), len(u)), "recall_estimate": None}
    if f and u and flagged_pop and unflagged_pop:
        tp = out["precision"] * flagged_pop
        fn = out["miss_rate"] * unflagged_pop
        out["recall_estimate"] = tp / (tp + fn) if tp + fn else None
    return out
