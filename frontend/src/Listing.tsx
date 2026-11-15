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
