import { useState, useEffect } from "react";
import Chat from "./chat.jsx";
import Auth from "./components/Auth.jsx";
import { API_BASE_URL } from "./utils/api.js";

function LoadingScreen() {
  return (
    <div style={{
      position: "fixed", inset: 0, background: "#0a0b0d",
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <div style={{
        width: 40, height: 40, borderRadius: 10, background: "#c6f24a",
        display: "grid", placeItems: "center",
        color: "#0c1003", fontWeight: 700, fontSize: 18,
        fontFamily: "'Space Grotesk', sans-serif",
        animation: "pulse 1.4s ease-in-out infinite",
      }}>B</div>
      <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }`}</style>
    </div>
  );
}

export default function App() {
  // null = still loading, false = not authenticated, object = authenticated user
  const [authUser, setAuthUser] = useState(null);
  const [resetToken] = useState(() => {
    const p = new URLSearchParams(window.location.search);
    return p.get("reset_token") || null;
  });

  useEffect(() => {
    fetch(`${API_BASE_URL}/auth/me`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((user) => setAuthUser(user || false))
      .catch(() => setAuthUser(false));
  }, []);

  // If a reset_token is in the URL, always show Auth in reset mode
  if (resetToken) return <Auth onLogin={setAuthUser} initialResetToken={resetToken} />;
  if (authUser === null) return <LoadingScreen />;
  if (!authUser) return <Auth onLogin={setAuthUser} />;
  return <Chat authUser={authUser} onLogout={() => setAuthUser(false)} />;
}
