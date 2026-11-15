import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { USE_MOCK } from "../api";
import { useAuth } from "../useAuth";

/** Log in (FR-35). Any wrong field gives the same message, like the backend. */
export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as { from?: string; registered?: boolean } | null;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={state?.from ?? "/dashboard"} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      navigate(state?.from ?? "/dashboard", { replace: true });
    } catch {
      setError("Wrong email or password");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <form className="card auth-card" onSubmit={submit}>
        <div className="brand"><img className="brand-logo" src="/simera-logo.jpg" alt="Simera" /><div><b>Open Rec</b><small>by Simera</small></div></div>
        <h1>Log in</h1>
        <p className="sub">Internal tool for the Simera team</p>
        {state?.registered && <div className="notice success">Account created, please log in.</div>}
        {error && <div className="notice error" role="alert">{error}</div>}
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" className="input" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input id="password" className="input" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        <button className="btn btn-primary btn-block" disabled={busy}>{busy ? "Logging in…" : "Log in"}</button>
        <p className="auth-foot">No account? <Link to="/register">Create an account</Link></p>
        {USE_MOCK && <p className="auth-foot">Fake data: lilian@simera.com (admin) or nadeen@simera.com (reviewer), any password.</p>}
      </form>
    </div>
  );
}
