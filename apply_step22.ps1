# Step 22: run from the project root (the folder that contains backend and frontend).
$ErrorActionPreference = 'Stop'

@'
"""Results CSV for one upload. Pure functions, so they test offline."""
import csv
import io

BASE = ["review_id", "product", "stars_raw", "stars", "language", "date", "text", "spam_score",
        "sentiment", "confidence", "text_adjusted_stars", "expected_stars", "star_gap", "mismatch"]


def safe_cell(v):
    """Stops a spreadsheet from running a review that starts with = + - or @ as a formula."""
    if v is None:
        return ""
    s = str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") and not _is_number(s) else s


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def short_model(name: str) -> str:
    return (name or "model").split("/")[-1]


def vote_label(p_neg: float, p_neu: float, p_pos: float) -> str:
    """Same tie rule as fusion: negative wins ties, then neutral."""
    conf = max(p_neg, p_neu, p_pos)
    return "neg" if conf == p_neg else ("neu" if conf == p_neu else "pos")


def build_csv(rows: list[tuple], votes: dict[int, dict[str, str]]) -> str:
    """rows follow BASE order. votes maps review_id -> {model short name: label}."""
    models = sorted({m for v in votes.values() for m in v})
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(BASE + [f"vote_{m}" for m in models])
    for r in rows:
        v = votes.get(r[0], {})
        w.writerow([safe_cell(c) for c in r] + [v.get(m, "") for m in models])
    return chr(0xFEFF) + out.getvalue()
'@ | Set-Content -Encoding ascii backend\app\services\export_csv.py

@'
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dashboard import _ws
from app.db.session import get_session
from app.models import UploadBatch
from app.services.export_csv import build_csv, short_model, vote_label

router = APIRouter(tags=["sentiment"])


@router.get("/sentiment/uploads")
async def sentiment_uploads(session: AsyncSession = Depends(get_session)):
    """Every upload with how far it has been analysed, so a manager can return to earlier results."""
    ws = await _ws(session)
    rows = (await session.execute(text("""
        SELECT b.batch_id, b.file_name, b.status, b.created_at, b.rows_total, b.rows_rejected,
               count(r.review_id) AS reviews, count(s.review_id) AS scored,
               count(u.review_id) AS aspects_done, count(e.review_id) AS embedded,
               count(*) FILTER (WHERE s.text_label = 'pos') AS pos,
               count(*) FILTER (WHERE s.text_label = 'neu') AS neu,
               count(*) FILTER (WHERE s.text_label = 'neg') AS neg
        FROM upload_batch b
        LEFT JOIN review r ON r.batch_id = b.batch_id
        LEFT JOIN review_score s ON s.review_id = r.review_id
        LEFT JOIN review_aspect_run u ON u.review_id = r.review_id
        LEFT JOIN review_embedding e ON e.review_id = r.review_id
        WHERE b.workspace_id = :ws GROUP BY b.batch_id ORDER BY b.batch_id DESC"""), {"ws": ws})).mappings().all()
    return {"uploads": [{**dict(r), "created_at": r["created_at"].isoformat()} for r in rows]}


@router.get("/uploads/{batch_id}/votes")
async def model_votes(batch_id: int, session: AsyncSession = Depends(get_session)):
    """What each model voted for this upload (its own most likely class per review)."""
    if await session.get(UploadBatch, batch_id) is None:
        raise HTTPException(404, "Upload not found.")
    rows = (await session.execute(text("""
        SELECT m.name, m.version, count(*) AS reviews,
               count(*) FILTER (WHERE p.p_neg >= p.p_neu AND p.p_neg >= p.p_pos) AS neg,
               count(*) FILTER (WHERE p.p_neu > p.p_neg AND p.p_neu >= p.p_pos) AS neu,
               count(*) FILTER (WHERE p.p_pos > p.p_neg AND p.p_pos > p.p_neu) AS pos,
               avg(p.expected_stars) AS avg_expected_stars
        FROM prediction p JOIN model m ON m.model_id = p.model_id JOIN review r ON r.review_id = p.review_id
        WHERE r.batch_id = :b GROUP BY m.model_id, m.name, m.version ORDER BY m.name"""), {"b": batch_id})).all()
    return {"models": [{"model": short_model(n), "version": v, "reviews": c, "neg": ng, "neu": nu, "pos": ps,
                        "avg_expected_stars": None if a is None else round(float(a), 2)} for n, v, c, ng, nu, ps, a in rows]}


