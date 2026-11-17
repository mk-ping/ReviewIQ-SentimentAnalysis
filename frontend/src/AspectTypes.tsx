import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import LoadError from "./LoadError";

type Domain = { key: string; label: string; categories: { aspect: string; seeds: string[] }[] };
type Domains = { forced: string; domains: Domain[] };
type Detected = { products: { product: string; domain: string; reviews: number }[] };
type Aspects = { aspects: { aspect: string; mentions: number; avg_sentiment: number }[] };

const DETECTED = "__detected__";

export default function AspectTypes() {
  const [sel, setSel] = useState(DETECTED);
  const d = useQuery({ queryKey: ["domains"], queryFn: () => api<Domains>("/domains") });
  const det = useQuery({ queryKey: ["domains-detected"], queryFn: () => api<Detected>("/domains/detected") });
  const asp = useQuery({ queryKey: ["aspects"], queryFn: () => api<Aspects>("/aspects") });
  if (d.isLoading) return <div className="p-8 text-slate-500">Loading...</div>;
  if (d.error || !d.data) return <LoadError />;

  const counts = new Map((asp.data?.aspects ?? []).map((a) => [a.aspect, a]));
  const byKey = new Map(d.data.domains.map((x) => [x.key, x]));
  const detectedKeys = Array.from(new Set((det.data?.products ?? []).map((p) => p.domain)));
  const shown = sel === DETECTED ? detectedKeys.map((k) => byKey.get(k)).filter(Boolean) as Domain[] : [byKey.get(sel)].filter(Boolean) as Domain[];
  const input = "rounded-md border border-slate-300 bg-slate-100 px-2 py-1 text-sm text-slate-800";

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-6">
      <header>
        <h1 className="text-2xl font-bold">Aspect types</h1>
        <p className="text-slate-500">Each kind of review has its own aspects. Pick a type to see them and the seed phrases used to find them, or pick the first option to see only what your reviews actually mention.</p>
      </header>
      <label className="flex items-center gap-2 text-sm text-slate-500">Review type
        <select className={input} value={sel} onChange={(e) => setSel(e.target.value)}>
          <option value={DETECTED}>Detected in my data</option>
          {d.data.domains.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
        </select>
      </label>
      {d.data.forced !== "auto" && <p className="text-sm text-amber-500">The server is forced to use the "{d.data.forced}" type (ASPECT_DOMAIN in .env).</p>}
      {sel === DETECTED && det.data && (
        <p className="text-sm text-slate-400">{det.data.products.map((p) => `${p.product}: ${byKey.get(p.domain)?.label ?? p.domain}`).join(" | ") || "No reviews yet."}</p>
      )}
      {shown.map((dom) => {
        const cats = sel === DETECTED ? dom.categories.filter((c) => counts.has(c.aspect)) : dom.categories;
        return (
          <section key={dom.key} className="rounded-xl border border-slate-200 bg-white p-4">
            <h2 className="font-semibold">{dom.label}</h2>
            {cats.length === 0 && <p className="mt-2 text-sm text-slate-400">No aspects mentioned yet. Run the analysis on an upload of this type.</p>}
            <div className="mt-2 space-y-2">
              {cats.map((c) => {
                const m = counts.get(c.aspect);
                return (
                  <details key={c.aspect} className="rounded-lg border border-slate-200 p-3">
                    <summary className="flex cursor-pointer flex-wrap items-center gap-3">
                      <span className="font-medium">{c.aspect}</span>
                      <span className="text-xs text-slate-500">{c.seeds.length} seed phrases</span>
                      {m && <span className="text-xs" style={{ color: m.avg_sentiment <= -0.25 ? "#fb7185" : m.avg_sentiment >= 0.25 ? "#34d399" : "#94a3b8" }}>{m.mentions} mentions, avg {m.avg_sentiment.toFixed(2)}</span>}
                    </summary>
                    <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm text-slate-400">{c.seeds.map((s) => <li key={s}>{s}</li>)}</ul>
                  </details>
                );
              })}
            </div>
          </section>
        );
      })}
      <p className="text-xs text-slate-500">Mention counts are workspace-wide, so an aspect name shared by several types (such as price) shows the same count under each.</p>
    </div>
  );
}
