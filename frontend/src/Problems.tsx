import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, send, ActionRow, Issue, Recommendation, WhatIf } from "./api";

const num = (x: number | null | undefined, d = 2) => (x == null ? "n/a" : x.toFixed(d));
const STATUSES = ["todo", "in_progress", "done", "dropped"];

export default function Problems() {
  const qc = useQueryClient();
  const [k, setK] = useState(3);
  const issues = useQuery({ queryKey: ["issues"], queryFn: () => api<{ issues: Issue[] }>("/issues") });
  const recs = useQuery({ queryKey: ["recs"], queryFn: () => api<{ recommendations: Recommendation[]; note: string }>("/recommendations") });
  const acts = useQuery({ queryKey: ["actions"], queryFn: () => api<{ actions: ActionRow[] }>("/actions") });
  const wi = useQuery({ queryKey: ["whatif", k], queryFn: () => api<WhatIf>("/what-if?k=" + k) });

  const refresh = () => { qc.invalidateQueries({ queryKey: ["actions"] }); qc.invalidateQueries({ queryKey: ["recs"] }); };
  const create = useMutation({ mutationFn: (issue_id: number) => send("POST", "/actions", { issue_id }), onSuccess: refresh });
  const patch = useMutation({
    mutationFn: (v: { id: number; status: string }) => send("PATCH", "/actions/" + v.id, { status: v.status }),
    onSuccess: refresh,
  });

  if (issues.isLoading) return <div className="p-8 text-slate-500">Loading...</div>;
  if (issues.error || !issues.data) return <div className="p-8 text-red-600">Could not reach the API. Is uvicorn running on port 8010?</div>;
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
            {wi.data.low_sample && <p className="text-amber-600">Warning: fewer than 30 rated reviews, so this is a rough estimate.</p>}
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
                    {i.low_sample && <span className="ml-1 text-amber-600">few reviews</span>}
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
                    ) : <span className="text-xs text-emerald-700">In tracker (action {r.existing_action_id})</span>}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
        {create.error && <p className="mt-2 text-sm text-red-600">{(create.error as Error).message}</p>}
        <p className="mt-3 text-xs text-slate-400">{recs.data?.note}</p>
      </section>

      <section className="rounded-xl bg-white p-4 shadow-sm">
        <h2 className="mb-3 font-semibold">Action tracker</h2>
        <table className="w-full text-sm">
          <thead className="text-left text-slate-500"><tr><th>Issue</th><th>Action</th><th>Owner</th><th>Status</th></tr></thead>
          <tbody>
            {(acts.data?.actions ?? []).map((a) => (
              <tr key={a.action_id} className="border-t align-top">
                <td className="py-1">{a.issue} <span className="text-slate-400">({a.aspect})</span></td>
                <td>{a.suggested_action}</td><td>{a.owner ?? "-"}</td>
                <td>
                  <select className="rounded-md border px-1 py-0.5" value={a.status}
                    onChange={(e) => patch.mutate({ id: a.action_id, status: e.target.value })}>
                    {STATUSES.map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
                  </select>
                </td>
              </tr>
            ))}
            {(acts.data?.actions ?? []).length === 0 && <tr><td colSpan={4} className="py-2 text-slate-400">No actions yet.</td></tr>}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-slate-400">When an action is marked done, the API compares the issue&apos;s share before and after. That shows association, not proof of cause.</p>
      </section>
    </div>
  );
}
