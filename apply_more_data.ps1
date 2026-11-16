# Run from the repo root. Re-runnable. Adds 6 more training datasets to ml\reviewiq_train.py build. No migration.
$f = "ml\reviewiq_train.py"
if (-not (Test-Path $f)) { Write-Host "Run this from the ReviewIQ repo root."; exit 1 }

$py = @'
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
'@
[IO.File]::WriteAllText("ml\extra_sources.py", $py, (New-Object Text.UTF8Encoding($false)))

$t = [IO.File]::ReadAllText($f)
if ($t -match "load_extra") { Write-Host "reviewiq_train.py already patched."; exit 0 }
$a1 = '    pool += load_hindi(a.hindi_total)'
$a2 = '    p.add_argument("--hindi-total", type=int, default=6000)'
if (($t.IndexOf($a1) -lt 0) -or ($t.IndexOf($a2) -lt 0)) { Write-Host "Anchors not found; no change made to reviewiq_train.py."; exit 1 }
$t = $t.Replace($a1, $a1 + "`n    print(`"Extra datasets`")`n    from extra_sources import load_extra`n    pool += load_extra(a.extra_per_source, row, norm, keep)")
$t = $t.Replace($a2, $a2 + "`n    p.add_argument(`"--extra-per-source`", type=int, default=3000)")
[IO.File]::WriteAllText($f, $t, (New-Object Text.UTF8Encoding($false)))
Write-Host "Done. Now: cd ml ; python reviewiq_train.py build ; then from backend: python -m scripts.train_tfidf"
