import { useState } from "react";
import { api } from "../api.js";

export default function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("login"); // "login" | "register"
  const [form, setForm] = useState({ username: "", email: "", password: "", full_name: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function updateField(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "register") {
        await api.register({
          username: form.username,
          email: form.email,
          password: form.password,
          full_name: form.full_name || undefined,
        });
        // auto-login right after registering
      }
      const { access_token } = await api.login({ username: form.username, password: form.password });
      api.setToken(access_token);
      onAuthenticated();
    } catch (err) {
      setError(err.message || "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <h1>TaskFlow</h1>
        <p className="subtitle">Project & task management</p>

        <div className="tab-row">
          <button
            className={mode === "login" ? "tab active" : "tab"}
            onClick={() => setMode("login")}
            type="button"
          >
            Log in
          </button>
          <button
            className={mode === "register" ? "tab active" : "tab"}
            onClick={() => setMode("register")}
            type="button"
          >
            Register
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          {mode === "register" && (
            <input
              placeholder="Full name"
              value={form.full_name}
              onChange={(e) => updateField("full_name", e.target.value)}
            />
          )}
          <input
            placeholder="Username"
            value={form.username}
            onChange={(e) => updateField("username", e.target.value)}
            required
          />
          {mode === "register" && (
            <input
              placeholder="Email"
              type="email"
              value={form.email}
              onChange={(e) => updateField("email", e.target.value)}
              required
            />
          )}
          <input
            placeholder="Password"
            type="password"
            value={form.password}
            onChange={(e) => updateField("password", e.target.value)}
            required
          />

          {error && <div className="error">{error}</div>}

          <button className="primary" type="submit" disabled={busy}>
            {busy ? "Please wait..." : mode === "login" ? "Log in" : "Create account"}
          </button>
        </form>
      </div>
    </div>
  );
}
