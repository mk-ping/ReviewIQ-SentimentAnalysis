"""Pure helpers for the sentiment distribution and star-gap views."""

LABELS = ("pos", "neu", "neg")
GAP_BUCKETS = ["over by 2 or more", "over by 1 to 2", "over by 0.5 to 1", "within 0.5", "under by 0.5 to 1", "under by 1 to 2", "under by 2 or more"]


def fold(rows, keep: int | None = None) -> list[dict]:
    """rows of (key, label, count) -> one dict per key with counts and shares, biggest key first."""
    acc: dict = {}
    for key, label, n in rows:
        if label not in LABELS:
            continue
        d = acc.setdefault(key, {"key": key, "pos": 0, "neu": 0, "neg": 0})
        d[label] += int(n)
    out = []
    for d in acc.values():
        total = d["pos"] + d["neu"] + d["neg"]
        d["n"] = total
        for k in LABELS:
            d[k + "_share"] = round(d[k] / total, 3) if total else 0.0
        out.append(d)
    out.sort(key=lambda d: -d["n"])
    return out[:keep] if keep else out


def gap_bucket(gap: float) -> int:
    """Index into GAP_BUCKETS for gap = text-supported stars minus customer stars.
    Negative: the stars are higher than the words (over-rated). Positive: the words are happier (under-rated)."""
    level = 0 if abs(gap) < 0.5 else 1 if abs(gap) < 1 else 2 if abs(gap) < 2 else 3
    if level == 0:
        return 3
    return 3 + level if gap > 0 else 3 - level
