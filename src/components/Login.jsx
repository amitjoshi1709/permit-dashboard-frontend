import { useState } from "react";
import { login } from "../api";

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
    <div className="min-h-screen flex items-center justify-center bg-navy">
      <div className="w-full max-w-[380px] bg-navy-2 border border-subtle rounded-[14px] p-8">
        <div className="text-center mb-6">
          <div className="text-[22px] font-bold text-txt-1">PermitFlo</div>
          <div className="text-[12px] text-txt-3 mt-1">Sign in to continue</div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
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
            <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
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
            <div className="text-[12px] text-permit-red2 bg-permit-red2/10 border border-permit-red2/30 rounded-md px-3 py-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !username || !password}
            className={`w-full py-3 rounded-lg text-sm font-medium transition-all font-sans border-none ${
              loading || !username || !password
                ? "bg-navy-3 text-txt-3 cursor-not-allowed"
                : "bg-accent text-white hover:bg-accent-2 cursor-pointer"
            }`}
          >
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
