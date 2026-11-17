import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import LoadError from "./LoadError";

type Severe = {
  total: number; by_category: Record<string, number>; note: string;
  items: { review_id: number; product: string; stars: number | null; date: string | null; categories: string[]; text: string }[];
};
type Reply = {
  review_id: number; product: string; stars: number | null; language: string | null; text: string;
  severe: string[]; aspect: string | null; saved: boolean; draft: string;
};
type Queue = {
  kind: string; total: number; items: Reply[]; products: string[];
  counts: { waiting: number; serious: number; sent: number; skipped: number; saved_drafts: number };
};

const CAT_STYLE: Record<string, string> = {
  safety: "bg-red-100 text-red-800", allergy: "bg-orange-100 text-orange-800",
  fraud: "bg-purple-100 text-purple-800", legal: "bg-slate-200 text-slate-800",
};
const TONES = [
  { key: "professional", label: "Professional" }, { key: "warm", label: "Warm" }, { key: "brief", label: "Brief" },
];
const input = "rounded-md border border-slate-300 bg-slate-100 px-2 py-1 text-sm text-slate-800 outline-none focus:border-accent";

function store(key: string, value?: string): string {
  try {
    if (value !== undefined) localStorage.setItem(key, value);
    return localStorage.getItem(key) ?? "";
  } catch { return value ?? ""; }
}

