# apply_models_training.ps1 - run from the repo root. Safe to re-run.
$ErrorActionPreference = 'Stop'
if (-not (Test-Path backend\app\services\model_registry.py)) { throw 'Run from the repo root, after apply_model_swap.ps1.' }

$p = 'backend\app\services\ablation.py'
$c = @'
"""Does a model earn its place? Pure functions over gold labels, so they can be tested without a database.

Systems are dicts {review_id: 'neg'|'neu'|'pos'}. Everything is compared on the reviews both systems cover,
and a model only 'beats' another when the paired bootstrap interval of the macro-F1 difference is above zero."""
import random

from app.services import evaluation as E


def common_ids(gold: dict[int, str], *systems: dict[int, str]) -> list[int]:
    return sorted(i for i in gold if all(i in s for s in systems))


def mean_fusion(preds: dict[int, list[tuple[float, float, float]]], skip: int | None = None) -> dict[int, str]:
    """What the pipeline does: average the models' probabilities, take the top label. skip drops one model by position."""
    out = {}
    for rid, ps in preds.items():
        use = [p for k, p in enumerate(ps) if k != skip]
        if use:
            n, u, p = (sum(x[i] for x in use) / len(use) for i in range(3))
            out[rid] = E.argmax_label(n, u, p)
    return out


def paired_bootstrap_diff(gold: dict[int, str], a: dict[int, str], b: dict[int, str], n: int = 500, seed: int = 7) -> dict | None:
    """Macro-F1 of a minus b on shared reviews, with a 95% interval. None under 10 shared reviews."""
    ids = common_ids(gold, a, b)
    if len(ids) < 10:
        return None
    rng = random.Random(seed)
    g, pa, pb = [gold[i] for i in ids], [a[i] for i in ids], [b[i] for i in ids]
    diffs = []
    for _ in range(n):
        pick = [rng.randrange(len(ids)) for _ in ids]
        fa = E.macro_f1([g[i] for i in pick], [pa[i] for i in pick])
        fb = E.macro_f1([g[i] for i in pick], [pb[i] for i in pick])
        if fa is not None and fb is not None:
            diffs.append(fa - fb)
    diffs.sort()
    lo, hi = diffs[int(0.025 * len(diffs))], diffs[min(int(0.975 * len(diffs)), len(diffs) - 1)]
    return {"n": len(ids), "f1_a": E.macro_f1(g, pa), "f1_b": E.macro_f1(g, pb), "diff": E.macro_f1(g, pa) - E.macro_f1(g, pb),
            "lo": lo, "hi": hi, "verdict": "beats" if lo > 0 else "worse" if hi < 0 else "no clear difference"}


def stacker_features(stars: float | None, per_model: list[tuple[float, float, float] | None]) -> list[float]:
    """One row per review: each model's three probabilities (zeros plus a missing flag when it did not run), then the star score."""
    row: list[float] = []
    for p in per_model:
        row += list(p) + [0.0] if p else [0.0, 0.0, 0.0, 1.0]
    row += [0.0, 1.0] if stars is None else [(stars - 3) / 2, 0.0]
    return row


