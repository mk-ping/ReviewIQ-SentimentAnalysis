import { FormEvent, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth, Splash } from "./auth";
import { Icon, Wordmark } from "./Brand";

const POINTS = [
  "Fused stars that show under-rated and over-rated reviews",
  "Aspect sentiment for every sentence, in many languages",
  "A ranked list of problems to fix first",
];

export default function AuthPage({ mode }: { mode: "login" | "signup" }) {
  const { loading, user, login, signup } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const from = (loc.state as { from?: string } | null)?.from || "/";
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const isLogin = mode === "login";

  if (loading) return <Splash />;
  if (user) return <Navigate to={from} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (!isLogin && password.length < 8) { setError("Use a password of at least 8 characters."); return; }
    setBusy(true);
    try {
      if (isLogin) await login(email, password); else await signup(name, email, password);
      nav(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const field = "mt-1.5 w-full rounded-lg border border-slate-300 bg-slate-100 px-3 py-2.5 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-accent focus:ring-2 focus:ring-accent/30";
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <aside className="relative hidden flex-col justify-between overflow-hidden border-r border-slate-200 bg-white p-12 lg:flex">
        <div className="absolute -left-24 -top-24 h-80 w-80 rounded-full bg-accent/20 blur-3xl" />
        <div className="absolute -bottom-24 -right-16 h-80 w-80 rounded-full bg-accent2/15 blur-3xl" />
        <Link to="/welcome" className="relative"><Wordmark /></Link>
        <div className="relative">
          <h2 className="max-w-md text-4xl font-bold leading-tight tracking-tight text-slate-900">
            Read between the <span className="text-gradient">stars</span>
          </h2>
          <ul className="mt-8 space-y-4">
            {POINTS.map((p) => (
              <li key={p} className="flex items-start gap-3 text-slate-600">
                <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-indigo-50 text-accent"><Icon name="check" size={14} /></span>
                {p}
              </li>
            ))}
          </ul>
        </div>
        <div className="relative text-sm text-slate-400">ReviewIQ &middot; ADBMS project</div>
      </aside>

      <main className="flex items-center justify-center px-5 py-12">
        <div className="w-full max-w-sm">
          <Link to="/welcome" className="mb-8 block lg:hidden"><Wordmark /></Link>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">{isLogin ? "Welcome back" : "Create your account"}</h1>
          <p className="mt-1.5 text-sm text-slate-500">{isLogin ? "Log in to see your dashboards." : "It takes a few seconds. The first account becomes the manager."}</p>

          <form onSubmit={submit} className="mt-8 space-y-4">
            {!isLogin && (
              <label className="block text-sm text-slate-600">Name
                <input className={field} value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" autoComplete="name" />
              </label>
            )}
            <label className="block text-sm text-slate-600">Email
              <input className={field} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" autoComplete="email" />
            </label>
            <label className="block text-sm text-slate-600">Password
              <div className="relative">
                <input className={field + " pr-16"} type={show ? "text" : "password"} required value={password}
                       onChange={(e) => setPassword(e.target.value)} placeholder={isLogin ? "Your password" : "At least 8 characters"}
                       autoComplete={isLogin ? "current-password" : "new-password"} />
                <button type="button" onClick={() => setShow(!show)} className="absolute right-3 top-1/2 mt-0.5 -translate-y-1/2 text-xs text-slate-500 hover:text-slate-800">
                  {show ? "Hide" : "Show"}
                </button>
              </div>
            </label>
            {error && <div role="alert" className="rounded-lg border border-red-700/40 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
            <button disabled={busy} className="w-full rounded-lg bg-gradient-to-r from-accent to-accent2 py-2.5 text-sm font-semibold text-slate-50 hover:opacity-90 disabled:opacity-60">
              {busy ? "Please wait..." : isLogin ? "Log in" : "Create account"}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-500">
            {isLogin ? "New here? " : "Already have an account? "}
            <Link to={isLogin ? "/signup" : "/login"} state={loc.state} className="font-medium text-accent hover:underline">{isLogin ? "Create an account" : "Log in"}</Link>
          </p>
        </div>
      </main>
    </div>
  );
}
