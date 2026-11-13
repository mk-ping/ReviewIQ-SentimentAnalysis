import { useState, type ReactNode } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { api, ReviewPage } from "./api";
import Similar from "./Similar";
import { useFilters } from "./store";

export default function Explorer() {
  const f = useFilters();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [mismatchOnly, setMismatchOnly] = useState(false);
  const [minR, setMinR] = useState("");
  const [maxR, setMaxR] = useState("");

  const build = (after: number) => {
    const p = new URLSearchParams({ limit: "25", after_id: String(after) });
    if (f.product) p.set("product", f.product);
    if (query) p.set("q", query);
    if (mismatchOnly) p.set("mismatch_only", "true");
    if (minR) p.set("min_rating", minR);
    if (maxR) p.set("max_rating", maxR);
    return "/reviews?" + p.toString();
  };
  const res = useInfiniteQuery({
    queryKey: ["reviews", f.product, query, mismatchOnly, minR, maxR],
    queryFn: ({ pageParam }) => api<ReviewPage>(build(pageParam)),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_after_id ?? undefined,
  });
  const items = res.data?.pages.flatMap((p) => p.items) ?? [];
  const input = "rounded-md border border-slate-300 bg-white px-2 py-1 text-sm";

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-6">
      <header>
        <h1 className="text-2xl font-bold">Show me the proof</h1>
        <p className="text-slate-600">Search the reviews behind every number. Negative phrases are marked.</p>
      </header>

      <form className="flex flex-wrap items-center gap-3 rounded-xl bg-white p-4 text-sm shadow-sm"
        onSubmit={(e) => { e.preventDefault(); setQuery(q.trim()); }}>
        <input className={input + " w-56"} placeholder="Search words" value={q} onChange={(e) => setQ(e.target.value)} />
        <label className="flex items-center gap-1">Stars from
          <select className={input} value={minR} onChange={(e) => setMinR(e.target.value)}>
            <option value="">any</option>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
          </select></label>
        <label className="flex items-center gap-1">to
          <select className={input} value={maxR} onChange={(e) => setMaxR(e.target.value)}>
            <option value="">any</option>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
          </select></label>
        <label className="flex items-center gap-1"><input type="checkbox" checked={mismatchOnly} onChange={(e) => setMismatchOnly(e.target.checked)} /> Mismatches only</label>
        <button className="rounded-md bg-indigo-600 px-3 py-1 text-white">Search</button>
      </form>

      {res.isLoading && <div className="text-slate-500">Loading...</div>}
      {res.error && <div className="text-red-600">Could not reach the API. Is uvicorn running on port 8010?</div>}

      <ul className="space-y-3">
        {items.map((r) => {
          let body: ReactNode = r.text;
          const marks = r.negative_phrases.map((n) => n.phrase).filter((p) => p && r.text.toLowerCase().includes(p.toLowerCase()));
          if (marks.length > 0) {
            const p = marks[0], i = r.text.toLowerCase().indexOf(p.toLowerCase());
            body = <>{r.text.slice(0, i)}<mark className="rounded bg-red-100 px-0.5 text-red-800">{r.text.slice(i, i + p.length)}</mark>{r.text.slice(i + p.length)}</>;
          }
          return (
            <li key={r.review_id} className="rounded-xl bg-white p-4 text-sm shadow-sm">
              <div className="flex flex-wrap justify-between gap-2 text-xs text-slate-500">
                <span>{r.product} | {r.stars ?? "no"} stars | {r.date ?? "no date"} | {r.language ?? "?"}</span>
                <span>
                  {r.text_label && <>text says {r.text_label}{r.fused_stars != null && ` (${r.fused_stars.toFixed(1)} stars)`}</>}
                  {r.mismatch && <span className="ml-2 rounded bg-amber-50 px-2 py-0.5 text-amber-700">{r.mismatch}</span>}
                </span>
              </div>
              <p className="mt-1">{body}</p>
              <Similar id={r.review_id} />
              {r.negative_phrases.length > 0 && (
                <p className="mt-1 text-xs text-slate-500">Complaints: {r.negative_phrases.map((n) => n.aspect).join(", ")}</p>
              )}
            </li>
          );
        })}
        {!res.isLoading && items.length === 0 && <li className="text-slate-400">No reviews match.</li>}
      </ul>
      {res.hasNextPage && (
        <button className="rounded-md border px-4 py-2 text-sm hover:bg-slate-100" disabled={res.isFetchingNextPage} onClick={() => res.fetchNextPage()}>
          {res.isFetchingNextPage ? "Loading..." : "Load more"}
        </button>
      )}
    </div>
  );
}
