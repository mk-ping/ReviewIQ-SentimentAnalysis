# apply_model_swap.ps1 - run from the repo root. Safe to re-run.
$ErrorActionPreference = 'Stop'
if (-not (Test-Path backend\app)) { throw 'Run this from the ReviewIQ repo root.' }

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
New-Item -ItemType Directory -Force -Path (Split-Path $p) | Out-Null
Set-Content -Path $p -Value $c -Encoding ascii
Write-Host 'wrote backend/app/services/model_registry.py'

$p = 'backend\app\services\sentiment.py'
$c = @'
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.services.model_registry import configured, label_to_polarity, label_to_star, runs_on  # noqa: F401

MAX_LEN = 256
_device = "cuda" if torch.cuda.is_available() else "cpu"
_cache: dict = {}


class Scorer:
    def __init__(self, cfg: dict):
        src = cfg["source"]
        self.tok = AutoTokenizer.from_pretrained(src)
        self.model = AutoModelForSequenceClassification.from_pretrained(src).eval().to(_device)
        id2 = self.model.config.id2label
        self.n = len(id2)
        if self.n == 5:
            self.vals = [label_to_star(id2[i]) for i in range(5)]
            ok = None not in self.vals and sorted(self.vals) == [1, 2, 3, 4, 5]
        elif self.n == 3:
            self.vals = [label_to_polarity(id2[i]) for i in range(3)]
            ok = None not in self.vals and sorted(self.vals) == [0, 1, 2]
        else:
            ok = False
        if not ok:
            raise RuntimeError(f"Cannot map the labels of {src}: {id2}")
        self.mapping = {id2[i]: self.vals[i] for i in range(self.n)}

    def predict(self, texts: list[str], batch_size: int = 32):
        out = []
        for i in range(0, len(texts), batch_size):
            enc = self.tok(texts[i : i + batch_size], truncation=True, max_length=MAX_LEN, padding=True,
                           return_tensors="pt").to(_device)
            with torch.no_grad():
                probs = torch.softmax(self.model(**enc).logits, dim=-1).cpu().tolist()
            for row in probs:
                by = dict(zip(self.vals, row))
                if self.n == 5:
                    out.append((by[1] + by[2], by[3], by[4] + by[5], sum(s * p for s, p in by.items())))
                else:
                    out.append((by[0], by[1], by[2], None))
        return out


def get_scorer(cfg: dict) -> Scorer:
    if cfg["name"] not in _cache:
        _cache[cfg["name"]] = Scorer(cfg)
    return _cache[cfg["name"]]


def load():
    """Primary model only (kept for older callers). Returns (device, label -> value mapping)."""
    return _device, get_scorer(configured()[0]).mapping


def predict(texts: list[str], batch_size: int = 32, model: str | None = None):
    """Returns (p_neg, p_neu, p_pos, expected_stars or None) per text. Default is the primary model."""
    cfgs = configured()
    cfg = next((c for c in cfgs if c["name"] == model), cfgs[0]) if model else cfgs[0]
    return get_scorer(cfg).predict(texts, batch_size)
'@
New-Item -ItemType Directory -Force -Path (Split-Path $p) | Out-Null
Set-Content -Path $p -Value $c -Encoding ascii
Write-Host 'wrote backend/app/services/sentiment.py'

$p = 'backend\app\worker\scoring.py'
$c = @'
import asyncio

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import SessionLocal
from app.models import MLModel, Prediction, Review
from app.services import sentiment
from app.services.fusion import score_batch
from app.services.queue import set_progress

CHUNK = 32


async def _model_id(s, cfg: dict) -> int:
    await s.execute(
        pg_insert(MLModel)
        .values(name=cfg["name"], version=cfg["version"], kind="sentiment")
        .on_conflict_do_nothing(index_elements=["name", "version"])
    )
    await s.commit()
    return (await s.execute(select(MLModel.model_id).where(MLModel.name == cfg["name"], MLModel.version == cfg["version"]))).scalar_one()


async def handle_score_all(job_id: int, batch_id: int) -> None:
    cfgs = sentiment.configured()
    todo = []
    async with SessionLocal() as s:
        n_reviews = await s.scalar(select(func.count()).select_from(Review).where(Review.batch_id == batch_id)) or 0
        if n_reviews == 0:
            raise RuntimeError("This batch has no reviews to score.")
        for cfg in cfgs:
            mid = await _model_id(s, cfg)
            q = (
                select(Review.review_id, Review.text_clean)
                .outerjoin(Prediction, and_(Prediction.review_id == Review.review_id, Prediction.model_id == mid))
                .where(Review.batch_id == batch_id, Prediction.review_id.is_(None))
                .order_by(Review.review_id)
            )
            if cfg.get("languages"):  # language_filter: only languages this model was trained on
                q = q.where(Review.language.in_(cfg["languages"]))
            pending = (await s.execute(q)).all()
            todo.append((cfg, mid, pending))

    total = sum(len(p) for _, _, p in todo)
    done = 0
    for idx, (cfg, mid, pending) in enumerate(todo):
        if not pending:
            continue
        try:
            await asyncio.to_thread(sentiment.get_scorer, cfg)
        except Exception as e:
            if idx == 0:
                raise  # the primary model must work
            print(f"[score] skipping {cfg['name']}: {type(e).__name__}: {str(e)[:200]}")
            continue
        for i in range(0, len(pending), CHUNK):
            part = pending[i : i + CHUNK]
            results = await asyncio.to_thread(sentiment.predict, [t for _, t in part], CHUNK, cfg["name"])
            rows = [{"review_id": rid, "model_id": mid, "p_neg": a, "p_neu": b, "p_pos": c, "expected_stars": e}
                    for (rid, _), (a, b, c, e) in zip(part, results)]
            async with SessionLocal() as s:
                await s.execute(pg_insert(Prediction).on_conflict_do_nothing(index_elements=["review_id", "model_id"]), rows)
                await s.commit()
                done += len(part)
                await set_progress(s, job_id, int(100 * done / max(total, 1)))
    async with SessionLocal() as s:
        await score_batch(s, batch_id)
