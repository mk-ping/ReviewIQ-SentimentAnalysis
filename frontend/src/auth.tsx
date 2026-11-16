import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { send } from "./api";

export type User = { user_id: number; email: string; name: string; role: string };
type Me = { auth_required: boolean; user: User | null };
type Ctx = {
  loading: boolean; user: User | null; authRequired: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (name: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthCtx = createContext<Ctx | null>(null);

export function useAuth(): Ctx {
  const c = useContext(AuthCtx);
  if (!c) throw new Error("useAuth must be used inside AuthProvider");
  return c;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const [authRequired, setAuthRequired] = useState(true);

  useEffect(() => {
    fetch("/api/auth/me")
      .then((r) => (r.ok ? (r.json() as Promise<Me>) : Promise.reject(new Error(String(r.status)))))
      .then((m) => { setUser(m.user); setAuthRequired(m.auth_required); })
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const onExpired = () => { setUser(null); qc.clear(); };
    window.addEventListener("reviewiq:401", onExpired);
    return () => window.removeEventListener("reviewiq:401", onExpired);
  }, [qc]);

  const login = useCallback(async (email: string, password: string) => {
    const r = await send<{ user: User }>("POST", "/auth/login", { email, password });
    qc.clear(); setUser(r.user);
  }, [qc]);
  const signup = useCallback(async (name: string, email: string, password: string) => {
    const r = await send<{ user: User }>("POST", "/auth/signup", { name, email, password });
    qc.clear(); setUser(r.user);
  }, [qc]);
  const logout = useCallback(async () => {
    try { await send("POST", "/auth/logout"); } finally { setUser(null); qc.clear(); }
  }, [qc]);

  return <AuthCtx.Provider value={{ loading, user, authRequired, login, signup, logout }}>{children}</AuthCtx.Provider>;
}

export function Splash() {
  return (
    <div className="grid min-h-screen place-items-center">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-300 border-t-accent" />
    </div>
  );
}

/** Wraps every dashboard page. Logged-out visitors are sent to the landing page or the login page. */
export function Protected() {
  const { loading, user, authRequired } = useAuth();
  const loc = useLocation();
  if (loading) return <Splash />;
  if (authRequired && !user) {
    return <Navigate to={loc.pathname === "/" ? "/welcome" : "/login"} replace state={{ from: loc.pathname }} />;
  }
  return <Outlet />;
}
