import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, send } from "./api";
import LoadError from "./LoadError";

type Impact = {
  available: boolean; reason?: string; reviews_before?: number; reviews_after?: number;
  share_before?: number; share_after?: number; change?: number; low_sample?: boolean; note?: string;
};
type Item = {
  action_id: number; aspect: string; issue: string; suggested_action: string; owner: string | null; effort: string | null;
  status: "todo" | "in_progress" | "done" | "dropped"; done_at: string | null; impact_note: string | null; impact: Impact | null;
};

const COLUMNS: { key: Item["status"]; title: string; hint: string; tone: string }[] = [
  { key: "todo", title: "To do", hint: "Not started", tone: "#8b7bff" },
  { key: "in_progress", title: "In progress", hint: "Being worked on", tone: "#f5b83d" },
  { key: "done", title: "Done", hint: "Completed, impact is measured", tone: "#34d399" },
  { key: "dropped", title: "Dropped", hint: "Decided not to act", tone: "#94a3b8" },
];
const pct = (x?: number) => (x == null ? "n/a" : (x * 100).toFixed(0) + "%");
const field = "w-full rounded-md border border-slate-300 bg-slate-100 px-2 py-1 text-sm text-slate-800 outline-none focus:border-accent";

function ImpactLine({ i }: { i: Impact | null }) {
  if (!i) return null;
  if (!i.available) return <p className="text-xs text-slate-500">Impact: {i.reason}</p>;
  const down = (i.change ?? 0) < 0;
  return (
    <div className="rounded-md border border-slate-200 p-2 text-xs">
      <div className="font-medium" style={{ color: down ? "#34d399" : "#f87171" }}>
        Complaints {down ? "fell" : "rose"} from {pct(i.share_before)} to {pct(i.share_after)} of reviews
      </div>
      <div className="text-slate-500">{i.reviews_before} reviews before, {i.reviews_after} after.{i.low_sample ? " Small sample, treat with care." : ""} {i.note}</div>
    </div>
  );
}

function Card({ a, save }: { a: Item; save: (id: number, body: Record<string, unknown>) => void }) {
  const [owner, setOwner] = useState(a.owner ?? "");
  const [note, setNote] = useState(a.impact_note ?? "");
  return (
    <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-3 text-sm">
      <div>
        <div className="font-medium">{a.issue}</div>
        <div className="text-xs text-slate-500">{a.aspect}</div>
      </div>
      <p className="text-slate-300">{a.suggested_action}</p>
      <label className="block text-xs text-slate-500">Owner
        <input className={field} value={owner} placeholder="Who is responsible" onChange={(e) => setOwner(e.target.value)}
          onBlur={() => owner !== (a.owner ?? "") && save(a.action_id, { owner })} />
      </label>
      <div className="grid grid-cols-2 gap-2">
        <label className="block text-xs text-slate-500">Status
          <select className={field} value={a.status} onChange={(e) => save(a.action_id, { status: e.target.value })}>
            {COLUMNS.map((c) => <option key={c.key} value={c.key}>{c.title}</option>)}
          </select>
        </label>
        <label className="block text-xs text-slate-500">Effort
          <select className={field} value={a.effort ?? ""} onChange={(e) => e.target.value && save(a.action_id, { effort: e.target.value })}>
            <option value="">Not set</option>
            <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option>
          </select>
        </label>
      </div>
      {a.status === "done" && (
        <label className="block text-xs text-slate-500">Completed on
          <input type="date" className={field} value={a.done_at ?? ""} onChange={(e) => e.target.value && save(a.action_id, { done_at: e.target.value })} />
        </label>
      )}
      <label className="block text-xs text-slate-500">Notes
        <textarea className={field} rows={2} value={note} placeholder="What was done, or why it was dropped" onChange={(e) => setNote(e.target.value)}
          onBlur={() => note !== (a.impact_note ?? "") && save(a.action_id, { impact_note: note })} />
      </label>
      {a.status === "done" && <ImpactLine i={a.impact} />}
    </div>
  );
}

export default function Tracker() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["actions"], queryFn: () => api<{ actions: Item[] }>("/actions") });
  const patch = useMutation({
    mutationFn: (v: { id: number; body: Record<string, unknown> }) => send("PATCH", "/actions/" + v.id, v.body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["actions"] }); qc.invalidateQueries({ queryKey: ["recs"] }); },
  });
  if (q.isLoading) return <div className="p-8 text-slate-500">Loading...</div>;
  if (q.error || !q.data) return <LoadError what="the action tracker" />;
  const items = q.data.actions;
  if (items.length === 0) {
    return (
      <div className="mx-auto max-w-xl p-10 text-center">
        <h1 className="text-2xl font-bold">No actions yet</h1>
        <p className="mt-2 text-slate-500">Open a problem on the priorities page and choose Add to tracker. It then appears here, where you can assign an owner and follow it to completion.</p>
        <Link to="/problems" className="mt-6 inline-block rounded-lg bg-gradient-to-r from-accent to-accent2 px-5 py-2.5 text-sm font-semibold text-slate-50">Go to Problems and Priorities</Link>
      </div>
    );
  }
  const by = (s: string) => items.filter((a) => a.status === s);
  const open = by("todo").length + by("in_progress").length;
  return (
    <div className="mx-auto max-w-7xl space-y-4 p-6">
      <header>
        <h1 className="text-2xl font-bold">Action Tracker</h1>
        <p className="text-slate-500">{items.length} actions. {open} open, {by("done").length} done. Mark an action done to see whether complaints dropped afterwards.</p>
      </header>
      {patch.error && <p className="text-sm text-red-500">{(patch.error as Error).message}</p>}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {COLUMNS.map((c) => (
          <section key={c.key} className="space-y-3">
            <div className="flex items-baseline justify-between border-b-2 pb-1" style={{ borderColor: c.tone }}>
              <h2 className="font-semibold">{c.title} <span className="text-slate-500">{by(c.key).length}</span></h2>
              <span className="text-xs text-slate-500">{c.hint}</span>
            </div>
            {by(c.key).map((a) => <Card key={a.action_id} a={a} save={(id, body) => patch.mutate({ id, body })} />)}
            {by(c.key).length === 0 && <p className="text-xs text-slate-500">Nothing here.</p>}
          </section>
        ))}
      </div>
    </div>
  );
}
