# Step 23: run from the project root (the folder that contains backend and frontend).
$ErrorActionPreference = 'Stop'

@'
"""Aspect heatmap smoothing (final pipeline document, section 8): (n x cell mean + m x overall mean) / (n + m)."""


def smooth(n: int, cell_mean: float, overall_mean: float, m: int = 10) -> float:
    """Pulls a cell with few mentions toward the overall mean; a cell with many mentions barely moves."""
    return (n * cell_mean + m * overall_mean) / (n + m)
'@ | Set-Content -Encoding ascii backend\app\services\smoothing.py

@'
"""Offline checks for aspect smoothing. Run: python -m tests.check_smoothing"""
from app.services.smoothing import smooth

assert abs(smooth(10, -0.8, 0.2, 10) - (-0.3)) < 1e-9            # equal weight: halfway
assert abs(smooth(1, -1.0, 0.0, 10) - (-1 / 11)) < 1e-9          # one mention barely moves the overall mean
assert abs(smooth(1000, 0.5, 0.0, 10) - 0.5 * 1000 / 1010) < 1e-9
assert smooth(0, 0.9, 0.1, 10) == 0.1                            # no mentions: the overall mean
print("smoothing checks passed")
'@ | Set-Content -Encoding ascii backend\tests\check_smoothing.py

@'
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, send } from "./api";

type Evidence = { review_id: number; sentence: string; stance: string; similarity: number };
type Claim = {
  claim_id: number; claim: string; quote: string | null; aspect: string | null; verdict: string | null;
  supports: number | null; contradicts: number | null; support_share: number | null; evidence: Evidence[]; action: string | null;
};
type Product = { product_id: number; name: string; reviews: number; embedded: number };

const VERDICT: Record<string, { label: string; cls: string }> = {
  confirmed: { label: "Confirmed by reviews", cls: "bg-emerald-100 text-emerald-800" },
  contradicted: { label: "Contradicted by reviews", cls: "bg-red-100 text-red-800" },
  mixed: { label: "Mixed evidence", cls: "bg-amber-100 text-amber-800" },
  not_enough_evidence: { label: "Not enough evidence", cls: "bg-slate-100 text-slate-600" },
};

