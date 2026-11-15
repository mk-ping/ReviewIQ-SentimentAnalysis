
"""Tune the mismatch thresholds against hand-labelled mismatches (document section 14, build step 7).
Pure functions. A review is flagged when confidence >= conf AND |text score - star score| >= diff."""

MIN_LABELLED = 50     # gold reviews with a mismatch yes/no needed before tuning means anything
MIN_POSITIVES = 10    # and at least this many labelled as real mismatches
DIFFS = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2]
CONFS = [0.5, 0.6, 0.7, 0.8, 0.9]
MIN_PRECISION = 0.7   # document goal: fewer false mismatch flags, so precision first


def text_score_from_fused(fused_stars: float, stars: float, conf: float, w_min: float = 0.4, w_max: float = 0.9) -> float:
    """Inverts fused = 3 + 2 * (w * text + (1 - w) * star_score), with w = clip(conf, w_min, w_max)."""
    w = min(max(conf, w_min), w_max)
    star_score = (stars - 3) / 2
    return ((fused_stars - 3) / 2 - (1 - w) * star_score) / w


def evaluate(rows: list[tuple[bool, float, float, float]], diff: float, conf: float) -> dict:
    """rows: (gold_is_mismatch, text_score, star_score, confidence)."""
    tp = fp = fn = 0
    for gold, t, s, c in rows:
        flag = c >= conf and abs(t - s) >= diff
        tp += gold and flag
        fp += (not gold) and flag
        fn += gold and not flag
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if (tp + fp + fn) else None
    return {"diff": diff, "conf": conf, "flagged": tp + fp, "precision": prec, "recall": rec, "f1": f1}


def tune(rows: list[tuple[bool, float, float, float]]) -> dict:
    n, pos = len(rows), sum(1 for r in rows if r[0])
    if n < MIN_LABELLED or pos < MIN_POSITIVES:
        return {"ok": False, "n": n, "positives": pos,
                "reason": f"Need {MIN_LABELLED}+ labelled reviews with {MIN_POSITIVES}+ real mismatches; have {n} and {pos}."}
    grid = [evaluate(rows, d, c) for d in DIFFS for c in CONFS]
    scored = [g for g in grid if g["f1"] is not None]
    safe = [g for g in scored if g["precision"] is not None and g["precision"] >= MIN_PRECISION]
    pool = safe or scored
    best = max(pool, key=lambda g: (g["f1"], -g["flagged"]))
    return {"ok": True, "n": n, "positives": pos, "best": best, "precision_goal_met": bool(safe),
            "current": evaluate(rows, 0.7, 0.7), "top": sorted(pool, key=lambda g: (-g["f1"], g["flagged"]))[:5]}
