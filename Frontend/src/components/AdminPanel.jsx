import { useState, useEffect, useCallback } from "react";
import { IcClose, IcCheck, IcAlert } from "./icons.jsx";
import { API_BASE_URL } from "../utils/api.js";

const T = {
  bg: "#0a0b0d", panel: "#101216", panel2: "#15181d", field: "#0c0e11",
  ink: "#eef0f2", ink2: "#b6bbc2", muted: "#7c828c",
  border: "#22262d", border2: "#2c313a",
  accent: "#c6f24a", accentInk: "#0c1003",
  sans: "'Space Grotesk', sans-serif",
  mono: "'IBM Plex Mono', monospace",
};

const api = (path, opts) =>
  fetch(`${API_BASE_URL}${path}`, { credentials: "include", ...opts });

function Badge({ active, verified }) {
  if (!active) return <span style={{ fontFamily: T.mono, fontSize: 10, color: "#f87171", border: "1px solid rgba(248,113,113,0.3)", borderRadius: 4, padding: "1px 6px" }}>deactivated</span>;
  if (!verified) return <span style={{ fontFamily: T.mono, fontSize: 10, color: "#fbbf24", border: "1px solid rgba(251,191,36,0.3)", borderRadius: 4, padding: "1px 6px" }}>unverified</span>;
  return <span style={{ fontFamily: T.mono, fontSize: 10, color: T.accent, border: `1px solid rgba(198,242,74,0.3)`, borderRadius: 4, padding: "1px 6px" }}>active</span>;
}

