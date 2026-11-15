
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

type Severe = {
  total: number; by_category: Record<string, number>; note: string;
  items: { review_id: number; product: string; stars: number | null; date: string | null; categories: string[]; text: string }[];
};
type Reply = {
  review_id: number; product: string; stars: number | null; language: string | null; text: string;
  severe: string[]; aspect: string | null; saved: boolean; draft: string;
};
type Queue = { total: number; items: Reply[] };

const CAT_STYLE: Record<string, string> = {
  safety: "bg-red-100 text-red-800", allergy: "bg-orange-100 text-orange-800",
  fraud: "bg-purple-100 text-purple-800", legal: "bg-slate-200 text-slate-800",
};

function ReplyCard({ r, onDone }: { r: Reply; onDone: () => void }) {
  const [body, setBody] = useState(r.draft);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function save(status: "draft" | "sent" | "skipped") {
    setBusy(true); setErr("");
    const res = await fetch(`/api/replies/${r.review_id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ body, status }),
    });
    setBusy(false);
    if (!res.ok) { setErr("Could not save this reply."); return; }
    if (status !== "draft") onDone();
  }
  return (
    <li className="rounded-lg border border-slate-200 p-3">
      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <span>{r.product}</span><span>{r.stars ?? "-"} stars</span>
        {r.severe.map((c) => <span key={c} className={"rounded px-1.5 py-0.5 " + (CAT_STYLE[c] ?? "")}>{c}</span>)}
        {r.aspect && <span>about {r.aspect}</span>}
      </div>
      <p className="mt-1 text-sm">{r.text}</p>
      <textarea className="mt-2 h-24 w-full rounded-md border border-slate-300 p-2 text-sm" value={body} onChange={(e) => setBody(e.target.value)} />
      {err && <p className="text-sm text-red-700">{err}</p>}
      <div className="mt-1 flex gap-2 text-sm">
        <button disabled={busy} onClick={() => save("sent")} className="rounded-md bg-indigo-600 px-3 py-1 text-white disabled:opacity-50">Mark as sent</button>
        <button disabled={busy} onClick={() => save("draft")} className="rounded-md border px-3 py-1 hover:bg-slate-100 disabled:opacity-50">Save draft</button>
        <button disabled={busy} onClick={() => save("skipped")} className="rounded-md border px-3 py-1 hover:bg-slate-100 disabled:opacity-50">Skip</button>
      </div>
    </li>
  );
}

export default function Reports() {
  const qc = useQueryClient();
  const sev = useQuery({ queryKey: ["severe"], queryFn: () => api<Severe>("/severe") });
  const queue = useQuery({ queryKey: ["reply-queue"], queryFn: () => api<Queue>("/replies/queue") });
  const box = "rounded-xl bg-white p-4 shadow-sm";
  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-bold">Reports and replies</h1>
        <p className="text-slate-600">Download the summary, check serious complaints, and answer the reviews that need an answer.</p>
      </header>

      <section className={box}>
        <h2 className="font-semibold">Download</h2>
        <div className="mt-2 flex flex-wrap gap-3 text-sm">
          <a className="rounded-md bg-indigo-600 px-3 py-1 text-white" href="/api/reports/export.xlsx">Excel report</a>
          <a className="rounded-md bg-indigo-600 px-3 py-1 text-white" href="/api/reports/summary.pdf">PDF summary</a>
        </div>
      </section>

      <section className={box}>
        <h2 className="font-semibold">Serious complaints</h2>
        <p className="text-sm text-slate-500">Safety, allergy, fraud and legal words. Shown however few there are.</p>
        {sev.isLoading && <p className="mt-2 text-sm text-slate-500">Loading...</p>}
        {sev.data && sev.data.total === 0 && <p className="mt-2 text-sm text-emerald-700">None found.</p>}
        {sev.data && sev.data.total > 0 && (
          <>
            <p className="mt-2 text-sm">
              {sev.data.total} reviews:{" "}
              {Object.entries(sev.data.by_category).map(([c, n]) => <span key={c} className={"mr-2 rounded px-1.5 py-0.5 " + (CAT_STYLE[c] ?? "")}>{c} {n}</span>)}
            </p>
            <p className="text-xs text-slate-500">{sev.data.note}</p>
            <ul className="mt-2 space-y-2">
              {sev.data.items.map((i) => (
                <li key={i.review_id} className="rounded-lg border border-slate-200 p-3 text-sm">
                  <div className="flex flex-wrap gap-2 text-xs text-slate-500">
                    <span>{i.product}</span><span>{i.stars ?? "-"} stars</span><span>{i.date ?? ""}</span>
                    {i.categories.map((c) => <span key={c} className={"rounded px-1.5 py-0.5 " + (CAT_STYLE[c] ?? "")}>{c}</span>)}
                  </div>
                  <p className="mt-1">{i.text}</p>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section className={box}>
        <h2 className="font-semibold">Reply queue</h2>
        <p className="text-sm text-slate-500">Serious complaints first, then the most negative reviews. Drafts come from fixed templates. Edit before you mark one as sent. Nothing is sent from here.</p>
        {queue.isLoading && <p className="mt-2 text-sm text-slate-500">Loading...</p>}
        {queue.data && queue.data.items.length === 0 && <p className="mt-2 text-sm text-emerald-700">Nothing waiting for a reply.</p>}
        <ul className="mt-2 space-y-3">
          {queue.data?.items.map((r) => (
            <ReplyCard key={r.review_id} r={r} onDone={() => qc.invalidateQueries({ queryKey: ["reply-queue"] })} />
          ))}
        </ul>
      </section>
    </div>
  );
}