def stack_cv(X: list[list[float]], y: list[str], folds: int = 5, seed: int = 7) -> list[str]:
    """Out-of-fold predictions of a small logistic regression on the model outputs. Needs scikit-learn."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict

    counts = {c: y.count(c) for c in set(y)}
    k = max(2, min(folds, min(counts.values())))
    clf = LogisticRegression(max_iter=2000, class_weight="balanced", C=1.0)
    return list(cross_val_predict(clf, X, y, cv=StratifiedKFold(k, shuffle=True, random_state=seed)))
'@
Set-Content -Path $p -Value $c -Encoding ascii
Write-Host 'wrote backend/app/services/ablation.py'

$p = 'backend\scripts\model_ablation.py'
$c = @'
"""Which models earn their place? Compares every model, the pipeline's mean fusion, leave-one-model-out fusion,
stars alone, a TF-IDF baseline and a trained stacker, all on the hand-labelled gold set.
Run from backend:  python -m scripts.model_ablation      (needs scikit-learn; label 200+ reviews first)"""
import asyncio

from sqlalchemy import text

from app.db.session import SessionLocal
from app.services import ablation as A
from app.services import evaluation as E


def _f(x):
    return "  -  " if x is None else f"{x:.3f}"


async def main() -> None:
    async with SessionLocal() as s:
        gold_rows = (await s.execute(text("""
            SELECT g.review_id, g.label, r.text_clean, r.rating_norm FROM gold_label g
            JOIN review r ON r.review_id = g.review_id WHERE g.source = 'gold' ORDER BY g.review_id"""))).all()
        preds = (await s.execute(text("""
            SELECT pr.review_id, m.name, pr.p_neg, pr.p_neu, pr.p_pos FROM prediction pr
            JOIN model m ON m.model_id = pr.model_id JOIN gold_label g ON g.review_id = pr.review_id AND g.source = 'gold'
            ORDER BY m.name"""))).all()
    gold = {r[0]: r[1] for r in gold_rows}
    print(f"gold labels: {len(gold)}")
    if len(gold) < 30:
        print("Fewer than 30 gold labels: numbers below are only a smoke test. Label 200+ for anything you quote.")
    if len(set(gold.values())) < 2:
        print("Need at least two classes. Label more reviews first.")
        return

    names = sorted({p[1] for p in preds})
    by_model: dict[str, dict[int, tuple]] = {n: {} for n in names}
    for rid, name, pn, pu, pp in preds:
        by_model[name][rid] = (pn, pu, pp)
    stars = {r[0]: E.stars_to_label(r[3]) for r in gold_rows if r[3] is not None}

    systems: dict[str, dict[int, str]] = {"stars alone": stars}
    for n in names:
        systems[n] = {i: E.argmax_label(*p) for i, p in by_model[n].items()}
    per_review = {i: [by_model[n][i] for n in names if i in by_model[n]] for i in gold}
    per_review = {i: v for i, v in per_review.items() if v}
    systems["mean fusion (pipeline)"] = A.mean_fusion(per_review)
    if len(names) > 1:
        for k, n in enumerate(names):
            # position k in per_review only lines up when every model ran, so build this one explicitly
            rest = {i: [by_model[m][i] for m in names if m != n and i in by_model[m]] for i in gold}
            systems[f"fusion without {n.split('/')[-1]}"] = A.mean_fusion({i: v for i, v in rest.items() if v})

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline

    texts = {r[0]: r[2] for r in gold_rows}
    ids = sorted(gold)
    counts = {c: list(gold.values()).count(c) for c in set(gold.values())}
    k = max(2, min(5, min(counts.values())))
    pipe = make_pipeline(TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True), LogisticRegression(max_iter=1000, class_weight="balanced"))
    cv = cross_val_predict(pipe, [texts[i] for i in ids], [gold[i] for i in ids], cv=StratifiedKFold(k, shuffle=True, random_state=7))
    systems["TF-IDF + LR (cross-validated)"] = dict(zip(ids, cv))

    star_val = {r[0]: r[3] for r in gold_rows}
    X = [A.stacker_features(star_val[i], [by_model[n].get(i) for n in names]) for i in ids]
    st = A.stack_cv(X, [gold[i] for i in ids])
    systems["stacker (trained, cross-validated)"] = dict(zip(ids, st))

    print(f"\n{'system':44s} {'n':>5s} {'macro F1':>9s} {'95% range':>16s} {'acc':>6s}  vs stars alone   vs TF-IDF")
    for name, sysd in systems.items():
        idl = A.common_ids(gold, sysd)
        g, p = [gold[i] for i in idl], [sysd[i] for i in idl]
        ci = E.bootstrap_macro_f1(g, p)
        rng = f"{ci[0]:.2f}-{ci[1]:.2f}" if ci else "   -"
        v1 = A.paired_bootstrap_diff(gold, sysd, stars) if name != "stars alone" and stars else None
        v2 = A.paired_bootstrap_diff(gold, sysd, systems["TF-IDF + LR (cross-validated)"]) if "TF-IDF" not in name else None
        print(f"{name[:44]:44s} {len(idl):5d} {_f(E.macro_f1(g, p)):>9s} {rng:>16s} {_f(E.accuracy(g, p)):>6s}  "
              f"{(v1 or {}).get('verdict', '-'):16s} {(v2 or {}).get('verdict', '-')}")
    print("\nKeep a model only if it beats stars alone AND the TF-IDF baseline, or if it covers languages the others cannot.")
    print("The stacker is trained on gold labels with cross-validation. Use it in the pipeline only if it beats mean fusion.")


asyncio.run(main())
'@
Set-Content -Path $p -Value $c -Encoding ascii
Write-Host 'wrote backend/scripts/model_ablation.py'

$p = 'backend\scripts\import_gold_labels.py'
$c = @'
"""Bulk-load hand labels from a CSV so you do not have to click through 200 reviews.
CSV columns: text,label   (label is neg, neu or pos; optional column mismatch = 1/0)
The reviews must already be uploaded; each text is matched to a review after the same cleaning the upload uses.
Run from backend:  python -m scripts.import_gold_labels path\\to\\labels.csv
Labels must be a person's judgement of the TEXT. Labels copied from star ratings would make stars look perfect."""
import asyncio
import csv
import sys

