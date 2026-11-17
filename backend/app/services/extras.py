"""Pure helpers for the two optional checks: ABSA validation of aspect sentiment, and BERTopic-style topic discovery.
No database and no model here, so they test offline."""
from collections import Counter, defaultdict

BANDS = ("neg", "neu", "pos")
ABSA_MODEL = "yangheng/deberta-v3-base-absa-v1.1"


def band(score: float, thr: float = 0.25) -> str:
    """Our sentence score (P(pos) - P(neg)) as a label: at or beyond +-thr is positive or negative, between is neutral."""
    return "pos" if score >= thr else "neg" if score <= -thr else "neu"


def absa_label(raw: str | None) -> str | None:
    """The ABSA model's label as neg, neu or pos. Unknown labels return None so they are never counted as agreement."""
    s = (raw or "").strip().lower()
    return {"negative": "neg", "neutral": "neu", "positive": "pos", "neg": "neg", "neu": "neu", "pos": "pos"}.get(s)


def kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Cohen's kappa: agreement beyond what chance alone would give. 1 is perfect, 0 is chance."""
    n = len(pairs)
    if n == 0:
        return None
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in BANDS) / (n * n)
    return None if pe == 1 else round((po - pe) / (1 - pe), 3)


def agreement(rows: list[tuple[str, str, str]]) -> dict:
    """rows of (aspect, ours, theirs) -> overall agreement, kappa, confusion matrix and agreement per aspect."""
    pairs = [(o, t) for _, o, t in rows if o in BANDS and t in BANDS]
    n = len(pairs)
    conf = {o: {t: 0 for t in BANDS} for o in BANDS}
    for o, t in pairs:
        conf[o][t] += 1
    by: dict[str, list[bool]] = defaultdict(list)
    for a, o, t in rows:
        if o in BANDS and t in BANDS:
            by[a].append(o == t)
    return {
        "n": n,
        "agree_rate": round(sum(o == t for o, t in pairs) / n, 3) if n else None,
        "kappa": kappa(pairs),
        "confusion": conf,
        "by_aspect": sorted(({"aspect": a, "n": len(v), "agree_rate": round(sum(v) / len(v), 3)} for a, v in by.items()), key=lambda d: -d["n"]),
    }


def summarise_topics(docs: list[str], topic_ids: list[int], aspects: list[str], words: dict[int, list[str]],
                     examples: int = 3, general_share_min: float = 0.5) -> dict:
    """Groups sentences by topic id (-1 = outliers). A topic is 'emerging' when at least general_share_min of its
    sentences were tagged 'general' by the seven aspects, meaning the aspects do not cover it."""
    groups: dict[int, list[int]] = defaultdict(list)
    for i, t in enumerate(topic_ids):
        groups[t].append(i)
    topics = []
    for t, idx in groups.items():
        if t == -1:
            continue
        asp = Counter(aspects[i] for i in idx)
        general = asp.get("general", 0) / len(idx)
        dominant = asp.most_common(1)[0][0]
        pick = sorted(idx, key=lambda i: abs(len(docs[i]) - 100))[:examples]
        topics.append({"topic": t, "size": len(idx), "words": words.get(t, [])[:8], "dominant_aspect": dominant,
                       "general_share": round(general, 3), "emerging": general >= general_share_min,
                       "examples": [docs[i][:240] for i in pick]})
    topics.sort(key=lambda d: -d["size"])
    outliers = len(groups.get(-1, []))
    return {"sentences": len(docs), "topics": topics, "outliers": outliers,
            "outlier_share": round(outliers / len(docs), 3) if docs else None}
