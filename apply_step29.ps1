# Step 29: run from the project root (the folder that contains backend and frontend).
$ErrorActionPreference = 'Stop'

@'
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
'@ | Set-Content -Encoding ascii backend\app\services\extras.py

@'
import json
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dashboard import _ws
from app.core.config import settings
from app.db.session import get_session

router = APIRouter(tags=["extras"])


def _load(name: str, ws: int, command: str) -> dict:
    p = Path(settings.tfidf_path).parent / f"{name}_ws{ws}.json"
    if not p.exists():
        return {"available": False, "command": command}
    try:
        return {"available": True, **json.loads(p.read_text(encoding="utf-8"))}
    except ValueError:
        return {"available": False, "command": command}


@router.get("/extras/absa")
async def absa(session: AsyncSession = Depends(get_session)):
    """The saved result of scripts/absa_validate.py for this workspace."""
    return _load("absa", await _ws(session), "python -m scripts.absa_validate")


@router.get("/extras/topics")
async def topics(session: AsyncSession = Depends(get_session)):
    """The saved result of scripts/topic_discovery.py for this workspace."""
    return _load("topics", await _ws(session), "pip install -r requirements-extra.txt, then python -m scripts.topic_discovery")
'@ | Set-Content -Encoding ascii backend\app\api\extras.py

@'
"""Validates our aspect sentiment against an independent aspect-based sentiment (ABSA) model.
For a sample of tagged English sentences, the ABSA model reads (sentence, aspect) and gives its own
negative / neutral / positive. We report how often it agrees with our score, Cohen's kappa, and a confusion matrix.
Model: yangheng/deberta-v3-base-absa-v1.1 (downloaded once from Hugging Face, about 700 MB, runs on CPU).
Run from backend after sentence aspects exist:  python -m scripts.absa_validate [--workspace 3] [--per-aspect 60]
Writes ../ml/out/absa_ws<N>.json (shown on the Model Checks page) and ../docs/absa_validation.md. Exit code 2 = optional piece missing."""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.services.extras import ABSA_MODEL, absa_label, agreement, band

SQL = """
SELECT sent_id, aspect, sentence, sent_score FROM (
  SELECT sa.sent_id, sa.aspect, sa.sentence, sa.sent_score,
         row_number() OVER (PARTITION BY sa.aspect ORDER BY md5(sa.sent_id::text)) AS rn
  FROM sentence_aspect sa JOIN review r ON r.review_id = sa.review_id
  WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND sa.aspect <> 'general' AND sa.sent_score IS NOT NULL
    AND (r.language = 'en' OR r.language IS NULL)) x
WHERE rn <= :per ORDER BY aspect, rn"""


async def load(ws, per):
    from sqlalchemy import text
    from app.core import thresholds as T
    from app.db.session import SessionLocal
    async with SessionLocal() as s:
        if ws is None:
            ws = (await s.execute(text("SELECT min(workspace_id) FROM workspace"))).scalar()
        rows = (await s.execute(text(SQL), {"ws": ws, "spam": T.SPAM_MAX, "per": per})).all()
    return ws, rows