from sqlalchemy import text

from app.db.session import SessionLocal
from app.services.cleaning import clean_text

VALID = {"neg", "neu", "pos"}


async def main(path: str) -> None:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows or "text" not in rows[0] or "label" not in rows[0]:
        print("The CSV needs columns named text and label.")
        return
    saved = skipped_label = missing = 0
    async with SessionLocal() as s:
        for r in rows:
            label = (r["label"] or "").strip().lower()
            if label not in VALID:
                skipped_label += 1
                continue
            rid = (await s.execute(text("SELECT review_id FROM review WHERE text_clean = :t ORDER BY review_id LIMIT 1"),
                                   {"t": clean_text(r["text"] or "")})).scalar()
            if rid is None:
                missing += 1
                continue
            mm = r.get("mismatch")
            await s.execute(text("""
                INSERT INTO gold_label (review_id, label, mismatch_label, source) VALUES (:id, :l, :m, 'gold')
                ON CONFLICT (review_id) DO UPDATE SET label = EXCLUDED.label, mismatch_label = EXCLUDED.mismatch_label,
                    source = 'gold', labelled_at = now()"""),
                {"id": rid, "l": label, "m": None if mm in (None, "") else mm.strip() in ("1", "true", "True")})
            saved += 1
        await s.commit()
    print(f"saved {saved} labels; {skipped_label} rows had an invalid label; {missing} texts matched no uploaded review")


if len(sys.argv) != 2:
    print(__doc__)
else:
    asyncio.run(main(sys.argv[1]))
'@
Set-Content -Path $p -Value $c -Encoding ascii
Write-Host 'wrote backend/scripts/import_gold_labels.py'

$p = 'backend\tests\check_ablation.py'
$c = @'
import random

from app.services import ablation as A
from app.services import evaluation as E

rng = random.Random(1)
gold = {i: rng.choice(["neg", "neu", "pos"]) for i in range(120)}


def noisy(acc):
    return {i: g if rng.random() < acc else rng.choice(["neg", "neu", "pos"]) for i, g in gold.items()}


good, bad = noisy(0.9), noisy(0.4)
d = A.paired_bootstrap_diff(gold, good, bad)
assert d["verdict"] == "beats" and d["diff"] > 0.3, d
assert A.paired_bootstrap_diff(gold, bad, good)["verdict"] == "worse"
assert A.paired_bootstrap_diff(gold, good, dict(good))["verdict"] == "no clear difference"
assert A.paired_bootstrap_diff({1: "pos"}, {1: "pos"}, {1: "pos"}) is None

assert A.common_ids(gold, {1: "a", 2: "b"}, {2: "x"}) == [2]
mf = A.mean_fusion({1: [(0.9, 0.05, 0.05), (0.1, 0.1, 0.8)], 2: [(0.0, 0.0, 1.0)]})
assert mf == {1: "neg", 2: "pos"}, mf          # 0.5 neg vs 0.425 pos on average
assert A.mean_fusion({1: [(0.9, 0.05, 0.05), (0.1, 0.1, 0.8)]}, skip=0) == {1: "pos"}

row = A.stacker_features(5, [(0.1, 0.1, 0.8), None])
assert row == [0.1, 0.1, 0.8, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0], row
assert A.stacker_features(None, [])[-2:] == [0.0, 1.0]

try:
    import sklearn  # noqa: F401
except ImportError:
    print("ablation checks passed (stacker skipped: scikit-learn missing)")
else:
    ids = sorted(gold)
    X = [[(1.0 if gold[i] == "neg" else 0.0), (1.0 if gold[i] == "neu" else 0.0), (1.0 if gold[i] == "pos" else 0.0)] for i in ids]
    pred = A.stack_cv(X, [gold[i] for i in ids])
    assert E.accuracy([gold[i] for i in ids], pred) > 0.95
    print("ablation checks passed")
'@
Set-Content -Path $p -Value $c -Encoding ascii
Write-Host 'wrote backend/tests/check_ablation.py'

$p = 'backend\app\services\model_registry.py'
$c = @'
"""Which sentiment models run, which languages each one is routed to, and how their labels parse.

No torch import here, so it can be tested offline.
"""
import re

from app.core.config import settings

# nlptown was trained on product reviews in these languages only.
STAR_LANGUAGES = ("en", "es", "fr", "de", "it", "nl")