function ReplyCard({ r, onDone }: { r: Reply; onDone: () => void }) {
  const [body, setBody] = useState(r.draft);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  async function save(status: "draft" | "sent" | "skipped") {
    setBusy(true); setMsg("");
    const res = await fetch(`/api/replies/${r.review_id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ body, status }),
    });
    setBusy(false);
    if (!res.ok) { setMsg("Could not save this reply. Try again."); return; }
    if (status !== "draft") onDone(); else setMsg("Draft saved.");
  }
  async function copy() {
    try { await navigator.clipboard.writeText(body); setMsg("Copied to the clipboard."); } catch { setMsg("Select the text and copy it manually."); }
  }
  return (
    <li className="rounded-lg border border-slate-200 p-3">
      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <span className="font-medium text-slate-300">{r.product}</span><span>{r.stars ?? "-"} stars</span>
        {r.severe.map((c) => <span key={c} className={"rounded px-1.5 py-0.5 " + (CAT_STYLE[c] ?? "")}>{c}</span>)}
        {r.aspect && <span>about {r.aspect}</span>}
        {r.saved && <span className="text-accent">draft saved</span>}
      </div>
      <p className="mt-1 text-sm">&ldquo;{r.text}&rdquo;</p>
      <textarea className={input + " mt-2 h-28 w-full"} value={body} onChange={(e) => setBody(e.target.value)} />
      <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
        <button disabled={busy} onClick={() => save("sent")} className="rounded-md bg-indigo-600 px-3 py-1 text-white disabled:opacity-50">Mark as sent</button>
        <button disabled={busy} onClick={copy} className="rounded-md border px-3 py-1 hover:bg-slate-100">Copy</button>
        <button disabled={busy} onClick={() => save("draft")} className="rounded-md border px-3 py-1 hover:bg-slate-100 disabled:opacity-50">Save draft</button>
        <button disabled={busy} onClick={() => save("skipped")} className="rounded-md border px-3 py-1 hover:bg-slate-100 disabled:opacity-50">Skip</button>
        {msg && <span className="text-xs text-slate-500">{msg}</span>}
      </div>
    </li>
  );
}

function Replies() {
  const qc = useQueryClient();
  const [kind, setKind] = useState<"needs" | "praise">("needs");
  const [tone, setTone] = useState(store("reviewiq.tone") || "professional");
  const [sigText, setSigText] = useState(store("reviewiq.signature"));
  const [sig, setSig] = useState(sigText);
  const [product, setProduct] = useState("");
  const qs = new URLSearchParams({ kind, tone, limit: "40" });
  if (sig.trim()) qs.set("signature", sig);
  if (product) qs.set("product", product);
  const q = useQuery({ queryKey: ["reply-queue", kind, tone, sig, product], queryFn: () => api<Queue>("/replies/queue?" + qs.toString()) });
  const c = q.data?.counts;
  return (
    <section className="rounded-xl bg-white p-4 shadow-sm">
      <h2 className="font-semibold">Replies</h2>
      <p className="text-sm text-slate-500">Ready-to-edit drafts for customer reviews. Nothing is sent from here: copy the reply into your store or email, then mark it as sent.</p>
      <div className="mt-3 flex gap-2 border-b border-slate-200 text-sm">
        {([["needs", "Needs a reply"], ["praise", "Say thanks"]] as const).map(([k, label]) => (
          <button key={k} onClick={() => setKind(k)} className={"-mb-px border-b-2 px-3 py-1.5 " + (kind === k ? "border-accent font-medium" : "border-transparent text-slate-500")}>{label}</button>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-end gap-3 text-sm">
        <label className="text-xs text-slate-500">Tone
          <select className={input + " block"} value={tone} onChange={(e) => { setTone(e.target.value); store("reviewiq.tone", e.target.value); }}>
            {TONES.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
        </label>
        <label className="text-xs text-slate-500">Product
          <select className={input + " block"} value={product} onChange={(e) => setProduct(e.target.value)}>
            <option value="">All products</option>
            {(q.data?.products ?? []).map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <label className="min-w-[14rem] flex-1 text-xs text-slate-500">Sign-off
          <input className={input + " block w-full"} placeholder="For example: Priya, Customer Care Team" value={sigText}
            onChange={(e) => setSigText(e.target.value)} onBlur={() => { setSig(sigText); store("reviewiq.signature", sigText); }} />
        </label>
      </div>
      {c && (
        <p className="mt-3 text-sm text-slate-400">
          {c.waiting} waiting{kind === "needs" && c.serious > 0 && <>, <b className="text-red-400">{c.serious} serious</b></>}. {c.sent} sent, {c.skipped} skipped.
        </p>
      )}
      {q.isLoading && <p className="mt-2 text-sm text-slate-500">Loading...</p>}
      {q.error && <LoadError what="the replies" compact />}
      {q.data && q.data.items.length === 0 && <p className="mt-2 text-sm text-emerald-500">{kind === "needs" ? "Nothing is waiting for a reply." : "No happy reviews are waiting for a thank-you."}</p>}
      <ul className="mt-3 space-y-3">
        {q.data?.items.map((r) => (
          <ReplyCard key={`${kind}-${r.review_id}-${tone}-${sig}`} r={r} onDone={() => qc.invalidateQueries({ queryKey: ["reply-queue"] })} />
        ))}
      </ul>
      {q.data && q.data.total > q.data.items.length && <p className="mt-2 text-xs text-slate-500">Showing {q.data.items.length} of {q.data.total}. Handle these and the next ones appear.</p>}
    </section>
  );
}

export default function Reports() {
  const sev = useQuery({ queryKey: ["severe"], queryFn: () => api<Severe>("/severe") });
  const box = "rounded-xl bg-white p-4 shadow-sm";
  const dl = "block rounded-lg border border-slate-200 p-4 hover:border-accent";
  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-bold">Reports and Replies</h1>
        <p className="text-slate-500">Download a report to share, review serious complaints, and answer your customers.</p>
      </header>

      <section className={box}>
        <h2 className="font-semibold">Download</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <a className={dl} href="/api/reports/summary.pdf">
            <div className="font-medium">Executive report (PDF)</div>
            <p className="mt-1 text-sm text-slate-500">A short readable summary: key numbers, what to fix first, products to watch and what customers like.</p>
          </a>
          <a className={dl} href="/api/reports/export.xlsx">
            <div className="font-medium">Full data (Excel)</div>
            <p className="mt-1 text-sm text-slate-500">Summary, product watchlist, issues with owners, aspects and every review, for your own analysis.</p>
          </a>
        </div>
      </section>

      <section className={box}>
        <h2 className="font-semibold">Serious complaints</h2>
        <p className="text-sm text-slate-500">Reviews that mention safety, allergy, fraud or legal issues. They are always shown, however few there are.</p>
        {sev.isLoading && <p className="mt-2 text-sm text-slate-500">Loading...</p>}
        {sev.error && <LoadError what="the complaints" compact />}
        {sev.data && sev.data.total === 0 && <p className="mt-2 text-sm text-emerald-500">None found.</p>}
        {sev.data && sev.data.total > 0 && (
          <>
            <p className="mt-2 text-sm">
              {sev.data.total} reviews:{" "}
              {Object.entries(sev.data.by_category).map(([c, n]) => <span key={c} className={"mr-2 rounded px-1.5 py-0.5 " + (CAT_STYLE[c] ?? "")}>{c} {n}</span>)}
            </p>
            <p className="text-xs text-slate-500">{sev.data.note}</p>
            <ul className="mt-2 space-y-2">
              {sev.data.items.slice(0, 20).map((i) => (
                <li key={i.review_id} className="rounded-lg border border-slate-200 p-3 text-sm">
                  <div className="flex flex-wrap gap-2 text-xs text-slate-500">
                    <span>{i.product}</span><span>{i.stars ?? "-"} stars</span><span>{i.date ?? ""}</span>
                    {i.categories.map((c) => <span key={c} className={"rounded px-1.5 py-0.5 " + (CAT_STYLE[c] ?? "")}>{c}</span>)}
                  </div>
                  <p className="mt-1">{i.text}</p>
                </li>
              ))}
            </ul>
            {sev.data.items.length > 20 && <p className="mt-2 text-xs text-slate-500">Showing 20 of {sev.data.total}. The Excel file has them all.</p>}
          </>
        )}
      </section>

      <Replies />
    </div>
  );
}
