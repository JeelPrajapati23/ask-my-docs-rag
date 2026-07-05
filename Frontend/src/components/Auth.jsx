import { useState } from "react";
import { API_BASE_URL } from "../utils/api.js";

const T = {
  bg: "#0a0b0d", panel: "#101216", panel2: "#15181d", field: "#0c0e11",
  ink: "#eef0f2", ink2: "#b6bbc2", muted: "#7c828c",
  border: "#22262d", border2: "#2c313a",
  accent: "#c6f24a", accentInk: "#0c1003",
  sans: "'Space Grotesk', sans-serif",
  mono: "'IBM Plex Mono', monospace",
};

export default function Auth({ onLogin, initialResetToken }) {
  const [mode, setMode] = useState(() => initialResetToken ? "reset" : "login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const switchMode = (next) => {
    setMode(next);
    setError("");
    setSuccess("");
    setPassword("");
    setNewPassword("");
    setConfirmPassword("");
  };

  // ── Login / Register ──────────────────────────────────────────────────────
  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");
    if (!email.trim() || !password) { setError("Email and password are required."); return; }
    setLoading(true);
    try {
      const endpoint = mode === "login" ? "/auth/login" : "/auth/register";
      const res = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email: email.trim(), password }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || "Something went wrong."); return; }
      if (mode === "register") {
        setSuccess(data.message);
        const loginRes = await fetch(`${API_BASE_URL}/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ email: email.trim(), password }),
        });
        if (loginRes.ok) {
          const loginData = await loginRes.json();
          onLogin({ id: loginData.id, email: loginData.email, role: loginData.role });
        }
      } else {
        onLogin({ id: data.id, email: data.email, role: data.role });
      }
    } catch {
      setError("Cannot reach the backend. Make sure the API is running.");
    } finally {
      setLoading(false);
    }
  };

  // ── Forgot password ───────────────────────────────────────────────────────
  const handleForgot = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");
    if (!email.trim()) { setError("Please enter your email address."); return; }
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || "Something went wrong."); return; }
      setSuccess(data.message);
      setEmail("");
    } catch {
      setError("Cannot reach the backend. Make sure the API is running.");
    } finally {
      setLoading(false);
    }
  };

  // ── Reset password (via email link token) ─────────────────────────────────
  const handleReset = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");
    if (!newPassword || !confirmPassword) { setError("Please fill in both password fields."); return; }
    if (newPassword !== confirmPassword) { setError("Passwords do not match."); return; }
    if (newPassword.length < 8) { setError("Password must be at least 8 characters."); return; }
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: initialResetToken, new_password: newPassword }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || "Something went wrong."); return; }
      setSuccess(data.message);
      setNewPassword("");
      setConfirmPassword("");
      // Clear the token from the URL and switch to login
      window.history.replaceState({}, "", "/");
      setTimeout(() => switchMode("login"), 1800);
    } catch {
      setError("Cannot reach the backend. Make sure the API is running.");
    } finally {
      setLoading(false);
    }
  };

  const isLoginRegister = mode === "login" || mode === "register";

  return (
    <div style={{
      position: "fixed", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
      background: T.bg, fontFamily: T.sans,
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');
        .auth-input:focus { border-color: #c6f24a !important; outline: none; }
        .auth-btn-primary:hover:not(:disabled) { filter: brightness(1.08); }
        .auth-tab:hover { color: #eef0f2 !important; }
        .auth-link:hover { color: #c6f24a !important; }
      `}</style>

      <div style={{ width: "100%", maxWidth: 420, padding: "0 20px" }}>
        {/* Logo */}
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <div style={{
            width: 48, height: 48, borderRadius: 13, background: T.accent,
            display: "grid", placeItems: "center", margin: "0 auto 16px",
            color: T.accentInk, fontWeight: 700, fontSize: 22, fontFamily: T.sans,
          }}>B</div>
          <h1 style={{ fontFamily: T.sans, fontSize: 22, fontWeight: 700, color: T.ink, margin: 0 }}>
            Ask My Docs
          </h1>
          <p style={{ fontFamily: T.mono, fontSize: 11, color: T.muted, marginTop: 6, letterSpacing: "0.08em" }}>
            RAG · legal document intelligence
          </p>
        </div>

        {/* Card */}
        <div style={{
          background: T.panel, border: `1px solid ${T.border2}`, borderRadius: 16, padding: "28px 28px 24px",
        }}>

          {/* ── Tabs (login / register only) ── */}
          {isLoginRegister && (
            <div style={{ display: "flex", gap: 4, marginBottom: 24, borderBottom: `1px solid ${T.border}`, paddingBottom: 16 }}>
              {["login", "register"].map((tab) => (
                <button key={tab} onClick={() => switchMode(tab)} className="auth-tab"
                  style={{
                    flex: 1, padding: "8px 0", borderRadius: 8, border: "none",
                    background: mode === tab ? T.panel2 : "transparent",
                    color: mode === tab ? T.ink : T.muted,
                    fontFamily: T.sans, fontWeight: mode === tab ? 600 : 400, fontSize: 13.5,
                    cursor: "pointer", transition: "all .14s",
                    borderBottom: mode === tab ? `2px solid ${T.accent}` : "2px solid transparent",
                  }}>
                  {tab === "login" ? "Sign In" : "Create Account"}
                </button>
              ))}
            </div>
          )}

          {/* ── Forgot / Reset heading ── */}
          {(mode === "forgot" || mode === "reset") && (
            <div style={{ marginBottom: 22, borderBottom: `1px solid ${T.border}`, paddingBottom: 16 }}>
              <div style={{ fontFamily: T.sans, fontWeight: 700, fontSize: 16, color: T.ink }}>
                {mode === "forgot" ? "Forgot your password?" : "Set a new password"}
              </div>
              <div style={{ fontFamily: T.mono, fontSize: 11, color: T.muted, marginTop: 5, lineHeight: 1.55 }}>
                {mode === "forgot"
                  ? "Enter your email and we'll send you a reset link."
                  : "Enter and confirm your new password below."}
              </div>
            </div>
          )}

          {/* ── Messages ── */}
          {error && (
            <div style={{
              background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.25)",
              borderRadius: 8, padding: "10px 14px", marginBottom: 16,
              fontFamily: T.mono, fontSize: 12, color: "#f87171",
            }}>{error}</div>
          )}
          {success && (
            <div style={{
              background: "rgba(198,242,74,0.08)", border: "1px solid rgba(198,242,74,0.25)",
              borderRadius: 8, padding: "10px 14px", marginBottom: 16,
              fontFamily: T.mono, fontSize: 12, color: T.accent,
            }}>{success}</div>
          )}

          {/* ── Login / Register form ── */}
          {isLoginRegister && (
            <form onSubmit={handleSubmit}>
              <div style={{ marginBottom: 14 }}>
                <label style={{ display: "block", fontFamily: T.mono, fontSize: 10.5, color: T.muted,
                  letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 6 }}>Email</label>
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com" autoComplete="email" className="auth-input"
                  style={{ width: "100%", boxSizing: "border-box", background: T.field,
                    border: `1px solid ${T.border2}`, borderRadius: 8,
                    padding: "10px 12px", color: T.ink, fontFamily: T.mono, fontSize: 13,
                    transition: "border-color .14s" }} />
              </div>
              <div style={{ marginBottom: mode === "login" ? 8 : 22 }}>
                <label style={{ display: "block", fontFamily: T.mono, fontSize: 10.5, color: T.muted,
                  letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 6 }}>
                  Password {mode === "register" && <span style={{ opacity: 0.6 }}>(min 8 chars)</span>}
                </label>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••" autoComplete={mode === "login" ? "current-password" : "new-password"}
                  className="auth-input"
                  style={{ width: "100%", boxSizing: "border-box", background: T.field,
                    border: `1px solid ${T.border2}`, borderRadius: 8,
                    padding: "10px 12px", color: T.ink, fontFamily: T.mono, fontSize: 13,
                    transition: "border-color .14s" }} />
              </div>

              {/* Forgot password link — only on login tab */}
              {mode === "login" && (
                <div style={{ textAlign: "right", marginBottom: 18 }}>
                  <button type="button" onClick={() => switchMode("forgot")} className="auth-link"
                    style={{ background: "none", border: "none", cursor: "pointer",
                      fontFamily: T.mono, fontSize: 11, color: T.muted, transition: "color .14s", padding: 0 }}>
                    Forgot password?
                  </button>
                </div>
              )}

              <button type="submit" disabled={loading} className="auth-btn-primary"
                style={{ width: "100%", padding: "11px 0", borderRadius: 9,
                  background: loading ? T.panel2 : T.accent,
                  border: `1px solid ${loading ? T.border2 : T.accent}`,
                  color: loading ? T.muted : T.accentInk,
                  fontFamily: T.sans, fontWeight: 600, fontSize: 14,
                  cursor: loading ? "default" : "pointer", transition: "filter .14s, background .14s" }}>
                {loading ? "Please wait…" : mode === "login" ? "Sign In" : "Create Account"}
              </button>
            </form>
          )}

          {/* ── Forgot password form ── */}
          {mode === "forgot" && (
            <form onSubmit={handleForgot}>
              <div style={{ marginBottom: 22 }}>
                <label style={{ display: "block", fontFamily: T.mono, fontSize: 10.5, color: T.muted,
                  letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 6 }}>Email</label>
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com" autoComplete="email" className="auth-input"
                  style={{ width: "100%", boxSizing: "border-box", background: T.field,
                    border: `1px solid ${T.border2}`, borderRadius: 8,
                    padding: "10px 12px", color: T.ink, fontFamily: T.mono, fontSize: 13,
                    transition: "border-color .14s" }} />
              </div>
              <button type="submit" disabled={loading} className="auth-btn-primary"
                style={{ width: "100%", padding: "11px 0", borderRadius: 9,
                  background: loading ? T.panel2 : T.accent,
                  border: `1px solid ${loading ? T.border2 : T.accent}`,
                  color: loading ? T.muted : T.accentInk,
                  fontFamily: T.sans, fontWeight: 600, fontSize: 14,
                  cursor: loading ? "default" : "pointer", transition: "filter .14s, background .14s" }}>
                {loading ? "Sending…" : "Send Reset Link"}
              </button>
              <button type="button" onClick={() => switchMode("login")}
                style={{ marginTop: 12, width: "100%", padding: "9px 0", borderRadius: 9,
                  background: "none", border: `1px solid ${T.border2}`,
                  color: T.muted, fontFamily: T.sans, fontWeight: 500, fontSize: 13.5,
                  cursor: "pointer" }}>
                Back to Sign In
              </button>
            </form>
          )}

          {/* ── Reset password form ── */}
          {mode === "reset" && (
            <form onSubmit={handleReset}>
              <div style={{ marginBottom: 14 }}>
                <label style={{ display: "block", fontFamily: T.mono, fontSize: 10.5, color: T.muted,
                  letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 6 }}>
                  New Password <span style={{ opacity: 0.6 }}>(min 8 chars)</span>
                </label>
                <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="••••••••" autoComplete="new-password" className="auth-input"
                  style={{ width: "100%", boxSizing: "border-box", background: T.field,
                    border: `1px solid ${T.border2}`, borderRadius: 8,
                    padding: "10px 12px", color: T.ink, fontFamily: T.mono, fontSize: 13,
                    transition: "border-color .14s" }} />
              </div>
              <div style={{ marginBottom: 22 }}>
                <label style={{ display: "block", fontFamily: T.mono, fontSize: 10.5, color: T.muted,
                  letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 6 }}>
                  Confirm Password
                </label>
                <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="••••••••" autoComplete="new-password" className="auth-input"
                  style={{ width: "100%", boxSizing: "border-box", background: T.field,
                    border: `1px solid ${T.border2}`, borderRadius: 8,
                    padding: "10px 12px", color: T.ink, fontFamily: T.mono, fontSize: 13,
                    transition: "border-color .14s" }} />
              </div>
              <button type="submit" disabled={loading} className="auth-btn-primary"
                style={{ width: "100%", padding: "11px 0", borderRadius: 9,
                  background: loading ? T.panel2 : T.accent,
                  border: `1px solid ${loading ? T.border2 : T.accent}`,
                  color: loading ? T.muted : T.accentInk,
                  fontFamily: T.sans, fontWeight: 600, fontSize: 14,
                  cursor: loading ? "default" : "pointer", transition: "filter .14s, background .14s" }}>
                {loading ? "Saving…" : "Set New Password"}
              </button>
            </form>
          )}

          {mode === "register" && (
            <p style={{ fontFamily: T.mono, fontSize: 11, color: T.muted, textAlign: "center", marginTop: 16, lineHeight: 1.6 }}>
              The first account created becomes the admin.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
