"""Detects Hindi sentiment data whose negative and positive labels are swapped, by counting obvious cue words.
In correctly labelled data, words like 'bekar' or 'kharab' show up in the negative rows more than in the positive rows, and the reverse for 'accha'.
Pure standard library; the same file lives in ml/polarity_fix.py so the data build can use it."""
POS = ["\u0905\u091a\u094d\u091b\u093e", "\u0905\u091a\u094d\u091b\u0940", "\u0905\u091a\u094d\u091b\u0947", "\u092c\u0922\u093c\u093f\u092f\u093e", "\u092c\u0947\u0939\u0924\u0930\u0940\u0928",
       "\u0936\u093e\u0928\u0926\u093e\u0930", "\u092a\u0938\u0902\u0926", "\u0909\u0924\u094d\u0924\u092e", "\u0932\u093e\u091c\u0935\u093e\u092c", "\u092e\u0938\u094d\u0924",
       "\u0916\u0941\u0936", "\u0927\u0928\u094d\u092f\u0935\u093e\u0926", "\u0938\u0941\u0902\u0926\u0930",
       "great", "good", "love", "best", "awesome", "nice", "excellent", "badhiya", "zabardast", "accha", "achha", "mast ", "shandar"]
NEG = ["\u092c\u0947\u0915\u093e\u0930", "\u0916\u0930\u093e\u092c", "\u092c\u0941\u0930\u093e", "\u092c\u0941\u0930\u0940", "\u0918\u091f\u093f\u092f\u093e", "\u0927\u094b\u0916\u093e",
       "\u0928\u093f\u0930\u093e\u0936", "\u0915\u091a\u0930\u093e", "\u092c\u0915\u0935\u093e\u0938", "\u0928\u092b\u0930\u0924", "\u0935\u0947\u0938\u094d\u091f",
       "worst", "bad", "waste", "terrible", "horrible", "bekar", "ghatiya", "kharab", "bakwas", "hate"]
MIN_PER_CLASS = 30
MARGIN = 0.03


def _has(t: str, words: list[str]) -> bool:
    t = t.lower()
    return any(w in t for w in words)


def orientation(rows: list[tuple[str, int]]) -> dict:
    """rows: (text, label) with label 0 = negative, 2 = positive (neutral ignored).
    verdict: 'ok', 'inverted' or 'unclear' (too few rows or no clear difference)."""
    pos = [t for t, y in rows if y == 2]
    neg = [t for t, y in rows if y == 0]
    if len(pos) < MIN_PER_CLASS or len(neg) < MIN_PER_CLASS:
        return {"verdict": "unclear", "score": None, "n_pos": len(pos), "n_neg": len(neg)}
    rate = lambda ts, ws: sum(_has(t, ws) for t in ts) / len(ts)   # noqa: E731
    score = (rate(pos, POS) - rate(neg, POS)) + (rate(neg, NEG) - rate(pos, NEG))
    return {"verdict": "ok" if score > MARGIN else "inverted" if score < -MARGIN else "unclear", "score": round(score, 4),
            "pos_cue_in_pos": rate(pos, POS), "pos_cue_in_neg": rate(neg, POS), "neg_cue_in_neg": rate(neg, NEG), "neg_cue_in_pos": rate(pos, NEG),
            "n_pos": len(pos), "n_neg": len(neg)}


def swap(label: int) -> int:
    return {0: 2, 2: 0}.get(label, label)