export default function AdminPanel({ onClose }) {
  const [tab, setTab] = useState("users");
  const [users, setUsers] = useState([]);
  const [logs, setLogs] = useState([]);
  const [docs, setDocs] = useState([]);
  const [loadingAction, setLoadingAction] = useState(null);

  const fetchAll = useCallback(async () => {
    const [uRes, lRes, dRes] = await Promise.all([
      api("/admin/users"),
      api("/admin/audit-logs"),
      api("/admin/documents"),
    ]);
    if (uRes.ok) setUsers(await uRes.json());
    if (lRes.ok) setLogs(await lRes.json());
    if (dRes.ok) setDocs(await dRes.json());
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const toggleActive = async (user) => {
    setLoadingAction(user.id);
    const action = user.is_active ? "deactivate" : "activate";
    await api(`/admin/users/${user.id}/${action}`, { method: "PUT" });
    await fetchAll();
    setLoadingAction(null);
  };

  const tabs = ["users", "logs", "documents"];

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.65)", zIndex: 60,
      display: "flex", justifyContent: "flex-end",
    }} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: "min(680px, 100vw)", height: "100%", background: T.panel,
        borderLeft: `1px solid ${T.border2}`, display: "flex", flexDirection: "column",
        boxShadow: "-16px 0 48px rgba(0,0,0,0.5)",
      }}>
        {/* Header */}
        <div style={{
          height: 60, flexShrink: 0, borderBottom: `1px solid ${T.border}`,
          display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 20px",
        }}>
          <div>
            <span style={{ fontFamily: T.sans, fontWeight: 600, fontSize: 15, color: T.ink }}>Admin Panel</span>
            <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.accent, marginLeft: 10,
              border: `1px solid rgba(198,242,74,0.3)`, borderRadius: 4, padding: "2px 6px" }}>admin</span>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", color: T.muted,
            cursor: "pointer", padding: 6, borderRadius: 7, display: "grid", placeItems: "center" }}>
            <IcClose />
          </button>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", borderBottom: `1px solid ${T.border}`, flexShrink: 0 }}>
          {tabs.map((t) => (
            <button key={t} onClick={() => setTab(t)} style={{
              flex: 1, padding: "12px 0", background: "none",
              border: "none", borderBottom: tab === t ? `2px solid ${T.accent}` : "2px solid transparent",
              color: tab === t ? T.ink : T.muted,
              fontFamily: T.sans, fontWeight: tab === t ? 600 : 400, fontSize: 13,
              cursor: "pointer", textTransform: "capitalize", transition: "color .14s",
            }}>
              {t === "users" ? `Users (${users.length})` : t === "logs" ? `Audit Logs` : "Documents"}
            </button>
          ))}
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: "auto", padding: 20 }}>

          {/* Users Tab */}
          {tab === "users" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {users.map((u) => (
                <div key={u.id} style={{
                  background: T.panel2, border: `1px solid ${T.border2}`, borderRadius: 10,
                  padding: "12px 14px", display: "flex", alignItems: "center", gap: 12,
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                      <span style={{ fontFamily: T.sans, fontSize: 13.5, fontWeight: 600, color: T.ink,
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{u.email}</span>
                      {u.role === "admin" && (
                        <span style={{ fontFamily: T.mono, fontSize: 10, color: T.accent,
                          border: `1px solid rgba(198,242,74,0.3)`, borderRadius: 4, padding: "1px 6px", flexShrink: 0 }}>admin</span>
                      )}
                      <Badge active={u.is_active} verified={u.is_verified} />
                    </div>
                    <div style={{ fontFamily: T.mono, fontSize: 10.5, color: T.muted }}>
                      {new Date(u.created_at).toLocaleDateString()} · {u.id.slice(0, 8)}…
                    </div>
                  </div>
                  {u.role !== "admin" && (
                    <button
                      onClick={() => toggleActive(u)}
                      disabled={loadingAction === u.id}
                      style={{
                        padding: "6px 12px", borderRadius: 7, border: "none", cursor: "pointer",
                        fontFamily: T.mono, fontSize: 11, fontWeight: 500, flexShrink: 0,
                        background: u.is_active ? "rgba(248,113,113,0.12)" : "rgba(198,242,74,0.12)",
                        color: u.is_active ? "#f87171" : T.accent,
                        transition: "filter .14s",
                        opacity: loadingAction === u.id ? 0.5 : 1,
                      }}>
                      {u.is_active ? "Deactivate" : "Activate"}
                    </button>
                  )}
                </div>
              ))}
              {users.length === 0 && (
                <p style={{ fontFamily: T.mono, fontSize: 12, color: T.muted, textAlign: "center", paddingTop: 32 }}>No users yet.</p>
              )}
            </div>
          )}

          {/* Audit Logs Tab */}
          {tab === "logs" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {logs.map((l) => (
                <div key={l.id} style={{
                  background: T.panel2, border: `1px solid ${T.border}`, borderRadius: 8,
                  padding: "9px 12px", display: "grid",
                  gridTemplateColumns: "90px 90px 1fr auto", gap: "0 12px", alignItems: "center",
                }}>
                  <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.accent, fontWeight: 500 }}>
                    {l.action}
                  </span>
                  <span style={{ fontFamily: T.mono, fontSize: 10, color: T.muted, overflow: "hidden",
                    textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={l.user_id}>
                    {l.user_id ? l.user_id.slice(0, 8) + "…" : "—"}
                  </span>
                  <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.ink2, overflow: "hidden",
                    textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={l.detail}>
                    {l.detail || "—"}
                  </span>
                  <span style={{ fontFamily: T.mono, fontSize: 9.5, color: T.muted, whiteSpace: "nowrap" }}>
                    {new Date(l.created_at).toLocaleString()}
                  </span>
                </div>
              ))}
              {logs.length === 0 && (
                <p style={{ fontFamily: T.mono, fontSize: 12, color: T.muted, textAlign: "center", paddingTop: 32 }}>No logs yet.</p>
              )}
            </div>
          )}

          {/* Documents Tab */}
          {tab === "documents" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {docs.map((d, i) => (
                <div key={i} style={{
                  background: T.panel2, border: `1px solid ${T.border}`, borderRadius: 8,
                  padding: "9px 12px", display: "flex", alignItems: "center", gap: 12,
                }}>
                  <span style={{ color: T.accent, display: "flex" }}>
                    <IcCheck s={13} />
                  </span>
                  <span style={{ fontFamily: T.mono, fontSize: 12, color: T.ink, flex: 1,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {d.source_file}
                  </span>
                  <span style={{ fontFamily: T.mono, fontSize: 10, color: T.muted, flexShrink: 0 }} title={d.user_id}>
                    uid: {d.user_id.slice(0, 8)}…
                  </span>
                </div>
              ))}
              {docs.length === 0 && (
                <p style={{ fontFamily: T.mono, fontSize: 12, color: T.muted, textAlign: "center", paddingTop: 32 }}>No documents indexed yet.</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
