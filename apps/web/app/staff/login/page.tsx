"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function csrfToken() {
  return document.cookie.split("; ").find((item) => item.startsWith("csrftoken="))?.split("=")[1] ?? "";
}

export default function StaffLogin() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    const form = new FormData(event.currentTarget);
    try {
      await fetch(`${API}/api/auth/csrf/`, { credentials: "include" });
      const response = await fetch(`${API}/api/auth/login/`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": decodeURIComponent(csrfToken()) },
        body: JSON.stringify({ username: form.get("username"), password: form.get("password") }),
      });
      if (!response.ok) throw new Error("Sign in failed. Check your details and try again.");
      router.replace("/staff");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to contact the sign-in service.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-card">
      <p className="eyebrow">SSP · Staff portal</p>
      <h1>Sign in</h1>
      <p className="description">Use the account provided by your administrator.</p>
      <form className="login-form" onSubmit={submit}>
        <label>Username<input name="username" autoComplete="username" required /></label>
        <label>Password<input name="password" type="password" autoComplete="current-password" required /></label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button disabled={busy}>{busy ? "Signing in…" : "Sign in securely"}</button>
      </form>
      <a className="back-link" href="/">← Back to public website</a>
    </main>
  );
}