export default function Listing() {
  const qc = useQueryClient();
  const products = useQuery({ queryKey: ["products"], queryFn: () => api<{ products: Product[] }>("/products") });
  const [pid, setPid] = useState<number | "">("");
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const claims = useQuery({
    queryKey: ["claims", pid], enabled: pid !== "",
    queryFn: async () => { try { return await api<{ claims: Claim[] }>(`/products/${pid}/claims`); } catch { return { claims: [] as Claim[] }; } },
  });
  const prod = (products.data?.products ?? []).find((p) => p.product_id === pid);

  async function check() {
    if (pid === "") return;
    setBusy(true); setError(""); setNote("");
    try {
      const r = await send<{ note: string }>("POST", `/products/${pid}/listing`, { source_text: source });
      setNote(r.note);
      await qc.invalidateQueries({ queryKey: ["claims", pid] });
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  const list = claims.data?.claims ?? [];
  const contradicted = list.filter((c) => c.verdict === "contradicted").length;
  return (
    <div className="mx-auto max-w-4xl space-y-5 p-6">
      <header>
        <h1 className="text-2xl font-bold">Listing vs Reality</h1>
        <p className="text-slate-600">Paste a product listing. Each promise in it is checked against what customers wrote.</p>
      </header>

      <section className="space-y-3 rounded-xl bg-white p-4 shadow-sm">
        <label className="block text-sm">Product
          <select className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-2 py-1" value={pid}
            onChange={(e) => setPid(e.target.value ? Number(e.target.value) : "")}>
            <option value="">Choose a product</option>
            {(products.data?.products ?? []).map((p) => <option key={p.product_id} value={p.product_id}>{p.name} ({p.reviews} reviews)</option>)}
          </select>
        </label>
        {prod && prod.embedded === 0 && (
          <p className="rounded-md bg-amber-50 p-2 text-sm text-amber-700">This product's reviews are not indexed yet. Run the full analysis for its upload first (Sentiment page).</p>
        )}
        <textarea className="h-40 w-full rounded-md border border-slate-300 p-2 text-sm" placeholder="Paste the listing title, bullets and description here"
          value={source} onChange={(e) => setSource(e.target.value)} />
        <div className="flex items-center gap-3">
          <button className="rounded-md bg-indigo-600 px-3 py-1 text-sm text-white disabled:opacity-50"
            disabled={busy || pid === "" || source.trim().length < 20} onClick={check}>{busy ? "Checking claims..." : "Check the claims"}</button>
          {busy && <span className="text-sm text-slate-500">This can take a few minutes. A local language model reads every claim.</span>}
        </div>
        {error && <p className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      </section>

      {pid !== "" && list.length === 0 && !claims.isLoading && <p className="text-sm text-slate-500">No claims checked for this product yet.</p>}
      {list.length > 0 && (
        <p className="text-sm text-slate-600">{list.length} claims checked; {contradicted} contradicted by reviews.</p>
      )}
      <ul className="space-y-3">
        {list.map((c) => {
          const v = VERDICT[c.verdict ?? "not_enough_evidence"] ?? VERDICT.not_enough_evidence;
          return (
            <li key={c.claim_id} className="rounded-xl bg-white p-4 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium">{c.claim}</p>
                <span className={"rounded-full px-2 py-0.5 text-xs " + v.cls}>{v.label}</span>
              </div>
              {c.quote && <p className="mt-1 text-xs text-slate-400">Listing says: &ldquo;{c.quote}&rdquo;</p>}
              <p className="mt-1 text-sm text-slate-600">
                {c.aspect ? `About ${c.aspect}. ` : ""}
                {c.supports ?? 0} supporting and {c.contradicts ?? 0} contradicting review sentences
                {c.support_share != null ? ` (${Math.round(c.support_share * 100)}% support).` : "."}
              </p>
              {c.action && <p className="mt-1 rounded-md bg-red-50 p-2 text-sm text-red-700">Suggested: {c.action}</p>}
              {c.evidence.length > 0 && (
                <ul className="mt-2 space-y-1 text-sm">
                  {c.evidence.map((e, i) => (
                    <li key={i} className="flex gap-2">
                      <span className={e.stance === "supports" ? "text-emerald-600" : "text-red-600"}>{e.stance === "supports" ? "supports" : "contradicts"}</span>
                      <span className="text-slate-700">&ldquo;{e.sentence}&rdquo;</span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
      {note && <p className="text-xs text-slate-400">{note}</p>}
    </div>
  );
}
'@ | Set-Content -Encoding ascii frontend\src\Listing.tsx

@'
# ReviewIQ decisions

These follow the final pipeline document (Nov 14). The older model-swap notes are replaced.

## Models (CPU only, nothing needs an API key)
- We train one model: TF-IDF + Logistic Regression (single words and word pairs, min_df 3, 50,000 features, balanced classes),
  trained on public sources and saved as ml/out/tfidf_lr.joblib. Every other model is pretrained and downloaded once.
- English: TF-IDF, cardiffnlp/twitter-roberta-base-sentiment-latest, nlptown/bert-base-multilingual-uncased-sentiment.
- Spanish, French, German, Italian, Dutch: TF-IDF, nlptown, cardiffnlp/twitter-xlm-roberta-base-sentiment.
- Hindi, Hinglish, undetermined: TF-IDF, Twitter XLM-RoBERTa, multilingual DistilBERT.
  nlptown does not cover Hindi, so Hindi reviews never get a vote from it and the star gap shows as not available.
- Dropped: tabularisai as a core model, the fine-tuned GPU star model, and the rule that every model must agree before a
  mismatch is flagged.
- Route groups and per-group weights are designs validated by ablation on the gold set, not results.

## Ensemble and fusion
- Ensemble weight = validation macro F1 of each model in the route group. Groups with fewer than 100 validation reviews use equal weights.
  Uploads with fewer than 300 rated reviews use the stored default weights. With 200 or more gold labels, weights are recomputed against them.
- Text score = P(pos) - P(neg). Star score = (stars - 3) / 2. Confidence = highest ensemble probability; w = clip(confidence, 0.4, 0.9).
- Fused = w x text + (1 - w) x star; fused stars = 3 + 2 x fused.
- Mismatch: confidence >= 0.7 and abs(text - star) >= 0.7 (tuned on gold labels, see tune_thresholds). Star gap: nlptown expected stars minus actual; flag at abs >= 1.5.

## Aspects
- pysbd sentences (fragments under 2 words dropped); seven aspects with 6 seed phrases each (config/aspect_config.py).
- SBERT: all-MiniLM-L6-v2 for English, paraphrase-multilingual-MiniLM-L12-v2 for the rest. A sentence gets every aspect at cosine 0.35 or more;
  otherwise a keyword check on word starts; otherwise general. The LLM never replaces the SBERT tags.
- Sentence sentiment: RoBERTa for English, Twitter XLM-RoBERTa for other route groups.
- The aspect view smooths each cell with (n x cell mean + 10 x overall mean) / (n + 10).
- review_aspect is derived from sentence_aspect so Hidden Dissatisfaction and the issues keep one reading path.

## Issues
- Problem sentences: sentiment -0.25 or lower. An aspect needs 30 of them for per-aspect KMeans (k 2 to 4, silhouette picks k, clusters named by c-TF-IDF,
  rare complaints beyond mean + 2 std). Fewer than 30 gives one issue marked few sentences.
- English and non-English sentences are clustered separately because their vectors come from different models.

## Embeddings
- One vector per review with a model column; search compares only vectors from the same model. HNSW index on 384-number vectors.

## Reports
- reportlab for the PDF and openpyxl for Excel, so nothing needs a system library.
- Alerts: SPIKE_Z 2.5, SPIKE_MIN_WEEKS 4, SPIKE_MIN_COUNT 5 (core/thresholds.py): chosen defaults, tune on real data.

## Retired
- The GPU fine-tuning path. ml/reviewiq_train.py is kept only for its build and baseline commands (public-source data build for TF-IDF training and the held-out evaluation).
'@ | Set-Content -Encoding ascii docs\DECISIONS.md

@'
"""Step 23 patcher (Listing page, aspect smoothing, cleanup of retired code). Safe to run twice."""
import io

def edit(path, marker, fn):
    s = io.open(path, encoding="utf-8").read()
    if marker in s:
        print("already applied:", path); return
    s2 = fn(s); assert s2 != s, "no change: " + path
    io.open(path, "w", encoding="utf-8", newline="\n").write(s2); print("patched:", path)

def once(s, old, new):
    assert s.count(old) == 1, "anchor not found exactly once: " + old[:80]
    return s.replace(old, new)

edit("backend/app/core/thresholds.py", "\nASPECT_M = ", lambda s: s.rstrip("\n") + "\n\nASPECT_M = 10             # aspect heatmap smoothing: (n x cell mean + m x overall mean) / (n + m)\n")

def insights(s):
    s = once(s, "from app.services.true_rating import true_rating\n", "from app.services.smoothing import smooth\nfrom app.services.true_rating import true_rating\n")
    old = '''    return {"aspects": [
        {"aspect": name, "mentions": n, "reviews": nr, "avg_sentiment": round(float(avg), 2),
         "negative": neg, "positive": pos, "neutral": n - neg - pos, "low_sample": n < T.LOW_SAMPLE}
        for name, n, nr, avg, neg, pos in rows
    ]}'''
    new = '''    total = sum(r[1] for r in rows)
    overall = sum(r[1] * float(r[3]) for r in rows) / total if total else 0.0
    return {"smoothing_m": T.ASPECT_M, "aspects": [
        {"aspect": name, "mentions": n, "reviews": nr, "avg_sentiment": round(float(avg), 2),
         "smoothed_sentiment": round(smooth(n, float(avg), overall, T.ASPECT_M), 2),
         "negative": neg, "positive": pos, "neutral": n - neg - pos, "low_sample": n < T.LOW_SAMPLE}
        for name, n, nr, avg, neg, pos in rows
    ]}'''
    return once(s, old, new)
edit("backend/app/api/insights.py", "smoothed_sentiment", insights)

edit("frontend/src/api.ts", "smoothed_sentiment", lambda s: once(s, "  aspect: string; mentions: number; reviews: number; avg_sentiment: number;\n",
                                                               "  aspect: string; mentions: number; reviews: number; avg_sentiment: number; smoothed_sentiment?: number;\n"))

def aspects_tsx(s):
    s = once(s, "  const rows = [...a.data.aspects].sort((x, y) => x.avg_sentiment - y.avg_sentiment);\n",
             "  const sm = (r: { avg_sentiment: number; smoothed_sentiment?: number }) => r.smoothed_sentiment ?? r.avg_sentiment;\n  const rows = [...a.data.aspects].sort((x, y) => sm(x) - sm(y));\n")
    s = once(s, 'name: "average sentiment"', 'name: "smoothed average sentiment"')
    s = once(s, 'data: rows.map((r) => ({ value: r.avg_sentiment, itemStyle: { color: r.avg_sentiment < -0.25 ? "#dc2626" : r.avg_sentiment > 0.25 ? "#16a34a" : "#94a3b8" } })),',
             'data: rows.map((r) => ({ value: sm(r), itemStyle: { color: sm(r) < -0.25 ? "#dc2626" : sm(r) > 0.25 ? "#16a34a" : "#94a3b8" } })),')
    s = once(s, "<th>Negative</th></tr></thead>", "<th>Negative</th><th>Raw average</th></tr></thead>")
    return once(s, "<td>{r.negative}</td>\n", "<td>{r.negative}</td><td>{r.avg_sentiment.toFixed(2)}</td>\n")
edit("frontend/src/Aspects.tsx", "smoothed average", aspects_tsx)

def layout(s):
    return once(s, '  { to: "/reports", label: "Reports and Replies", ready: true },\n',
                '  { to: "/listing", label: "Listing vs Reality", ready: true },\n  { to: "/reports", label: "Reports and Replies", ready: true },\n')
edit("frontend/src/Layout.tsx", "/listing", layout)

def main_tsx(s):
    s = once(s, 'import Sentiment from "./Sentiment";\n', 'import Sentiment from "./Sentiment";\nimport Listing from "./Listing";\n')
    return once(s, '            <Route path="reports" element={<Reports />} />\n',
                '            <Route path="reports" element={<Reports />} />\n            <Route path="listing" element={<Listing />} />\n')
edit("frontend/src/main.tsx", "<Listing", main_tsx)

def handlers(s):
    a = s.index("async def _model_id(s) -> int:"); b = s.index("async def _aspect_ids(")
    s = s[:a] + s[b:]
    a = s.index("async def handle_aspects(job_id"); b = s.index("async def handle_issues(")
    s = s[:a] + s[b:]
    a = s.index("async def handle_embed(job_id"); b = s.index("from app.worker.scoring import handle_score_all")
    return s[:a] + s[b:]
edit("backend/app/worker/handlers.py", "# retired-handlers-removed", lambda s: handlers(s).rstrip("\n") + "\n# retired-handlers-removed: the review-level LLM aspect stage, single-model score and old embed stage live in scoring.py, aspects_sbert.py, embed_models.py\n")

edit("backend/app/core/config.py", "# no sentiment_model", lambda s: once(s, '    sentiment_model: str = "tabularisai/multilingual-sentiment-analysis"\n', "    # no sentiment_model: the model list comes from services/sentiment.registry()\n"))
'@ | Set-Content -Encoding ascii patch_step23.py
python patch_step23.py
Remove-Item patch_step23.py

Write-Host 'Step 23 files written.'
