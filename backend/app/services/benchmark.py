"""Benchmark on public datasets whose sentiment labels were given by people (not derived from star ratings).
Pure helpers: label mapping, group choice, scoring and the markdown table. The script scripts/benchmark_labeled.py does the downloading."""
from app.services import metrics as M

# (key, hub id, config, split, label kind, language, note). kind: 3 = neg/neu/pos, 5 = five levels, 2 = binary.
DATASETS = [
    ("tweet_eval", "cardiffnlp/tweet_eval", "sentiment", "test", "3", "en", "Tweets, 3 classes, people-labelled (SemEval)"),
    ("tweet_sentiment", "mteb/tweet_sentiment_extraction", None, "test", "3", "en", "Tweets, 3 classes, people-labelled"),
    ("sst5", "SetFit/sst5", None, "test", "5", "en", "Movie sentences, 5 levels collapsed to 3"),
    ("sst2", "stanfordnlp/sst2", None, "validation", "2", "en", "Movie sentences, positive or negative"),
    ("yelp_polarity", "fancyzhx/yelp_polarity", None, "test", "2", "en", "Restaurant reviews, positive or negative"),
    ("amazon_polarity", "fancyzhx/amazon_polarity", None, "test", "2", "en", "Product reviews, positive or negative"),
    ("financial_news", "zeroshot/twitter-financial-news-sentiment", None, "validation", "3", "en", "Finance tweets, 3 classes"),
    ("multilingual_hi", "cardiffnlp/tweet_sentiment_multilingual", "hindi", "test", "3", "hi", "Hindi tweets, 3 classes"),
    ("multilingual_es", "cardiffnlp/tweet_sentiment_multilingual", "spanish", "test", "3", "es", "Spanish tweets, 3 classes"),
    ("multilingual_de", "cardiffnlp/tweet_sentiment_multilingual", "german", "test", "3", "de", "German tweets, 3 classes"),
    ("multilingual_fr", "cardiffnlp/tweet_sentiment_multilingual", "french", "test", "3", "fr", "French tweets, 3 classes"),
]
TEXT_COLS = ("text", "sentence", "content", "review", "tweet", "headline")
LABEL_COLS = ("label", "label_text", "sentiment", "labels")
FALLBACK = {"3": ("neg", "neu", "pos"), "5": ("neg", "neg", "neu", "pos", "pos"), "2": ("neg", "pos")}


OVERRIDE = {"financial_news": {0: "neg", 1: "pos", 2: "neu"}}   # that dataset codes 0 bearish, 1 bullish, 2 neutral


def polarity(value, names, kind: str, key: str | None = None) -> str | None:
    """neg, neu or pos for one raw label. names: the dataset's own label names when it has them."""
    if key in OVERRIDE and str(value).isdigit():
        return OVERRIDE[key].get(int(value))
    if isinstance(value, str) and not value.isdigit():
        s = value.lower()
    elif names is not None and 0 <= int(value) < len(names):
        s = str(names[int(value)]).lower()
    else:
        seq = FALLBACK.get(kind)
        try:
            return seq[int(value)] if seq else None
        except (ValueError, IndexError):
            return None
    if "neg" in s or "bear" in s:
        return "neg"
    if "pos" in s or "bull" in s:
        return "pos"
    if "neu" in s:
        return "neu"
    return None


def pick_columns(columns: list[str]) -> tuple[str | None, str | None]:
    low = {c.lower(): c for c in columns}
    return next((low[c] for c in TEXT_COLS if c in low), None), next((low[c] for c in LABEL_COLS if c in low), None)


def stratified(rows: list[tuple], cap: int, seed: int = 7) -> list[tuple]:
    """Up to cap rows with the label mix kept. Rows are (text, label)."""
    import random
    rng = random.Random(seed)
    by: dict = {}
    for r in rows:
        by.setdefault(r[1], []).append(r)
    total = len(rows)
    out = []
    for lab, rs in by.items():
        rng.shuffle(rs)
        out += rs[: max(1, round(cap * len(rs) / total))] if total > cap else rs
    rng.shuffle(out)
    return out[:cap]


def decide(probs: tuple, binary: bool) -> str:
    """The label from (p_neg, p_neu, p_pos). Binary datasets have no neutral, so only negative and positive compete."""
    if binary:
        return "neg" if probs[0] >= probs[2] else "pos"
    return M.LABELS[max(range(3), key=lambda c: probs[c])]


def score_system(gold: list[str], probs: list[tuple], binary: bool) -> dict:
    pred = [decide(p, binary) for p in probs]
    if binary:
        probs = [(p[0], 0.0, p[2]) if (p[0] + p[2]) > 0 else (0.5, 0.0, 0.5) for p in probs]
        probs = [(a / (a + c), 0.0, c / (a + c)) for a, _, c in probs]
    r = M.report(gold, pred, probs)
    r["macro_f1_ci"] = M.bootstrap_ci(M.f_macro, gold, pred)
    r["accuracy_ci"] = M.bootstrap_ci(M.f_acc, gold, pred)
    return r


def f(x, k=3):
    return "-" if x is None else f"{x:.{k}f}"


def table_for(name: str, note: str, n: int, mix: dict, systems: dict) -> list[str]:
    """Markdown block for one dataset. systems: label -> report dict."""
    L = [f"### {name}", "", f"{note}. {n} reviews ({', '.join(f'{k} {v}' for k, v in sorted(mix.items()))}).", "",
         "| System | Accuracy | 95% range | Macro F1 | MCC | Kappa | ROC AUC | ECE | Opposite errors |", "|---|---|---|---|---|---|---|---|---|"]
    for lab, r in systems.items():
        ci = r.get("accuracy_ci")
        L.append(f"| {lab} | {f(r['accuracy'])} | {'-' if not ci else f'{ci[0]:.3f} to {ci[1]:.3f}'} | {f(r['macro_f1'])} | {f(r['mcc'])} | {f(r['kappa'])} | "
                 f"{f(r.get('auc_ovr'))} | {f(r.get('calibration', {}).get('ece'), 4)} | {f(r['opposite_error_rate'])} |")
    return L + [""]
