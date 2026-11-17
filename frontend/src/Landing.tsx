import { Link } from "react-router-dom";
import { useAuth } from "./auth";
import { Icon, Wordmark } from "./Brand";

const FEATURES = [
  { icon: "smile", title: "Three models, one answer", body: "Each review is read by three sentiment models chosen for its language, then combined with weights earned on validation data." },
  { icon: "gap", title: "Stars versus words", body: "Fused stars show where the text disagrees with the rating, and which reviews are under-rated or over-rated." },
  { icon: "layers", title: "Aspect sentiment", body: "Every sentence is tagged with the aspects it talks about, so you see what people love and hate, not only how many." },
  { icon: "alert", title: "Problems, ranked", body: "Complaints are clustered into issues and ranked by how often they appear, how severe they are and whether they are growing." },
  { icon: "star", title: "Listing versus reality", body: "Compare the rating shown on the listing with the rating the text supports, and find unhappy customers hiding in 4 and 5 star reviews." },
  { icon: "globe", title: "Many languages", body: "English, Spanish, French, German, Italian, Dutch, Hindi and Hinglish are routed to models that handle them." },
];
const STEPS = [
  { n: "1", title: "Upload", body: "Drop in a CSV or Excel export of reviews. Columns are mapped for you and bad rows are set aside." },
  { n: "2", title: "Analyse", body: "Sentiment, aspects and issues are computed in the background with live progress." },
  { n: "3", title: "Act", body: "Read the dashboards, assign actions, draft replies and export an Excel or PDF report." },
];

function Preview() {
  const bars = [["Positive", "w-4/5", "bg-emerald-600"], ["Neutral", "w-2/5", "bg-slate-400"], ["Negative", "w-3/5", "bg-red-600"]];
  return (
    <div className="relative mx-auto mt-14 max-w-3xl">
      <div className="absolute -inset-6 rounded-3xl bg-gradient-to-r from-accent/20 to-accent2/20 blur-3xl" />
      <div className="relative rounded-2xl border border-slate-300 bg-white p-5 shadow-2xl shadow-black/60">
        <div className="mb-4 flex items-center justify-between text-xs text-slate-500">
          <span className="flex gap-1.5"><i className="h-2.5 w-2.5 rounded-full bg-red-600" /><i className="h-2.5 w-2.5 rounded-full bg-amber-600" /><i className="h-2.5 w-2.5 rounded-full bg-emerald-600" /></span>
          <span>Sample layout, not real data</span>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-slate-200 bg-slate-100 p-4">
            <div className="mb-3 text-sm font-medium text-slate-800">Who feels what</div>
            {bars.map(([label, w, color]) => (
              <div key={label} className="mb-2.5">
                <div className="mb-1 text-xs text-slate-500">{label}</div>
                <div className="h-2 rounded-full bg-slate-200"><div className={`h-2 rounded-full ${w} ${color}`} /></div>
              </div>
            ))}
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-100 p-4">
            <div className="mb-3 text-sm font-medium text-slate-800">Rating versus text</div>
            <div className="flex h-24 items-end gap-2">
              {[30, 45, 35, 60, 85].map((h, i) => (
                <div key={i} className="flex-1 rounded-t bg-gradient-to-t from-accent/40 to-accent" style={{ height: h + "%" }} />
              ))}
            </div>
            <div className="mt-2 flex justify-between text-xs text-slate-500"><span>1 star</span><span>5 stars</span></div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-100 p-4 sm:col-span-2">
            <div className="mb-3 text-sm font-medium text-slate-800">Aspect heatmap</div>
            <div className="grid grid-cols-7 gap-1.5">
              {Array.from({ length: 14 }).map((_, i) => (
                <div key={i} className="h-6 rounded" style={{ background: ["#34d399", "#22d3ee", "#8b7bff", "#fb7185"][(i * 3 + (i % 4)) % 4], opacity: 0.35 + ((i * 37) % 60) / 100 }} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Landing() {
  const { user, authRequired } = useAuth();
  const inside = !!user || !authRequired;
  const primary = "rounded-lg bg-gradient-to-r from-accent to-accent2 px-5 py-2.5 text-sm font-semibold text-slate-50 hover:opacity-90";
  const ghost = "rounded-lg border border-slate-300 px-5 py-2.5 text-sm font-medium text-slate-800 hover:bg-slate-100";
  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5">
        <Wordmark />
        <nav className="flex items-center gap-2">
          <a href="#features" className="hidden px-3 py-2 text-sm text-slate-600 hover:text-slate-900 sm:block">Features</a>
          <a href="#how" className="hidden px-3 py-2 text-sm text-slate-600 hover:text-slate-900 sm:block">How it works</a>
          {inside ? (
            <Link to="/" className={primary}>Open dashboard</Link>
          ) : (
            <>
              <Link to="/login" className="px-3 py-2 text-sm text-slate-800 hover:text-slate-900">Log in</Link>
              <Link to="/signup" className={primary}>Sign up</Link>
            </>
          )}
        </nav>
      </header>

      <section className="mx-auto max-w-6xl px-5 pb-10 pt-16 text-center">
        <span className="rounded-full border border-slate-300 bg-slate-100 px-3 py-1 text-xs text-slate-600">Sentiment analysis for customer reviews</span>
        <h1 className="mx-auto mt-6 max-w-3xl text-4xl font-bold leading-tight tracking-tight text-slate-900 sm:text-6xl">
          Know what your customers <span className="text-gradient">really</span> mean
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-slate-500">
          ReviewIQ reads every review, finds the gap between the stars and the words, and tells you which problems to fix first.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          {inside ? <Link to="/" className={primary}>Open dashboard</Link> : <Link to="/signup" className={primary}>Get started free</Link>}
          {!inside && <Link to="/login" className={ghost}>Log in</Link>}
        </div>
        <Preview />
      </section>

      <section id="features" className="mx-auto max-w-6xl px-5 py-20">
        <h2 className="text-center text-3xl font-bold tracking-tight text-slate-900">Everything the reviews are trying to tell you</h2>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-2xl border border-slate-200 bg-white p-5 transition-colors hover:border-accent/60">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-indigo-50 text-accent"><Icon name={f.icon} size={20} /></span>
              <h3 className="mt-4 font-semibold text-slate-900">{f.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-slate-500">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="how" className="mx-auto max-w-6xl px-5 py-16">
        <h2 className="text-center text-3xl font-bold tracking-tight text-slate-900">From file to action in three steps</h2>
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {STEPS.map((s) => (
            <div key={s.n} className="rounded-2xl border border-slate-200 bg-white p-6">
              <span className="grid h-9 w-9 place-items-center rounded-full bg-gradient-to-br from-accent to-accent2 font-bold text-slate-50">{s.n}</span>
              <h3 className="mt-4 text-lg font-semibold text-slate-900">{s.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-slate-500">{s.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-4xl px-5 py-20">
        <div className="rounded-3xl border border-slate-300 bg-gradient-to-br from-indigo-100 to-white p-10 text-center">
          <h2 className="text-3xl font-bold tracking-tight text-slate-900">Ready to read between the stars?</h2>
          <p className="mx-auto mt-3 max-w-xl text-slate-500">Create an account, upload a file of reviews and have your first dashboards in minutes.</p>
          <div className="mt-6">
            {inside ? <Link to="/" className={primary}>Open dashboard</Link> : <Link to="/signup" className={primary}>Create your account</Link>}
          </div>
        </div>
      </section>

      <footer className="border-t border-slate-200 py-8 text-center text-sm text-slate-400">ReviewIQ &middot; Customer review intelligence</footer>
    </div>
  );
}
