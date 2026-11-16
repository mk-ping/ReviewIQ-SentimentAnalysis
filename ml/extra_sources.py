"""Six extra public datasets for the baseline. Every loader skips itself with a message if the download fails.
Star datasets give star labels (0-4). Polarity datasets give neg/neu/pos (0/1/2); binary ones skip neutral."""
import random

SEED = 7

# (hf id, config or None, kind, language, label->star/pol map)
SOURCES = [
    ("SetFit/sst5",                          None, "star", "en", None),
    ("mteb/amazon_reviews_multi",            "de", "star", "de", None),
    ("mteb/amazon_reviews_multi",            "es", "star", "es", None),
    ("mteb/amazon_reviews_multi",            "fr", "star", "fr", None),
    ("stanfordnlp/imdb",                     None, "pol",  "en", {0: 0, 1: 2}),
    ("cornell-movie-review-data/rotten_tomatoes", None, "pol", "en", {0: 0, 1: 2}),
    ("mteb/tweet_sentiment_extraction",      None, "pol",  "en", {0: 0, 1: 1, 2: 2}),
    ("Sp1786/multiclass-sentiment-analysis-dataset", None, "pol", "en", {0: 0, 1: 1, 2: 2}),
]


def load_extra(per_source, row, norm, keep):
    from datasets import load_dataset
    out = []
    for hid, cfg, kind, lang, mp in SOURCES:
        name = hid.split("/")[-1] + (":" + cfg if cfg else "")
        try:
            ds = load_dataset(hid, cfg) if cfg else load_dataset(hid)
        except Exception as e:
            print(f"  skip {name}: {type(e).__name__}: {str(e)[:100]}")
            continue
        rows = []
        for sp in ds:
            d = ds[sp]
            cols = d.column_names
            tcol = "text" if "text" in cols else next((c for c in cols if c.lower() in ("sentence", "review", "content")), None)
            lcol = "label" if "label" in cols else next((c for c in cols if c.lower() in ("labels", "sentiment")), None)
            if not tcol or not lcol:
                print(f"  skip {name}/{sp}: columns {cols}")
                continue
            for ex in d:
                t = norm(str(ex[tcol]))
                try:
                    v = int(ex[lcol])
                except (TypeError, ValueError):
                    continue
                if not keep(t):
                    continue
                if kind == "star":
                    if 0 <= v <= 4:
                        rows.append(row(t, star=v, src=name, lang=lang))
                elif v in (mp or {}):
                    rows.append(row(t, pol=mp[v], src=name, lang=lang))
        random.Random(SEED).shuffle(rows)
        out += rows[:per_source]
        print(f"  {name}: {len(rows[:per_source])} rows")
    return out