import { useState, type FormEvent } from 'react';
import { api } from '../api/client';
import type { Identity } from '../types';

// Synthetic demo accounts (usernames only; the password is set by the server operator).
const ACCOUNTS = [
  ['northstar.lead', 'Northstar · software launch'],
  ['northstar.peer', 'Northstar · second user (own sessions only)'],
  ['harbor.lead', 'Harbor · logistics route change'],
  ['aw.quality', 'AdventureWorks · manufacturing quality hold'],
];

export function LoginScreen({ onSignedIn, notice }: { onSignedIn: (who: Identity) => void; notice?: string | null }) {
  const [username, setUsername] = useState('northstar.lead');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { onSignedIn(await api.login(username, password)); }
    catch (err) { setError(err instanceof Error ? err.message : 'Sign in failed'); setPassword(''); }
    finally { setBusy(false); }
  }
  return <main className="login">
    <form className="glass glass--l2 panel login__card" onSubmit={submit} aria-labelledby="login-title">
      <div className="brand" style={{ marginBottom: 18 }}><span className="brand__mark" aria-hidden /><span>Relay<b>Mind</b></span></div>
      <h1 id="login-title" className="h2">Sign in to your company workspace</h1>
      <p className="caption" style={{ margin: '6px 0 18px' }}>Each account sees only its own company graph and its own sessions.</p>
      {notice && <p className="alert alert--warn" role="status" style={{ marginBottom: 12 }}>{notice}</p>}
      <label className="field"><span>Account</span>
        <select value={username} onChange={e => setUsername(e.target.value)} disabled={busy}>
          {ACCOUNTS.map(([id, label]) => <option key={id} value={id}>{id} — {label}</option>)}
        </select></label>
      <label className="field"><span>Password</span>
        <input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)}
          disabled={busy} required /></label>
      {error && <p className="alert alert--danger" role="alert">{error}</p>}
      <button type="submit" className="btn btn--primary" disabled={busy || !password} style={{ width: '100%', justifyContent: 'center', marginTop: 8 }}>
        {busy ? 'Signing in…' : 'Sign in'}</button>
      <p className="caption" style={{ marginTop: 14 }}>Local demo authentication with synthetic accounts. Sessions are server-side and expire.</p>
    </form>
  </main>;
}