'@
New-Item -ItemType Directory -Force -Path (Split-Path $p) | Out-Null
Set-Content -Path $p -Value $c -Encoding ascii
Write-Host 'wrote backend/app/worker/scoring.py'

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
print("model registry checks passed")
'@
New-Item -ItemType Directory -Force -Path (Split-Path $p) | Out-Null
Set-Content -Path $p -Value $c -Encoding ascii
Write-Host 'wrote backend/tests/check_model_registry.py'

$p = 'backend\tests\check_star_model.py'
$c = @'
"""Downloads nlptown once. Prints the label -> stars mapping and checks ordering on clear examples."""
from app.services.model_registry import STAR_LANGUAGES
from app.services.sentiment import get_scorer

cfg = {"name": "nlptown/bert-base-multilingual-uncased-sentiment",
       "source": "nlptown/bert-base-multilingual-uncased-sentiment", "version": "pretrained",
       "role": "core", "languages": STAR_LANGUAGES}
sc = get_scorer(cfg)
print("label -> stars:", sc.mapping)
assert sorted(sc.mapping.values()) == [1, 2, 3, 4, 5]

bad, ok, good = sc.predict([
    "Terrible. Broke on day one, total waste of money.",
    "It is okay, does the job.",
    "Absolutely fantastic, best purchase I have made this year.",
])
print("expected stars:", round(bad[3], 2), round(ok[3], 2), round(good[3], 2))
assert bad[3] < ok[3] < good[3], "ordering failed - fix label_to_star"
assert bad[0] > bad[2] and good[2] > good[0]
print("star model checks passed")
'@
New-Item -ItemType Directory -Force -Path (Split-Path $p) | Out-Null
Set-Content -Path $p -Value $c -Encoding ascii
Write-Host 'wrote backend/tests/check_star_model.py'

$p = 'docs\DECISIONS.md'
$c = @'
# ReviewIQ decisions

## Models (CPU only, all pretrained)
- Core 1: tabularisai/multilingual-sentiment-analysis (5-class, every language, cc-by-nc-4.0, fine for coursework).
- Core 2: nlptown/bert-base-multilingual-uncased-sentiment (1-5 stars, MIT). Routed by detected language to en, es, fr, de, it, nl only.
  Hindi, Hinglish and undetermined text get no vote from it, because it was not trained on them.
- Optional: cardiffnlp/twitter-xlm-roberta-base-sentiment, enabled by setting cardiff_model.
- We train nothing. The GPU fine-tune (ml/reviewiq_train.py) is retired: it needed a GPU and was not reproducible on a laptop.
- Each model is measured on the hand-labelled gold set and kept only if it beats stars alone and the TF-IDF baseline.

## Fusion
Text score = P(pos) - P(neg). Star score = (stars - 3) / 2. Weight = clip(confidence, 0.4, 0.9).
Fused stars = 3 + 2 * (w * text + (1 - w) * star). Probabilities are averaged over the models that ran for that review.
A mismatch is flagged only when every model that ran agrees on the label.

## Alerts
SPIKE_Z 2.5, SPIKE_MIN_WEEKS 4, SPIKE_MIN_COUNT 5 (core/thresholds.py): chosen defaults, tune on real data.
'@
New-Item -ItemType Directory -Force -Path (Split-Path $p) | Out-Null
Set-Content -Path $p -Value $c -Encoding ascii
Write-Host 'wrote docs/DECISIONS.md'

# config.py: swap star_model_path for star_model (marker-checked)
$p = 'backend\app\core\config.py'
$t = Get-Content $p -Raw
if ($t -notmatch 'star_model:') {
  $t = $t -replace '(?m)^\s*star_model_path: str = .*$', '    star_model: str = "nlptown/bert-base-multilingual-uncased-sentiment"  # empty string disables it'
  Set-Content -Path $p -Value $t -Encoding ascii -NoNewline
  Write-Host 'patched config.py'
} else { Write-Host 'config.py already patched' }

# thresholds.py: add SPIKE_* used by api/explorer.py (marker-checked)
$p = 'backend\app\core\thresholds.py'
$t = Get-Content $p -Raw
if ($t -notmatch 'SPIKE_Z') {
  Add-Content -Path $p -Encoding ascii -Value "`nSPIKE_Z = 2.5             # weekly count this many std above earlier weeks raises an alert`nSPIKE_MIN_WEEKS = 4       # earlier weeks needed before any alert can fire`nSPIKE_MIN_COUNT = 5       # latest week needs at least this many complaints"
  Write-Host 'patched thresholds.py'
} else { Write-Host 'thresholds.py already has SPIKE_*' }

# .env: drop the retired STAR_MODEL_PATH line
$e = 'backend\.env'
if (Test-Path $e) {
  $l = Get-Content $e | Where-Object { $_ -notmatch '^\s*STAR_MODEL_PATH' }
  Set-Content -Path $e -Value $l -Encoding ascii
  Write-Host 'cleaned backend\.env'
}
Write-Host 'done'
