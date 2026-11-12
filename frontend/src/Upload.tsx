import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

const ROLES = ["text", "rating", "date", "product", "title", "helpful", "id", "author"];
const ROLE_HELP: Record<string, string> = {
  text: "Review text (required)", rating: "Star rating", date: "Review date", product: "Product name",
  title: "Review title", helpful: "Helpful votes", id: "Review id", author: "Author",
};

type MapRow = { role: string; column: string | null; confidence: number; action: string; alternatives?: unknown[] };
type MappingInfo = {
  columns: string[]; data_rows: number; from_template: boolean; needs_confirmation: boolean;
  repairs: { row_no: number; problem: string }[]; mapping: MapRow[]; preview: string[][];
};
type Report = {
  batch_id: number; rows_total: number; accepted: number; repaired: number; rejected: number; adds_up: boolean;
  reviews_saved: number; already_ingested?: boolean;
  problems: { problem: string; action: string; count: number }[];
};
type Job = { job_id: number; status: string; progress: number; error: string | null };

async function call(method: string, path: string, body?: BodyInit, json = false) {
  const r = await fetch("/api" + path, { method, body, headers: json ? { "Content-Type": "application/json" } : undefined });
  let data: any = null;
  try { data = await r.json(); } catch { /* not json */ }
  return { ok: r.ok, status: r.status, data };
}
const errText = (d: any, fallback: string) =>
  typeof d?.detail === "string" ? d.detail : d?.detail?.message ?? fallback;