@router.get("/uploads/{batch_id}/results.csv")
async def results_csv(batch_id: int, session: AsyncSession = Depends(get_session)):
    batch = await session.get(UploadBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "Upload not found.")
    rows = (await session.execute(text("""
        SELECT r.review_id, p.name, r.rating_raw, r.rating_norm, r.language, r.review_date, r.text_clean, r.spam_score,
               s.text_label, s.confidence, s.fused_stars, s.pred_stars, s.star_gap, s.mismatch_type
        FROM review r JOIN product p ON p.product_id = r.product_id
        LEFT JOIN review_score s ON s.review_id = r.review_id
        WHERE r.batch_id = :b ORDER BY r.review_id"""), {"b": batch_id})).all()
    preds = (await session.execute(text("""
        SELECT p.review_id, m.name, p.p_neg, p.p_neu, p.p_pos
        FROM prediction p JOIN model m ON m.model_id = p.model_id JOIN review r ON r.review_id = p.review_id
        WHERE r.batch_id = :b"""), {"b": batch_id})).all()
    votes: dict[int, dict[str, str]] = {}
    for rid, name, n, u, pp in preds:
        votes.setdefault(rid, {})[short_model(name)] = vote_label(n, u, pp)
    body = build_csv([tuple(r) for r in rows], votes)
    stem = (batch.file_name or f"upload_{batch_id}").rsplit(".", 1)[0][:60] or f"upload_{batch_id}"
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{safe}_results.csv"'})
'@ | Set-Content -Encoding ascii backend\app\api\sentiment.py

@'
"""Offline checks for the results CSV. Run: python -m tests.check_export_csv"""
import csv
import io

from app.services.export_csv import BASE, build_csv, safe_cell, short_model, vote_label

assert vote_label(0.5, 0.3, 0.2) == "neg" and vote_label(0.2, 0.5, 0.3) == "neu" and vote_label(0.1, 0.2, 0.7) == "pos"
assert vote_label(0.4, 0.4, 0.2) == "neg"                      # ties: negative first, same rule as fusion
assert short_model("cardiffnlp/twitter-roberta-base-sentiment-latest") == "twitter-roberta-base-sentiment-latest"
assert safe_cell("=SUM(A1)") == chr(39) + "=SUM(A1)" and safe_cell("@x") == chr(39) + "@x" and safe_cell("-5") == "-5" and safe_cell(None) == ""
assert safe_cell("Great product") == "Great product"

rows = [(1, "Lip balm", "5", 5.0, "en", None, "Loved it, really", 0.0, "pos", 0.9, 4.9, 4.7, -0.3, None),
        (2, "Lip balm", "1", 1.0, "hi", None, "=HYPERLINK(\"x\")", 0.0, "neg", 0.8, 1.2, None, None, None)]
votes = {1: {"roberta": "pos", "nlptown": "pos"}, 2: {"xlmr": "neg"}}
text = build_csv(rows, votes)
assert text.startswith(chr(0xFEFF))
parsed = list(csv.reader(io.StringIO(text.lstrip(chr(0xFEFF)))))
assert parsed[0] == BASE + ["vote_nlptown", "vote_roberta", "vote_xlmr"], parsed[0]
assert parsed[1][6] == "Loved it, really" and parsed[1][-3:] == ["pos", "pos", ""], parsed[1]
assert parsed[2][6].startswith(chr(39) + "=") and parsed[2][-1] == "neg"
assert len(parsed) == 3 and all(len(r) == len(parsed[0]) for r in parsed)
print("results CSV checks passed")
'@ | Set-Content -Encoding ascii backend\tests\check_export_csv.py

@'
export type Job = { job_id: number; status: string; progress: number; error: string | null };

