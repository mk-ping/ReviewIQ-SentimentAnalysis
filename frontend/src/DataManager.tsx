import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, send } from "./api";
import LoadError from "./LoadError";

type Sources = {
  uploads: { batch_id: number; file_name: string | null; status: string; rows: number; uploaded_at: string; reviews: number }[];
  products: { product_id: number; name: string; reviews: number }[];
};

const STATUS: Record<string, string> = {
  done: "Analysed", failed: "Failed", scoring: "Analysing", ingesting: "Loading", uploaded: "Uploaded", mapping_needed: "Needs column check",
};

export default function DataManager() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["data-sources"], queryFn: () => api<Sources>("/data/sources") });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function remove(path: string, what: string, detail: string) {
    if (!window.confirm(`Delete ${what}?\n\n${detail}\nThis cannot be undone.`)) return;
    setBusy(true); setMsg("");
    try {
      const r = await send<{ reviews_removed: number }>("DELETE", path);
      setMsg(`Removed ${r.reviews_removed.toLocaleString()} reviews.`);
      qc.invalidateQueries();
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (q.isLoading) return null;
  if (q.error || !q.data) return <LoadError what="your data" compact />;
  const { uploads, products } = q.data;
  const total = products.reduce((n, p) => n + p.reviews, 0);
  const btn = "rounded-md border border-red-400/60 px-2 py-0.5 text-xs text-red-400 hover:bg-red-500/10 disabled:opacity-50";
  return (
    <section className="mt-6 rounded-xl bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-semibold">Manage your data</h2>
          <p className="text-sm text-slate-500">{uploads.length} uploads, {products.length} products, {total.toLocaleString()} reviews. Delete what you no longer need and every page updates.</p>
        </div>
        {uploads.length > 0 && (
          <button disabled={busy} className={btn} onClick={() => remove("/data/all", "all of your data", `${total.toLocaleString()} reviews, issues and tracked actions will be removed.`)}>
            Delete everything
          </button>
        )}
      </div>
      {msg && <p className="mt-2 text-sm text-slate-400">{msg}</p>}
      {uploads.length === 0 && products.length === 0 && <p className="mt-3 text-sm text-slate-500">Nothing uploaded yet.</p>}
      <div className="mt-3 grid gap-4 md:grid-cols-2">
        {uploads.length > 0 && (
          <div>
            <div className="mb-1 text-xs uppercase tracking-wide text-slate-500">Uploads</div>
            <ul className="divide-y divide-slate-200 text-sm">
              {uploads.map((u) => (
                <li key={u.batch_id} className="flex items-center justify-between gap-2 py-1.5">
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{u.file_name ?? `Upload ${u.batch_id}`}</span>
                    <span className="text-xs text-slate-500">{u.uploaded_at} | {u.reviews.toLocaleString()} reviews | {STATUS[u.status] ?? u.status}</span>
                  </span>
                  <button disabled={busy} className={btn} onClick={() => remove(`/data/uploads/${u.batch_id}`, u.file_name ?? "this upload", `${u.reviews.toLocaleString()} reviews from this file will be removed.`)}>Delete</button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {products.length > 0 && (
          <div>
            <div className="mb-1 text-xs uppercase tracking-wide text-slate-500">Products</div>
            <ul className="max-h-72 divide-y divide-slate-200 overflow-auto text-sm">
              {products.map((p) => (
                <li key={p.product_id} className="flex items-center justify-between gap-2 py-1.5">
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{p.name}</span>
                    <span className="text-xs text-slate-500">{p.reviews.toLocaleString()} reviews</span>
                  </span>
                  <button disabled={busy} className={btn} onClick={() => remove(`/data/products/${p.product_id}`, p.name, `${p.reviews.toLocaleString()} reviews of this product will be removed.`)}>Delete</button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}