function runJob(jobId: number, onProgress: (j: Job) => void): Promise<Job> {
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

const STAGES: [string, string, string][] = [
  ["score", "Reading sentiment", "score"],
  ["aspects", "Finding aspects", "aspects"],
  ["issues", "Grouping problems", "issues"],
];

export default function Upload() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [pasted, setPasted] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [batch, setBatch] = useState<number | null>(null);
  const [fileName, setFileName] = useState("");
  const [note, setNote] = useState("");
  const [info, setInfo] = useState<MappingInfo | null>(null);
  const [choice, setChoice] = useState<Record<string, string>>({});
  const [pickColumns, setPickColumns] = useState<string[] | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [stage, setStage] = useState<Record<string, number>>({});
  const [running, setRunning] = useState("");
  const [finished, setFinished] = useState(false);

  const reset = () => {
    setBatch(null); setInfo(null); setReport(null); setError(""); setNote(""); setPickColumns(null);
    setStage({}); setRunning(""); setFinished(false); setChoice({}); setPasted("");
  };

  async function loadMapping(id: number) {
    const m = await call("GET", `/uploads/${id}/mapping`);
    if (m.status === 422 && m.data?.detail?.columns) {
      setPickColumns(m.data.detail.columns as string[]);
      setChoice({});
      setError(m.data.detail.message);
      return;
    }
    if (!m.ok) { setError(errText(m.data, "Could not detect columns.")); return; }
    if (m.data.already_ingested) {
      const r = await call("GET", `/uploads/${id}/report`);
      if (r.ok) setReport(r.data);
      return;
    }
    const mi = m.data as MappingInfo;
    setInfo(mi);
    setChoice(Object.fromEntries(mi.mapping.filter((x) => x.column).map((x) => [x.role, x.column as string])));
  }

  async function upload(file?: File) {
    reset(); setBusy(true);
    try {
      const fd = new FormData();
      if (file) fd.append("file", file); else fd.append("pasted_text", pasted);
      const u = await call("POST", "/uploads", fd);
      if (!u.ok) { setError(errText(u.data, "Upload failed.")); return; }
      setBatch(u.data.batch_id);
      setFileName(file?.name ?? "pasted text");
      if (u.data.duplicate) setNote("This exact file was uploaded before. Showing its earlier state.");
      await loadMapping(u.data.batch_id);
    } finally { setBusy(false); }
  }

  async function confirm() {
    if (batch == null) return;
    setBusy(true); setError("");
    try {
      const mapping = Object.fromEntries(Object.entries(choice).filter(([, v]) => v));
      if (!mapping.text) { setError("Choose which column holds the review text."); return; }
      const r = await call("PUT", `/uploads/${batch}/mapping`, JSON.stringify({ mapping }), true);
      if (!r.ok) { setError(errText(r.data, "Could not ingest this file.")); return; }
      setReport(r.data); setInfo(null); setPickColumns(null);
      qc.invalidateQueries();
    } finally { setBusy(false); }
  }

  async function analyse() {
    if (batch == null) return;
    setError(""); setFinished(false); setStage({});
    try {
      for (const [key, , path] of STAGES) {
        setRunning(key);
        const s = await call("POST", `/uploads/${batch}/${path}`);
        if (!s.ok) throw new Error(errText(s.data, "Could not start " + key));
        await runJob(s.data.job_id, (j) => setStage((p) => ({ ...p, [key]: j.progress })));
        setStage((p) => ({ ...p, [key]: 100 }));
      }
      await call("POST", "/views/refresh");
      qc.invalidateQueries();
      setFinished(true);
    } catch (e) {
      setError((e as Error).message);
    } finally { setRunning(""); }
  }

  const box = "rounded-xl bg-white p-4 shadow-sm";
  const sel = "rounded-md border border-slate-300 bg-white px-2 py-1 text-sm";
  const columns = info?.columns ?? pickColumns ?? [];

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-bold">Bring in my data</h1>
        <p className="text-slate-600">Upload a review file. The system finds the columns itself and asks only when it is unsure.</p>
      </header>

      {batch == null && (
        <section className={box}>
          <div
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) upload(f); }}
            onClick={() => fileRef.current?.click()}
            className={"cursor-pointer rounded-xl border-2 border-dashed p-10 text-center " + (drag ? "border-indigo-500 bg-indigo-50" : "border-slate-300")}>
            <p className="font-medium">Drop a file here, or click to choose</p>
            <p className="text-sm text-slate-500">CSV, TSV, Excel, JSON or JSONL, TXT</p>
            <input ref={fileRef} type="file" className="hidden" accept=".csv,.tsv,.xlsx,.json,.jsonl,.txt"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
          </div>
          <p className="my-3 text-center text-sm text-slate-400">or paste reviews, one per line</p>
          <textarea className="h-24 w-full rounded-md border border-slate-300 p-2 text-sm" value={pasted} onChange={(e) => setPasted(e.target.value)} />
          <button className="mt-2 rounded-md bg-indigo-600 px-3 py-1 text-sm text-white disabled:opacity-50"
            disabled={busy || !pasted.trim()} onClick={() => upload()}>Use pasted text</button>
        </section>
      )}

      {busy && <p className="text-sm text-slate-500">Working...</p>}
      {error && <p className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {note && <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-700">{note}</p>}

      {batch != null && !report && columns.length > 0 && (
        <section className={box}>
          <h2 className="font-semibold">Check the columns for {fileName}</h2>
          {info && (
            <p className="mb-3 text-sm text-slate-600">
              {info.data_rows} data rows. {info.from_template ? "A saved template for this layout was reused. " : ""}
              {info.needs_confirmation ? "Some columns need a second look." : "This looks right."}
            </p>
          )}
          {info?.repairs.map((r) => <p key={r.row_no} className="text-xs text-slate-500">Repaired: {r.problem}</p>)}
          <table className="mt-2 w-full text-sm">
            <thead className="text-left text-slate-500"><tr><th>What it is</th><th>Column</th><th>Confidence</th></tr></thead>
            <tbody>
              {ROLES.map((role) => {
                const row = info?.mapping.find((m) => m.role === role);
                const unsure = row && row.column && row.action === "ask";
                return (
                  <tr key={role} className="border-t">
                    <td className="py-1">{ROLE_HELP[role]}</td>
                    <td>
                      <select className={sel} value={choice[role] ?? ""} onChange={(e) => setChoice({ ...choice, [role]: e.target.value })}>
                        <option value="">(none)</option>
                        {columns.map((c) => <option key={c} value={c}>{c}</option>)}
                      </select>
                    </td>
                    <td className={unsure ? "text-amber-600" : "text-slate-500"}>
                      {row && row.column ? `${(row.confidence * 100).toFixed(0)}%${unsure ? " - please check" : ""}` : "-"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {info && info.preview.length > 0 && (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-xs text-slate-600">
                <thead><tr>{info.columns.map((c) => <th key={c} className="px-2 text-left">{c}</th>)}</tr></thead>
                <tbody>{info.preview.map((r, i) => <tr key={i} className="border-t">{r.map((c, j) => <td key={j} className="max-w-xs truncate px-2 py-1">{c}</td>)}</tr>)}</tbody>
              </table>
            </div>
          )}
          <div className="mt-3 flex gap-2">
            <button className="rounded-md bg-indigo-600 px-3 py-1 text-sm text-white disabled:opacity-50" disabled={busy} onClick={confirm}>
              {info?.needs_confirmation ? "Confirm and load" : "Looks right, load it"}
            </button>
            <button className="rounded-md border px-3 py-1 text-sm hover:bg-slate-100" onClick={reset}>Cancel</button>
          </div>
        </section>
      )}

      {report && (
        <section className={box}>
          <h2 className="font-semibold">Data quality report</h2>
          <p className="mt-1 text-sm text-slate-600">
            {report.reviews_saved} of {report.rows_total} rows are now reviews: {report.accepted} accepted, {report.repaired} repaired, {report.rejected} rejected
            {report.adds_up ? "." : ". Warning: these counts do not add up to the total."}
          </p>
          {report.problems.length > 0 && (
            <ul className="mt-2 space-y-0.5 text-sm text-slate-600">
              {report.problems.map((p, i) => <li key={i}>{p.count} x {p.problem} ({p.action})</li>)}
            </ul>
          )}
          {report.rejected > 0 && (
            <a className="mt-2 inline-block text-sm text-indigo-600 underline" href={`/api/uploads/${report.batch_id}/rejects.csv`}>Download the rejected rows</a>
          )}
          {report.reviews_saved === 0 && (
            <p className="mt-2 text-sm text-amber-700">Nothing new was saved, so there is nothing to analyse. These reviews may already exist from an earlier upload.</p>
          )}

          {report.reviews_saved > 0 && (
            <div className="mt-4 border-t pt-4">
              <h3 className="font-medium">Analyse these reviews</h3>
              <p className="text-sm text-slate-500">Needs the worker running. Aspect finding is the slow step if a local LLM is used.</p>
              <ul className="my-3 space-y-2 text-sm">
                {STAGES.map(([key, label]) => (
                  <li key={key}>
                    <div className="flex justify-between"><span>{label}</span><span className="text-slate-500">{stage[key] ?? 0}%</span></div>
                    <div className="h-2 rounded bg-slate-100"><div className="h-2 rounded bg-indigo-600" style={{ width: (stage[key] ?? 0) + "%" }} /></div>
                  </li>
                ))}
              </ul>
              {!finished && (
                <button className="rounded-md bg-indigo-600 px-3 py-1 text-sm text-white disabled:opacity-50" disabled={running !== ""} onClick={analyse}>
                  {running ? "Running..." : "Run analysis"}
                </button>
              )}
              {finished && (
                <p className="text-sm text-emerald-700">
                  Done. <Link className="underline" to="/">Open Home</Link> or <Link className="underline" to="/rating-vs-text">Rating vs Text</Link>.
                </p>
              )}
            </div>
          )}
          <button className="mt-4 rounded-md border px-3 py-1 text-sm hover:bg-slate-100" onClick={reset}>Upload another file</button>
        </section>
      )}
    </div>
  );
}