export async function call(method: string, path: string) {
  const r = await fetch("/api" + path, { method });
  let data: any = null;
  try { data = await r.json(); } catch { /* not json */ }
  return { ok: r.ok, status: r.status, data };
}

export function runJob(jobId: number, onProgress: (j: Job) => void): Promise<Job> {
  return new Promise((resolve, reject) => {
    const es = new EventSource(`/api/jobs/${jobId}/events`);
    es.onmessage = (e) => {
      const j = JSON.parse(e.data) as Job;
      onProgress(j);
      if (j.status === "done") { es.close(); resolve(j); }
      if (j.status === "failed") { es.close(); reject(new Error(j.error ?? "Job failed")); }
    };
    es.onerror = () => { es.close(); reject(new Error("Lost the progress stream. Is the worker running?")); };
  });
}

// Stage names double as the API path: POST /uploads/{id}/{stage}
export const ALL_STAGES = ["score", "aspects", "issues", "embed"] as const;
export const STAGE_LABEL: Record<string, string> = {
  score: "Reading sentiment", aspects: "Finding aspects", issues: "Grouping problems", embed: "Indexing for search",
};
'@ | Set-Content -Encoding ascii frontend\src\runner.ts

@'
import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "./api";
import { ALL_STAGES, call, runJob, STAGE_LABEL } from "./runner";

type Row = {
  batch_id: number; file_name: string | null; status: string; created_at: string; rows_total: number; rows_rejected: number;
  reviews: number; scored: number; aspects_done: number; embedded: number; pos: number; neu: number; neg: number;
};
type Votes = { models: { model: string; version: string; reviews: number; neg: number; neu: number; pos: number; avg_expected_stars: number | null }[] };
type Results = {
  reviews: number; scored_reviews: number; average_rating: number | null; text_adjusted_average: number | null;
  net_sentiment: number | null; mismatches: number; low_sample: boolean;
};

const pct = (n: number, d: number) => (d ? Math.round((100 * n) / d) + "%" : "-");

