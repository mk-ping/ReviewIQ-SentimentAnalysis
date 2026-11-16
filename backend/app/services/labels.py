import re


def label_to_star(label: str):
    """'1 star' ... '5 stars' (nlptown) or 'star 3'. Returns 1-5 or None."""
    low = str(label).lower().replace("_", " ").strip()
    m = re.search(r"\b([1-5])\s*stars?\b", low) or re.search(r"\bstars?\s*([1-5])\b", low)
    return int(m.group(1)) if m else None


def label_to_pol(label: str):
    """negative / neutral / positive, or LABEL_0..2 in that order. Returns 0, 1, 2 or None."""
    low = str(label).lower().replace("_", " ").strip()
    if "neg" in low:
        return 0
    if "neu" in low:
        return 1
    if "pos" in low:
        return 2
    m = re.fullmatch(r"label (\d)", low)
    return int(m.group(1)) if m and int(m.group(1)) < 3 else None


def parse_labels(id2label: dict) -> tuple[str, list[int]]:
    """Returns ('stars', [star per output index]) for 5-class models or ('polarity', [0/1/2 per index]) for 3-class models.
    Refuses to guess: an unmapped label set raises, so a wrong ordering can never be used silently."""
    n = len(id2label)
    if n == 5:
        vals = [label_to_star(id2label[i]) for i in range(5)]
        ok, kind = None not in vals and sorted(vals) == [1, 2, 3, 4, 5], "stars"
    elif n == 3:
        vals = [label_to_pol(id2label[i]) for i in range(3)]
        ok, kind = None not in vals and sorted(vals) == [0, 1, 2], "polarity"
    else:
        raise RuntimeError(f"Expected a 3-class or 5-class model, got {n} classes: {id2label}")
    if not ok:
        raise RuntimeError(f"Cannot map the labels: {id2label}")
    return kind, vals