def run_model(pairs, batch=16):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(ABSA_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(ABSA_MODEL).eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(pairs), batch):
            chunk = pairs[i:i + batch]
            enc = tok([s[:400] for s, _ in chunk], [a for _, a in chunk], padding=True, truncation=True, max_length=128, return_tensors="pt")
            out += [absa_label(model.config.id2label[int(k)]) for k in model(**enc).logits.argmax(-1)]
            print(f"  {min(i + batch, len(pairs))}/{len(pairs)}", end="\r")
    print()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", type=int, default=None)
    ap.add_argument("--per-aspect", type=int, default=60)
    a = ap.parse_args()
    try:
        import torch, transformers  # noqa: F401
    except ImportError:
        print("torch and transformers are needed (they are in requirements.txt). Run: pip install -r requirements.txt")
        return 2
    ws, rows = asyncio.run(load(a.workspace, a.per_aspect))
    if len(rows) < 30:
        print(f"Only {len(rows)} tagged English sentences. Run the aspects analysis on an upload first (Upload page, Run full analysis).")
        return 1
    print(f"Workspace {ws}: checking {len(rows)} sentences with {ABSA_MODEL} ...")
    theirs = run_model([(r.sentence, r.aspect) for r in rows])
    triples = [(r.aspect, band(float(r.sent_score)), t) for r, t in zip(rows, theirs)]
    res = agreement(triples)
    miss = [{"aspect": r.aspect, "sentence": r.sentence[:240], "ours": o, "absa": t}
            for r, (_, o, t) in zip(rows, triples) if t and o != t][:12]
    doc = {"model": ABSA_MODEL, "workspace": ws, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"), **res, "disagreements": miss}
    from app.core.config import settings
    out = Path(settings.tfidf_path).parent / f"absa_ws{ws}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    md = [f"# ABSA validation of aspect sentiment", "", f"Model: `{ABSA_MODEL}`. Sentences checked: {res['n']}.", "",
          f"- Agreement with our scores: **{res['agree_rate']:.1%}**", f"- Cohen's kappa: **{res['kappa']}** (1 = perfect, 0 = chance)", "",
          "| Aspect | Sentences | Agreement |", "| --- | --- | --- |"]
    md += [f"| {d['aspect']} | {d['n']} | {d['agree_rate']:.1%} |" for d in res["by_aspect"]]
    md += ["", "Rows are our label, columns are the ABSA model's label.", "", "| ours \\ ABSA | neg | neu | pos |", "| --- | --- | --- | --- |"]
    md += [f"| {o} | {c['neg']} | {c['neu']} | {c['pos']} |" for o, c in res["confusion"].items()]
    Path("../docs").mkdir(exist_ok=True)
    Path("../docs/absa_validation.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Agreement {res['agree_rate']:.1%}, kappa {res['kappa']}. Saved {out} and ../docs/absa_validation.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'@ | Set-Content -Encoding ascii backend\scripts\absa_validate.py

@'
"""BERTopic-style topic discovery on negative sentences: SBERT embeddings, UMAP, HDBSCAN, c-TF-IDF word lists.
It finds complaint topics the seven aspects may not cover (a topic is 'emerging' when most of its sentences were tagged 'general').
Optional: needs  pip install -r requirements-extra.txt   (bertopic, umap-learn, hdbscan).
Run from backend after sentence aspects exist:  python -m scripts.topic_discovery [--workspace 3] [--limit 20000]
Writes ../ml/out/topics_ws<N>.json (shown on the Model Checks page) and ../docs/topics_ws<N>.md. Exit code 2 = optional packages missing."""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.services.extras import summarise_topics

MIN_SENTENCES = 200

SQL = """
SELECT sa.sentence, sa.aspect FROM sentence_aspect sa JOIN review r ON r.review_id = sa.review_id
WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND sa.sent_score <= :neg AND (r.language = 'en' OR r.language IS NULL)
ORDER BY md5(sa.sent_id::text) LIMIT :lim"""


async def load(ws, lim):
    from sqlalchemy import text
    from app.core import thresholds as T
    from app.db.session import SessionLocal
    async with SessionLocal() as s:
        if ws is None:
            ws = (await s.execute(text("SELECT min(workspace_id) FROM workspace"))).scalar()
        rows = (await s.execute(text(SQL), {"ws": ws, "spam": T.SPAM_MAX, "neg": T.NEG_MENTION, "lim": lim})).all()
    return ws, rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", type=int, default=None)
    ap.add_argument("--limit", type=int, default=20000)
    a = ap.parse_args()
    try:
        from bertopic import BERTopic
        from hdbscan import HDBSCAN
        from sklearn.feature_extraction.text import CountVectorizer
        from umap import UMAP
    except ImportError:
        print("Optional packages missing. Run: pip install -r requirements-extra.txt   (bertopic, umap-learn, hdbscan)")
        return 2
    ws, rows = asyncio.run(load(a.workspace, a.limit))
    docs, aspects = [r.sentence for r in rows], [r.aspect for r in rows]
    if len(docs) < MIN_SENTENCES:
        print(f"Only {len(docs)} negative English sentences; at least {MIN_SENTENCES} are needed. Analyse a bigger upload first.")
        return 1
    from app.core import thresholds as T
    from app.services.embeddings import embed
    print(f"Workspace {ws}: embedding {len(docs)} negative sentences ...")
    import numpy as np
    emb = np.vstack([embed(docs[i:i + 512], T.SBERT_EN_MODEL) for i in range(0, len(docs), 512)])
    model = BERTopic(
        embedding_model=None,
        umap_model=UMAP(n_neighbors=15, n_components=5, min_dist=0.0, metric="cosine", random_state=42),
        hdbscan_model=HDBSCAN(min_cluster_size=max(10, len(docs) // 100), metric="euclidean", cluster_selection_method="eom"),
        vectorizer_model=CountVectorizer(stop_words="english", ngram_range=(1, 2), min_df=2),
        calculate_probabilities=False, verbose=False)
    ids, _ = model.fit_transform(docs, embeddings=emb)
    words = {t: [w for w, _ in model.get_topic(t)[:8]] for t in set(ids) if t != -1}
    res = summarise_topics(docs, [int(i) for i in ids], aspects, words)
    doc = {"workspace": ws, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"), **res}
    from app.core.config import settings
    out = Path(settings.tfidf_path).parent / f"topics_ws{ws}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    md = [f"# Complaint topics (workspace {ws})", "", f"{res['sentences']} negative sentences, {len(res['topics'])} topics, {res['outliers']} outliers.", "",
          "| Topic | Sentences | Top words | Main aspect | Emerging |", "| --- | --- | --- | --- | --- |"]
    md += [f"| {t['topic']} | {t['size']} | {', '.join(t['words'])} | {t['dominant_aspect']} | {'yes' if t['emerging'] else ''} |" for t in res["topics"]]
    Path("../docs").mkdir(exist_ok=True)
    Path(f"../docs/topics_ws{ws}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"{len(res['topics'])} topics, {sum(t['emerging'] for t in res['topics'])} emerging. Saved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'@ | Set-Content -Encoding ascii backend\scripts\topic_discovery.py

@'
bertopic
umap-learn
hdbscan
'@ | Set-Content -Encoding ascii backend\requirements-extra.txt

@'
"""Offline checks for the ABSA agreement and topic summary helpers. Run: python -m tests.check_extras"""
from app.services.extras import absa_label, agreement, band, kappa, summarise_topics

assert band(0.6) == "pos" and band(-0.25) == "neg" and band(0.1) == "neu" and band(0.25) == "pos"
assert absa_label("Positive") == "pos" and absa_label(" NEGATIVE ") == "neg" and absa_label("LABEL_1") is None and absa_label(None) is None

perfect = [("p", "pos", "pos"), ("p", "neg", "neg"), ("q", "neu", "neu"), ("q", "pos", "pos")]
a = agreement(perfect)
assert a["n"] == 4 and a["agree_rate"] == 1.0 and a["kappa"] == 1.0
mixed = [("price", "pos", "pos"), ("price", "pos", "neg"), ("scent", "neg", "neg"), ("scent", "neu", "pos"), ("scent", "neg", "neg"), ("x", "weird", "pos")]
m = agreement(mixed)
assert m["n"] == 5 and m["agree_rate"] == 0.6                        # the unknown label is not counted
assert m["confusion"]["pos"]["neg"] == 1 and m["confusion"]["neu"]["pos"] == 1
assert [d["aspect"] for d in m["by_aspect"]] == ["scent", "price"] and m["by_aspect"][0]["agree_rate"] == 0.667
assert kappa([("pos", "neg"), ("neg", "pos")]) < 0                    # worse than chance
assert kappa([]) is None and agreement([])["agree_rate"] is None

docs = ["box crushed", "arrived damaged", "scent too strong", "smell faint", "app keeps crashing", "login fails", "weird", "?"]
ids = [0, 0, 1, 1, 2, 2, -1, -1]
asp = ["packaging", "packaging", "scent", "scent", "general", "general", "general", "general"]
t = summarise_topics(docs, ids, asp, {0: ["box", "damaged"], 1: ["scent"], 2: ["app", "crash"]})
assert t["outliers"] == 2 and t["outlier_share"] == 0.25 and len(t["topics"]) == 3
by = {x["topic"]: x for x in t["topics"]}
assert by[2]["emerging"] is True and by[0]["emerging"] is False and by[0]["dominant_aspect"] == "packaging"
assert by[2]["words"] == ["app", "crash"] and len(by[0]["examples"]) == 2
print("extras checks passed")
'@ | Set-Content -Encoding ascii backend\tests\check_extras.py

@'
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import Chart from "./Chart";

type Absa = {
  available: boolean; command?: string; model?: string; created?: string; n?: number; agree_rate?: number | null; kappa?: number | null;
  confusion?: Record<string, Record<string, number>>; by_aspect?: { aspect: string; n: number; agree_rate: number }[];
  disagreements?: { aspect: string; sentence: string; ours: string; absa: string }[];
};
type Topics = {
  available: boolean; command?: string; created?: string; sentences?: number; outliers?: number;
  topics?: { topic: number; size: number; words: string[]; dominant_aspect: string; general_share: number; emerging: boolean; examples: string[] }[];
};

const pct = (x: number | null | undefined) => (x == null ? "-" : Math.round(x * 100) + "%");
const NAMES: Record<string, string> = { neg: "Negative", neu: "Neutral", pos: "Positive" };

function Panel({ title, sub, children }: { title: string; sub: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4">
      <h2 className="font-semibold">{title}</h2>
      <p className="mb-3 text-sm text-slate-500">{sub}</p>
      {children}
    </section>
  );
}

function NotRun({ command }: { command?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-500">
      Not run yet for your account. In the backend folder, run:
      <pre className="mt-2 overflow-x-auto rounded bg-slate-100 p-2 text-slate-800">{command}</pre>
      Then reload this page.
    </div>
  );
}

export default function Extras() {
  const absa = useQuery({ queryKey: ["extras-absa"], queryFn: () => api<Absa>("/extras/absa") });
  const topics = useQuery({ queryKey: ["extras-topics"], queryFn: () => api<Topics>("/extras/topics") });
  const a = absa.data, t = topics.data;
  const bars = a?.available && a.by_aspect ? {
    grid: { left: 90, right: 16, top: 10, bottom: 24 }, tooltip: { trigger: "axis" },
    xAxis: { type: "value", max: 100, axisLabel: { formatter: "{value}%" } },
    yAxis: { type: "category", inverse: true, data: a.by_aspect.map((x) => x.aspect) },
    series: [{ type: "bar", data: a.by_aspect.map((x) => Math.round(x.agree_rate * 100)), itemStyle: { color: "#8b7bff" } }],
  } : null;
  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6">
      <header>
        <h1 className="text-2xl font-bold">Model checks</h1>
        <p className="text-slate-500">Two optional checks that run on your machine: an independent model that re-scores our aspect sentiment, and topic discovery for complaints the seven aspects miss.</p>
      </header>

      <Panel title="Aspect sentiment against an ABSA model" sub="An independent aspect-based model reads each sentence with its aspect and gives its own label. High agreement means our sentence scores can be trusted.">
        {absa.isLoading ? <p className="text-slate-500">Loading...</p> : !a?.available ? <NotRun command={a?.command ?? "python -m scripts.absa_validate"} /> : (
          <>
            <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
              <div><div className="text-sm text-slate-500">Sentences checked</div><div className="text-2xl font-semibold">{a.n}</div></div>
              <div><div className="text-sm text-slate-500">Agreement</div><div className="text-2xl font-semibold">{pct(a.agree_rate)}</div></div>
              <div><div className="text-sm text-slate-500">Cohen&apos;s kappa</div><div className="text-2xl font-semibold">{a.kappa ?? "-"}</div><div className="text-xs text-slate-400">1 perfect, 0 chance</div></div>
              <div><div className="text-sm text-slate-500">Model</div><div className="truncate text-sm">{a.model}</div><div className="text-xs text-slate-400">{a.created}</div></div>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div><h3 className="mb-1 text-sm font-medium">Agreement by aspect</h3>{bars && <Chart option={bars as never} height={Math.max(180, 40 + (a.by_aspect?.length ?? 0) * 32)} />}</div>
              <div>
                <h3 className="mb-1 text-sm font-medium">Our label (rows) against the ABSA label (columns)</h3>
                <table className="w-full text-sm"><thead className="text-left text-slate-500"><tr><th></th>{["neg", "neu", "pos"].map((k) => <th key={k}>{NAMES[k]}</th>)}</tr></thead>
                  <tbody>{(Object.entries(a.confusion ?? {}) as [string, Record<string, number>][]).map(([o, row]) => (
                    <tr key={o} className="border-t"><td className="py-1.5 font-medium">{NAMES[o]}</td>{["neg", "neu", "pos"].map((k) => <td key={k} style={o === k ? { color: "#34d399" } : undefined}>{row[k]}</td>)}</tr>
                  ))}</tbody></table>
              </div>
            </div>
            {a.disagreements && a.disagreements.length > 0 && (
              <details className="mt-4 text-sm"><summary className="cursor-pointer text-slate-600">Examples where the two disagree</summary>
                <ul className="mt-2 space-y-2">{a.disagreements.map((d, i) => (
                  <li key={i} className="border-t pt-2"><span className="text-xs text-slate-500">{d.aspect}: we say {NAMES[d.ours]}, ABSA says {NAMES[d.absa]}</span><div>{d.sentence}</div></li>
                ))}</ul></details>
            )}
          </>
        )}
      </Panel>

      <Panel title="Complaint topics (BERTopic style)" sub="Negative sentences are embedded, clustered and named by their top words. Topics marked Emerging are mostly sentences the seven aspects tagged as general, so they point to something new.">
        {topics.isLoading ? <p className="text-slate-500">Loading...</p> : !t?.available ? <NotRun command={t?.command ?? "python -m scripts.topic_discovery"} /> : (
          <>
            <p className="mb-3 text-sm text-slate-500">{t.sentences} negative sentences, {t.topics?.length} topics, {t.outliers} not placed in any topic. {t.created}</p>
            <div className="space-y-3">
              {(t.topics ?? []).map((x) => (
                <div key={x.topic} className="rounded-lg border border-slate-200 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{x.words.slice(0, 4).join(", ") || "Topic " + x.topic}</span>
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{x.size} sentences</span>
                    <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-700">main aspect: {x.dominant_aspect}</span>
                    {x.emerging && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-800">Emerging</span>}
                  </div>
                  <p className="mt-1 text-xs text-slate-400">{x.words.join(", ")}</p>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600">{x.examples.map((e, i) => <li key={i}>{e}</li>)}</ul>
                </div>
              ))}
            </div>
          </>
        )}
      </Panel>
    </div>
  );
}
'@ | Set-Content -Encoding ascii frontend\src\Extras.tsx

@'
# Runs every check and script that needs your machine (database, models, Docker) and writes docs\run_report.txt.
# Run from the project root with the backend venv active and Docker Desktop running:
#   .\tools\run_everything.ps1                 checks, migrations, baseline, held-out evaluation, evidence, ABSA, topics
#   .\tools\run_everything.ps1 -Training       also builds the public training data first (long download)
#   .\tools\run_everything.ps1 -Docker         also builds and starts the full Docker stack and calls /health
# It keeps going after a failure and prints one PASS / FAIL / SKIP line per step at the end.
# Steps that need a person (labelling) are only exported; the real-file upload is done on the Upload page.
param([switch]$Training, [switch]$Docker)
$ErrorActionPreference = 'Continue'
$root = (Get-Location).Path
$report = Join-Path $root 'docs\run_report.txt'
New-Item -ItemType Directory -Force -Path (Join-Path $root 'docs') | Out-Null
("ReviewIQ run report " + (Get-Date -Format 'yyyy-MM-dd HH:mm')) | Out-File -Encoding utf8 $report
$script:results = @()

function Step([string]$name, [scriptblock]$body, [string]$dir = '') {
  Write-Host ("== " + $name) -ForegroundColor Cyan
  if ($dir) { Push-Location (Join-Path $root $dir) }
  $global:LASTEXITCODE = 0
  $out = & $body *>&1 | Out-String
  $code = $LASTEXITCODE
  if ($dir) { Pop-Location }
  ("`n===== " + $name + " (exit " + $code + ")`n" + $out) | Out-File -Append -Encoding utf8 $report
  $status = 'FAIL'
  if ($code -eq 0) { $status = 'PASS' } elseif ($code -eq 2) { $status = 'SKIP' }
  $lines = @($out -split "`r?`n" | Where-Object { $_.Trim() -ne '' })
  $note = ''
  if ($lines.Count -gt 0) { $note = $lines[-1] }
  $colour = 'Red'
  if ($status -eq 'PASS') { $colour = 'Green' } elseif ($status -eq 'SKIP') { $colour = 'Yellow' }
  Write-Host ("   " + $status + "  " + $note) -ForegroundColor $colour
  $script:results += [pscustomobject]@{ Step = $name; Status = $status; Note = $note }
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Write-Host "python not found. Activate the backend venv first." -ForegroundColor Red; exit 1 }

Step 'Database is up' { docker compose up -d db }
Step 'Migrations at head' { python -m alembic upgrade head } 'backend'
Step 'Offline checks (every tests/check_*.py)' { $o = (.\tools\run_checks.ps1 *>&1 | Out-String); Write-Output $o; if (($o -match '([0-9]+) failed') -and ([int]$Matches[1] -gt 0)) { $global:LASTEXITCODE = 1 } else { $global:LASTEXITCODE = 0 } }
if ($Training) { Step 'Build public training data' { python reviewiq_train.py build } 'ml' }
Step 'Train the TF-IDF baseline' { python -m scripts.train_tfidf } 'backend'
Step 'Held-out evaluation table' { python -m scripts.eval_heldout --cap 300 } 'backend'
Step 'Ensemble weights (dry run)' { python -m scripts.calibrate_weights } 'backend'
Step 'Export 100 sentences to hand-check' { python -m scripts.sentence_check export } 'backend'
Step 'Export hidden-dissatisfaction sample' { python -m scripts.hidden_check export } 'backend'
Step 'ABSA validation of aspect sentiment' { python -m scripts.absa_validate } 'backend'
Step 'Topic discovery (BERTopic style)' { python -m scripts.topic_discovery } 'backend'
Step 'EXPLAIN ANALYZE evidence file' { .\tools\make_evidence.ps1 }
if ($Docker) {
  Step 'Docker full stack builds and starts' { docker compose -f docker-compose.full.yml up -d --build }
  Step 'Docker API answers /health' { Start-Sleep -Seconds 20; $r = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8010/health; Write-Output $r.Content; if ($r.StatusCode -ne 200) { $global:LASTEXITCODE = 1 } else { $global:LASTEXITCODE = 0 } }
}

Write-Host ""
Write-Host "Summary" -ForegroundColor Cyan
$table = $script:results | Format-Table -AutoSize -Wrap | Out-String
Write-Host $table
$table | Out-File -Append -Encoding utf8 $report
$fails = @($script:results | Where-Object { $_.Status -eq 'FAIL' }).Count
Write-Host ($fails.ToString() + " step(s) failed. Full output: docs\run_report.txt")
Write-Host "Still done by hand: upload a real file and press Run full analysis, then fill data\sentence_check.csv and data\hidden_check.csv and run the 'score' commands."
'@ | Set-Content -Encoding ascii tools\run_everything.ps1

@'
"""Step 29 patcher. Safe to run twice."""
import io

def edit(path, marker, fn):
    s = io.open(path, encoding="utf-8").read()
    if marker in s:
        print("already applied:", path); return
    s2 = fn(s)
    assert s2 != s, "no change: " + path
    io.open(path, "w", encoding="utf-8", newline="\n").write(s2)
    print("patched:", path)

def once(s, old, new):
    assert s.count(old) == 1, "anchor not found exactly once: " + old[:70]
    return s.replace(old, new)

def main_py(s):
    s = once(s, "from app.api.evaluation import router as evaluation_router\n",
             "from app.api.evaluation import router as evaluation_router\nfrom app.api.extras import router as extras_router\n")
    return once(s, "app.include_router(quality_router, dependencies=protected)\n",
                "app.include_router(quality_router, dependencies=protected)\napp.include_router(extras_router, dependencies=protected)\n")
edit("backend/app/main.py", "extras_router", main_py)

edit("frontend/src/Layout.tsx", "/checks", lambda s: once(s,
    '    { to: "/quality", label: "Data Quality", icon: "check" },\n',
    '    { to: "/quality", label: "Data Quality", icon: "check" },\n    { to: "/checks", label: "Model Checks", icon: "bolt" },\n'))

def main_tsx(s):
    s = once(s, 'import Quality from "./Quality";\n', 'import Quality from "./Quality";\nimport Extras from "./Extras";\n')
    return once(s, '            <Route path="quality" element={<Quality />} />\n',
                '            <Route path="quality" element={<Quality />} />\n            <Route path="checks" element={<Extras />} />\n')
edit("frontend/src/main.tsx", "<Extras", main_tsx)
'@ | Set-Content -Encoding ascii patch_step29.py
python patch_step29.py
Remove-Item patch_step29.py

Write-Host 'Step 29 files written.'
