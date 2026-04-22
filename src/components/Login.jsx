import { useState } from "react";
import { login } from "../api";
import logo from "../assets/logo.png";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!username || !password) return;
    setLoading(true);
    setError("");
    try {
      await login(username, password);
      onLogin?.();
    } catch (err) {
      setError(err.message || "Login failed");
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bone px-6">
      <div className="w-full max-w-[400px] bg-white border border-ink/15 p-10">
        <div className="flex items-center gap-4 mb-8">
          <img src={logo} alt="PermitFlo" className="w-14 h-14 object-contain rounded-sm bg-steel-900/5 p-1.5" />
          <div>
            <div className="font-serif font-black text-2xl text-steel-900 leading-none">PermitFlo</div>
            <div className="text-[10px] text-amber-600 font-semibold uppercase tracking-[0.22em] mt-1.5">
              Est. 2025
            </div>
          </div>
        </div>

        <div className="eyebrow mb-2">Sign in</div>
        <span className="amber-rule mb-6" />

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-500 mb-2">
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
              disabled={loading}
              autoComplete="username"
            />
          </div>

          <div>
            <label className="block text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-500 mb-2">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              autoComplete="current-password"
            />
          </div>

          {error && (
            <div className="text-[12px] text-[#7A2C22] bg-[#9C3A2E]/10 border border-[#9C3A2E]/30 rounded-sm px-3 py-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !username || !password}
            className={`w-full py-3 rounded-sm text-[11px] font-semibold uppercase tracking-[0.06em] transition-colors border-none ${
              loading || !username || !password
                ? "bg-stone-100 text-ink-400 cursor-not-allowed"
                : "bg-amber text-white hover:bg-amber-600 cursor-pointer"
            }`}
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
