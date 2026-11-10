import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { USE_MOCK } from "../api";
import { useAuth } from "../useAuth";

/** Minimal login form, only so we can get into the app. The real screen comes later. */
export function LoginPage() {
  const { user, loading, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/jobs";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!loading && user) return <Navigate to={from} replace />;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch {
      setError("Wrong email or password");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login">
      <h1>Open Rec Engine</h1>
      <h2>Log in</h2>
      <form onSubmit={handleSubmit}>
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Logging in…" : "Log in"}
        </button>
      </form>
      {USE_MOCK && (
        <p className="hint">
          Mock mode: use <code>lilian@simera.com</code> (admin) or <code>nadeen@simera.com</code>{" "}
          (reviewer) with any password.
        </p>
      )}
    </main>
  );
}