def configured(cfg=settings) -> list[dict]:
    """Models to run, primary first. languages=None means every language."""
    out = [{"name": cfg.sentiment_model, "source": cfg.sentiment_model, "version": "pretrained",
            "role": "core", "languages": None}]
    if cfg.star_model:
        out.append({"name": cfg.star_model, "source": cfg.star_model, "version": "pretrained",
                    "role": "core", "languages": STAR_LANGUAGES})
    if cfg.cardiff_model:
        out.append({"name": cfg.cardiff_model, "source": cfg.cardiff_model, "version": "pretrained",
                    "role": "optional", "languages": None})
    for name in [m.strip() for m in (getattr(cfg, "extra_models", "") or "").split(",") if m.strip()]:
        if all(m["name"] != name for m in out):
            out.append({"name": name, "source": name, "version": "pretrained", "role": "optional", "languages": None})
    return out


def runs_on(model_cfg: dict, language: str | None) -> bool:
    """True if this model should vote on a review in this language."""
    langs = model_cfg.get("languages")
    if langs is None:
        return True
    return (language or "und") in langs


def label_to_star(label: str):
    """'1 star', '5 stars', 'LABEL_3' style (1-5), 'Very Negative' ... 'Very Positive'. None if unknown."""
    low = label.lower().replace("_", " ").strip()
    m = re.search(r"\b([1-5])\s*stars?\b", low) or re.search(r"\bstars?\s*([1-5])\b", low)
    if m:
        return int(m.group(1))
    if "very" in low and "neg" in low:
        return 1
    if "very" in low and "pos" in low:
        return 5
    if "neg" in low:
        return 2
    if "neu" in low:
        return 3
    if "pos" in low:
        return 4
    return None


def label_to_polarity(label: str):
    low = label.lower()
    return 0 if "neg" in low else 1 if "neu" in low else 2 if "pos" in low else None
'@
Set-Content -Path $p -Value $c -Encoding ascii
Write-Host 'wrote backend/app/services/model_registry.py'

$p = 'backend\tests\check_model_registry.py'
$c = @'
from types import SimpleNamespace as NS

from app.services.model_registry import configured, label_to_polarity, label_to_star, runs_on

cfg = NS(sentiment_model="p/primary", star_model="s/star", cardiff_model="")
ms = configured(cfg)
assert [m["name"] for m in ms] == ["p/primary", "s/star"], ms
assert ms[0]["role"] == "core" and ms[0]["languages"] is None

assert [m["name"] for m in configured(NS(sentiment_model="p", star_model="", cardiff_model=""))] == ["p"]
assert [m["name"] for m in configured(NS(sentiment_model="p", star_model="s", cardiff_model="c"))] == ["p", "s", "c"]

star = ms[1]
for lang in ("en", "es", "fr", "de", "it", "nl"):
    assert runs_on(star, lang), lang
for lang in ("hi", "hinglish", "und", "ar", "pt", None):
    assert not runs_on(star, lang), lang
assert runs_on(ms[0], "hi") and runs_on(ms[0], None)

assert [label_to_star(x) for x in ["1 star", "2 stars", "3 stars", "4 stars", "5 stars"]] == [1, 2, 3, 4, 5]
assert [label_to_star(x) for x in ["Very Negative", "Negative", "Neutral", "Positive", "Very Positive"]] == [1, 2, 3, 4, 5]
assert label_to_star("LABEL_9") is None
assert [label_to_polarity(x) for x in ["negative", "neutral", "positive"]] == [0, 1, 2]
ex = configured(NS(sentiment_model="p", star_model="s", cardiff_model="", extra_models=" x/one, y/two ,p"))
assert [m["name"] for m in ex] == ["p", "s", "x/one", "y/two"], ex
assert ex[2]["role"] == "optional" and runs_on(ex[2], "hi")
print("model registry checks passed")
'@
Set-Content -Path $p -Value $c -Encoding ascii
Write-Host 'wrote backend/tests/check_model_registry.py'

$p = 'backend\app\core\config.py'
$t = Get-Content $p -Raw
if ($t -notmatch 'extra_models') {
  $t = $t -replace '(?m)^(\s*)cardiff_model: str', ('$1extra_models: str = ""  # comma-separated Hugging Face ids to try as extra optional models' + "`r`n" + '$1cardiff_model: str')
  Set-Content -Path $p -Value $t -Encoding ascii -NoNewline
  Write-Host 'patched config.py'
} else { Write-Host 'config.py already has extra_models' }
Write-Host 'done'
