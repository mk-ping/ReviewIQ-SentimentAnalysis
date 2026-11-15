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
