import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../api";
import { errorText } from "../format";
import { useAuth } from "../useAuth";
import { registerProblems } from "../validation";

/** Create an account. New accounts are reviewers. It does not log in by itself. */
export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "", confirm: "" });
  const [problems, setProblems] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    const found = registerProblems(form.name, form.password, form.confirm);
    setProblems(found);
    if (found.length) return; // nothing is sent when the form is wrong
    setBusy(true);
    try {
      await register(form.name, form.email, form.password);
      navigate("/login", { replace: true, state: { registered: true } });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) setProblems(["This email is already registered"]);
      else if (err instanceof ApiError && err.status === 422) setProblems(["Please check the fields"]);
      else setProblems([errorText(err)]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <form className="card auth-card" onSubmit={submit} noValidate>
        <div className="brand"><img className="brand-logo" src="/simera-logo.jpg" alt="Simera" /><div><b>Open Rec</b><small>by Simera</small></div></div>
        <h1>Create an account</h1>
        <p className="sub">New accounts can review leads and drafts</p>
        {problems.length > 0 && (
          <div className="notice error" role="alert"><div>{problems.map((p) => <p key={p}>{p}</p>)}</div></div>
        )}
        <div className="field"><label htmlFor="name">Full name</label><input id="name" className="input" value={form.name} onChange={set("name")} /></div>
        <div className="field"><label htmlFor="email">Email</label><input id="email" className="input" type="email" required value={form.email} onChange={set("email")} /></div>
        <div className="field"><label htmlFor="password">Password</label><input id="password" className="input" type="password" autoComplete="new-password" value={form.password} onChange={set("password")} /><p className="hint">8 to 72 characters</p></div>
        <div className="field"><label htmlFor="confirm">Confirm password</label><input id="confirm" className="input" type="password" autoComplete="new-password" value={form.confirm} onChange={set("confirm")} /></div>
        <button className="btn btn-primary btn-block" disabled={busy}>{busy ? "Creating…" : "Create account"}</button>
        <p className="auth-foot">Already have an account? <Link to="/login">Log in</Link></p>
      </form>
    </div>
  );
}
