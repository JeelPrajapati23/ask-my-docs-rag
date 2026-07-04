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

export default function ResetPasswordModal({ onClose }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");
    if (!currentPassword || !newPassword || !confirmPassword) {
      setError("All fields are required."); return;
    }
    if (newPassword !== confirmPassword) {
      setError("New passwords do not match."); return;
    }
    if (newPassword.length < 8) {
      setError("New password must be at least 8 characters."); return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/auth/change-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || "Something went wrong."); return; }
      setSuccess(data.message);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setTimeout(onClose, 1600);
    } catch {
      setError("Cannot reach the backend. Make sure the API is running.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div onClick={onClose}
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 200,
        display: "flex", alignItems: "center", justifyContent: "center", fontFamily: T.sans }}>
      <style>{`.rp-input:focus { border-color: #c6f24a !important; outline: none; }`}</style>
      <div onClick={(e) => e.stopPropagation()}
        style={{ width: "100%", maxWidth: 400, margin: "0 20px",
          background: T.panel, border: `1px solid ${T.border2}`, borderRadius: 16,
          padding: "28px 28px 24px", boxShadow: "0 24px 64px rgba(0,0,0,0.7)" }}>

        {/* Header */}
        <div style={{ marginBottom: 22, borderBottom: `1px solid ${T.border}`, paddingBottom: 16 }}>
          <div style={{ fontFamily: T.sans, fontWeight: 700, fontSize: 16, color: T.ink }}>Reset Password</div>
          <div style={{ fontFamily: T.mono, fontSize: 11, color: T.muted, marginTop: 5 }}>
            Enter your current password and choose a new one.
          </div>
        </div>

        {/* Messages */}
        {error && (
          <div style={{ background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.25)",
            borderRadius: 8, padding: "10px 14px", marginBottom: 16,
            fontFamily: T.mono, fontSize: 12, color: "#f87171" }}>{error}</div>
        )}
        {success && (
          <div style={{ background: "rgba(198,242,74,0.08)", border: "1px solid rgba(198,242,74,0.25)",
            borderRadius: 8, padding: "10px 14px", marginBottom: 16,
            fontFamily: T.mono, fontSize: 12, color: T.accent }}>{success}</div>
        )}

        <form onSubmit={handleSubmit}>
          {[
            { label: "Current Password", val: currentPassword, set: setCurrentPassword, ac: "current-password" },
            { label: "New Password", val: newPassword, set: setNewPassword, ac: "new-password", hint: "(min 8 chars)" },
            { label: "Confirm New Password", val: confirmPassword, set: setConfirmPassword, ac: "new-password" },
          ].map(({ label, val, set, ac, hint }) => (
            <div key={label} style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontFamily: T.mono, fontSize: 10.5, color: T.muted,
                letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 6 }}>
                {label} {hint && <span style={{ opacity: 0.6 }}>{hint}</span>}
              </label>
              <input type="password" value={val} onChange={(e) => set(e.target.value)}
                placeholder="••••••••" autoComplete={ac} className="rp-input"
                style={{ width: "100%", boxSizing: "border-box", background: T.field,
                  border: `1px solid ${T.border2}`, borderRadius: 8,
                  padding: "10px 12px", color: T.ink, fontFamily: T.mono, fontSize: 13,
                  transition: "border-color .14s" }} />
            </div>
          ))}

          <div style={{ display: "flex", gap: 8, marginTop: 22 }}>
            <button type="button" onClick={onClose}
              style={{ flex: 1, padding: "10px 0", borderRadius: 9, background: "none",
                border: `1px solid ${T.border2}`, color: T.muted,
                fontFamily: T.sans, fontWeight: 500, fontSize: 13.5, cursor: "pointer" }}>
              Cancel
            </button>
            <button type="submit" disabled={loading}
              style={{ flex: 1, padding: "10px 0", borderRadius: 9,
                background: loading ? T.panel2 : T.accent,
                border: `1px solid ${loading ? T.border2 : T.accent}`,
                color: loading ? T.muted : T.accentInk,
                fontFamily: T.sans, fontWeight: 600, fontSize: 13.5,
                cursor: loading ? "default" : "pointer", transition: "filter .14s, background .14s" }}>
              {loading ? "Saving…" : "Save Password"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
