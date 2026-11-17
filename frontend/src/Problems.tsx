import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, send, ActionRow, Issue, Recommendation, WhatIf } from "./api";
import LoadError from "./LoadError";

const num = (x: number | null | undefined, d = 2) => (x == null ? "n/a" : x.toFixed(d));

export default function Problems() {
  const qc = useQueryClient();
  const [k, setK] = useState(3);
  const issues = useQuery({ queryKey: ["issues"], queryFn: () => api<{ issues: Issue[] }>("/issues") });
  const recs = useQuery({ queryKey: ["recs"], queryFn: () => api<{ recommendations: Recommendation[]; note: string }>("/recommendations") });
  const acts = useQuery({ queryKey: ["actions"], queryFn: () => api<{ actions: ActionRow[] }>("/actions") });
  const wi = useQuery({ queryKey: ["whatif", k], queryFn: () => api<WhatIf>("/what-if?k=" + k) });

  const refresh = () => { qc.invalidateQueries({ queryKey: ["actions"] }); qc.invalidateQueries({ queryKey: ["recs"] }); };
  const create = useMutation({ mutationFn: (issue_id: number) => send("POST", "/actions", { issue_id }), onSuccess: refresh });

  if (issues.isLoading) return <div className="p-8 text-slate-500">Loading...</div>;
  if (issues.error || !issues.data) return <LoadError />;
  const list = issues.data.issues;
  const recFor = (id: number) => recs.data?.recommendations.find((r) => r.issue_id === id);

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-bold">What do I fix first?</h1>
        <p className="text-slate-600">
          {list.length === 0 ? "No issues yet. Run issue discovery on a scored batch first." :
            `Top problem: ${list[0].name} (${list[0].aspect}), mentioned in ${list[0].reviews} reviews.`}
        </p>
      </header>

      <section className="rounded-xl bg-white p-4 shadow-sm">
        <h2 className="mb-2 font-semibold">What if we fix the top issues?</h2>
        <label className="flex items-center gap-3 text-sm">Fix the top
          <input type="range" min={1} max={Math.max(1, Math.min(10, list.length))} value={k} onChange={(e) => setK(Number(e.target.value))} />
          <b>{k}</b> issues
        </label>
        {wi.data && (
          <div className="mt-3 text-sm">
            <p>
              Average rating could move from <b>{num(wi.data.current_avg)}</b> to <b>{num(wi.data.estimated_avg)}</b>
              {wi.data.estimated_gain != null && <> (+{num(wi.data.estimated_gain)})</>}, across {wi.data.reviews_affected} affected reviews.
            </p>
            {wi.data.low_sample && <p className="text-amber-600">Early read: based on fewer than 30 rated reviews.</p>}
            <p className="mt-1 text-xs text-slate-400">{wi.data.assumption}</p>
          </div>
        )}
      </section>

      <section className="rounded-xl bg-white p-4 shadow-sm">
        <h2 className="mb-3 font-semibold">Ranked issues</h2>
        <ul className="space-y-4 text-sm">
          {list.map((i) => {
            const r = recFor(i.issue_id);
            return (
              <li key={i.issue_id} className="border-t pt-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-medium">{i.name} <span className="text-slate-400">({i.aspect})</span></span>
                  <span className="text-slate-500">priority {num(i.priority_score, 0)} | {i.reviews} reviews
                    {i.low_sample && <span className="ml-1 text-amber-600">early read</span>}
                    {i.few_sentences && <span className="ml-1 text-amber-600">limited detail</span>}
                    {(i.rare_reviews ?? 0) > 0 && <span className="ml-1 text-slate-500">{i.rare_reviews} rare</span>}
                    {i.hidden_share != null && ` | ${(i.hidden_share * 100).toFixed(0)}% hidden in 4-5 star reviews`}</span>
                </div>
                <ul className="mt-1 space-y-0.5 text-slate-600">
                  {i.evidence.map((e) => <li key={e.review_id}>&ldquo;{e.quote}&rdquo;</li>)}
                </ul>
                {r && (
                  <div className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-md bg-slate-50 p-2">
                    <span>Suggested: {r.suggested_action} <span className="text-slate-400">(team: {r.owner_team})</span></span>
                    {r.existing_action_id == null ? (
                      <button className="rounded-md bg-indigo-600 px-3 py-1 text-white disabled:opacity-50"
                        disabled={create.isPending} onClick={() => create.mutate(i.issue_id)}>Add to tracker</button>
                    ) : <Link to="/tracker" className="text-xs text-emerald-500 hover:underline">In tracker. View status</Link>}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
        {create.error && <p className="mt-2 text-sm text-red-600">{(create.error as Error).message}</p>}
        <p className="mt-3 text-xs text-slate-400">{recs.data?.note}</p>
      </section>

      <section className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white p-4 shadow-sm">
        <div>
          <h2 className="font-semibold">Action tracker</h2>
          <p className="text-sm text-slate-500">{(acts.data?.actions ?? []).length} actions, {(acts.data?.actions ?? []).filter((a) => a.status === "todo" || a.status === "in_progress").length} open.</p>
        </div>
        <Link to="/tracker" className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-700">Open the tracker</Link>
      </section>
    </div>
  );
}