function Detail({ id }: { id: number }) {
  const res = useQuery({ queryKey: ["results", id], queryFn: () => api<Results>(`/uploads/${id}/results`) });
  const votes = useQuery({ queryKey: ["votes", id], queryFn: () => api<Votes>(`/uploads/${id}/votes`) });
  const r = res.data;
  return (
    <div className="mt-3 space-y-3 rounded-lg bg-slate-50 p-3 text-sm">
      {r && (
        <p>
          Stars average {r.average_rating ?? "-"}; read from the text, {r.text_adjusted_average ?? "-"}.
          Net sentiment {r.net_sentiment ?? "-"}. {r.mismatches} reviews where stars and words disagree.
          {r.low_sample && <span className="text-amber-700"> Only {r.reviews} reviews, so treat these as rough.</span>}
        </p>
      )}
      <div>
        <p className="mb-1 font-medium">What each model voted</p>
        {votes.data && votes.data.models.length > 0 ? (
          <table className="w-full text-xs">
            <thead className="text-left text-slate-500"><tr><th>Model</th><th>Reviews</th><th>Negative</th><th>Neutral</th><th>Positive</th><th>Avg expected stars</th></tr></thead>
            <tbody>
              {votes.data.models.map((m) => (
                <tr key={m.model + m.version} className="border-t">
                  <td className="py-1">{m.model}</td><td>{m.reviews}</td>
                  <td>{m.neg} ({pct(m.neg, m.reviews)})</td><td>{m.neu} ({pct(m.neu, m.reviews)})</td><td>{m.pos} ({pct(m.pos, m.reviews)})</td>
                  <td>{m.avg_expected_stars ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="text-slate-500">No model votes yet. Run &ldquo;Get sentiment&rdquo; first.</p>}
      </div>
      <p>
        <a className="text-indigo-600 underline" href={`/api/uploads/${id}/results.csv`}>Download results (CSV)</a>
        {" | "}<Link className="text-indigo-600 underline" to="/rating-vs-text">Rating vs Text</Link>
        {" | "}<Link className="text-indigo-600 underline" to="/problems">Problems</Link>
      </p>
    </div>
  );
}

export default function Sentiment() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["sentiment-uploads"], queryFn: () => api<{ uploads: Row[] }>("/sentiment/uploads") });
  const [open, setOpen] = useState<number | null>(null);
  const [running, setRunning] = useState<{ id: number; stage: string; pct: number } | null>(null);
  const [error, setError] = useState("");
  const [stalled, setStalled] = useState(false);
  const lastMove = useRef(Date.now());

  async function run(id: number, stages: readonly string[]) {
    setError(""); setStalled(false);
    lastMove.current = Date.now();
    const t = setInterval(() => setStalled(Date.now() - lastMove.current > 20000), 2000);
    try {
      for (const stage of stages) {
        setRunning({ id, stage, pct: 0 });
        const s = await call("POST", `/uploads/${id}/${stage}`);
        if (!s.ok) throw new Error(typeof s.data?.detail === "string" ? s.data.detail : "Could not start " + stage);
        await runJob(s.data.job_id, (j) => { lastMove.current = Date.now(); setRunning({ id, stage, pct: j.progress }); });
      }
      await call("POST", "/views/refresh");
      qc.invalidateQueries();
      setOpen(id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      clearInterval(t); setRunning(null); setStalled(false);
    }
  }

  const rows = list.data?.uploads ?? [];
  const btn = "rounded-md border px-2 py-1 text-sm hover:bg-slate-100 disabled:opacity-50";
  return (
    <div className="mx-auto max-w-5xl space-y-4 p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Sentiment</h1>
          <p className="text-slate-600">Every upload and how far it has been analysed. Open one to see its results again.</p>
        </div>
        <Link to="/upload" className="rounded-md bg-indigo-600 px-3 py-2 text-sm text-white hover:bg-indigo-700">Upload reviews</Link>
      </header>
      {error && <p className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {stalled && <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-700">No progress for 20 seconds. Is the worker running? Start it with: python -m app.worker.main</p>}
      {list.isLoading && <p className="text-slate-500">Loading...</p>}
      {list.error && <p className="text-red-600">Could not reach the API. Is uvicorn running on port 8010?</p>}
      {!list.isLoading && rows.length === 0 && <p className="text-slate-500">No uploads yet. Use Upload reviews to add one.</p>}
      <ul className="space-y-3">
        {rows.map((u) => {
          const busy = running?.id === u.batch_id;
          const anyBusy = running != null;
          return (
            <li key={u.batch_id} className="rounded-xl bg-white p-4 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <span className="font-medium">{u.file_name ?? `Upload ${u.batch_id}`}</span>
                  <span className="ml-2 text-xs text-slate-400">{new Date(u.created_at).toLocaleString()}</span>
                  <div className="text-sm text-slate-600">
                    {u.reviews} reviews | scored {pct(u.scored, u.reviews)} | aspects {pct(u.aspects_done, u.reviews)} | indexed {pct(u.embedded, u.reviews)}
                    {u.scored > 0 && ` | ${u.pos} positive, ${u.neu} neutral, ${u.neg} negative`}
                    {u.rows_rejected > 0 && <span className="text-amber-600"> | {u.rows_rejected} rows rejected</span>}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button className={btn} onClick={() => setOpen(open === u.batch_id ? null : u.batch_id)}>{open === u.batch_id ? "Hide" : "View"}</button>
                  <button className={btn} disabled={anyBusy || u.reviews === 0} onClick={() => run(u.batch_id, ["score"])}>Get sentiment</button>
                  <button className="rounded-md bg-indigo-600 px-2 py-1 text-sm text-white disabled:opacity-50" disabled={anyBusy || u.reviews === 0}
                    onClick={() => run(u.batch_id, ALL_STAGES)}>Run full analysis</button>
                </div>
              </div>
              {busy && running && (
                <div className="mt-2 text-sm">
                  <div className="flex justify-between"><span>{STAGE_LABEL[running.stage] ?? running.stage}</span><span className="text-slate-500">{running.pct}%</span></div>
                  <div className="h-2 rounded bg-slate-100"><div className="h-2 rounded bg-indigo-600" style={{ width: running.pct + "%" }} /></div>
                </div>
              )}
              {open === u.batch_id && <Detail id={u.batch_id} />}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
'@ | Set-Content -Encoding ascii frontend\src\Sentiment.tsx

@'
"""Step 22 patcher (Upload reviews buttons, Sentiment page, results CSV). Safe to run twice."""
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

def main_py(s):
    s = once(s, "from app.api.results import router as results_router\n", "from app.api.results import router as results_router\nfrom app.api.sentiment import router as sentiment_router\n")
    return once(s, "app.include_router(results_router)\n", "app.include_router(results_router)\napp.include_router(sentiment_router)\n")
edit("backend/app/main.py", "sentiment_router", main_py)

def layout(s):
    s = once(s, 'import { NavLink, Outlet } from "react-router-dom";', 'import { Link, NavLink, Outlet } from "react-router-dom";')
    s = once(s, '  { to: "/upload", label: "Upload and Data", ready: true },\n',
             '  { to: "/upload", label: "Upload and Data", ready: true },\n  { to: "/sentiment", label: "Sentiment", ready: true },\n')
    return once(s, 'onClick={f.reset}>Clear</button>\n',
                'onClick={f.reset}>Clear</button>\n      <Link to="/upload" className="ml-auto rounded-md bg-indigo-600 px-3 py-1 text-white hover:bg-indigo-700">Upload reviews</Link>\n')
edit("frontend/src/Layout.tsx", "Upload reviews", layout)

def main_tsx(s):
    s = once(s, 'import Upload from "./Upload";\n', 'import Upload from "./Upload";\nimport Sentiment from "./Sentiment";\n')
    return once(s, '            <Route path="upload" element={<Upload />} />\n',
                '            <Route path="upload" element={<Upload />} />\n            <Route path="sentiment" element={<Sentiment />} />\n')
edit("frontend/src/main.tsx", "<Sentiment", main_tsx)

def home(s):
    s = once(s, 'import { useQuery } from "@tanstack/react-query";\n', 'import { useQuery } from "@tanstack/react-query";\nimport { Link } from "react-router-dom";\n')
    return once(s, '        </p>\n      </header>\n',
                '        </p>\n        <Link to="/upload" className="mt-2 inline-block rounded-md bg-indigo-600 px-3 py-2 text-sm text-white hover:bg-indigo-700">Upload reviews</Link>\n      </header>\n')
edit("frontend/src/Home.tsx", "Upload reviews", home)

def upload(s):
    s = once(s, "async function analyse(id: number | null = batch) {", "async function analyse(id: number | null = batch, only?: string[]) {")
    s = once(s, "for (const [key, , path] of STAGES) {", "for (const [key, , path] of STAGES.filter(([k]) => !only || only.includes(k))) {")
    old = '''              {!finished && (
                <button className="rounded-md bg-indigo-600 px-3 py-1 text-sm text-white disabled:opacity-50" disabled={running !== ""} onClick={() => analyse()}>
                  {running ? "Running..." : error ? "Retry analysis" : "Run analysis"}
                </button>
              )}'''
    new = '''              {!finished && (
                <div className="flex gap-2">
                  <button className="rounded-md bg-indigo-600 px-3 py-1 text-sm text-white disabled:opacity-50" disabled={running !== ""} onClick={() => analyse()}>
                    {running ? "Running..." : error ? "Retry full analysis" : "Run full analysis"}
                  </button>
                  <button className="rounded-md border px-3 py-1 text-sm hover:bg-slate-100 disabled:opacity-50" disabled={running !== ""} onClick={() => analyse(batch, ["score"])}>
                    Get sentiment only
                  </button>
                </div>
              )}'''
    s = once(s, old, new)
    return once(s, '<Link className="underline" to="/">Open Home</Link>, ',
                '<a className="underline" href={`/api/uploads/${report.batch_id}/results.csv`}>Download results (CSV)</a>, <Link className="underline" to="/sentiment">Sentiment page</Link>,{" "}\n                    <Link className="underline" to="/">Open Home</Link>, ')
edit("frontend/src/Upload.tsx", "results.csv", upload)
'@ | Set-Content -Encoding ascii patch_step22.py
python patch_step22.py
Remove-Item patch_step22.py

Write-Host 'Step 22 files written.'
