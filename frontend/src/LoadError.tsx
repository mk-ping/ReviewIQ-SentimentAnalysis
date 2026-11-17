export default function LoadError({ what = "this page", compact = false }: { what?: string; compact?: boolean }) {
  return (
    <div className={compact ? "py-2" : "mx-auto max-w-md p-10 text-center"}>
      <p className="font-medium text-slate-800">We could not load {what}.</p>
      <p className="mt-1 text-sm text-slate-500">Check your connection and try again. If it keeps happening, sign out and back in.</p>
      <button onClick={() => window.location.reload()} className="mt-3 rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100">Try again</button>
    </div>
  );
}
