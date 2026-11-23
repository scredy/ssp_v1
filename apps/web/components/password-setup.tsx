"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/car-api";
import { BrandLogo } from "@/components/public-site";

export default function PasswordSetup({ mode }: { mode: "invitation" | "password_reset" }) {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { setToken(new URLSearchParams(window.location.search).get("token") ?? ""); setReady(true); }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    const data = new FormData(event.currentTarget);
    const password = String(data.get("password") ?? "");
    if (password !== String(data.get("confirmation") ?? "")) { setError("The password confirmation does not match."); return; }
    setBusy(true);
    try {
      await api("/api/auth/password-setup/", { method: "POST", body: JSON.stringify({ token, password }) });
      router.replace("/staff/login?setup=complete");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "This secure link could not be used."); }
    finally { setBusy(false); }
  }

  const invitation = mode === "invitation";
  return <main className="auth-card account-auth-card">
    <BrandLogo className="login-logo" priority />
    <p className="eyebrow">SSP · STAFF PORTAL</p>
    <h1>{invitation ? "Set up your account" : "Reset your password"}</h1>
    <p className="description">{invitation ? "Choose a password to activate your individual SSP account." : "Choose a new password for your SSP account."}</p>
    {!ready ? <p className="state-card" role="status">Checking secure link…</p> : !token ? <p className="form-error" role="alert">This link is missing or invalid. Request a new email link.</p> : <form className="login-form" onSubmit={submit}>
      <label>New password<input name="password" type="password" required minLength={12} autoComplete="new-password" /></label>
      <label>Confirm password<input name="confirmation" type="password" required minLength={12} autoComplete="new-password" /></label>
      <p className="field-note">Use at least 12 characters. The server also checks its configured password rules.</p>
      {error && <p className="form-error" role="alert">{error}</p>}
      <button disabled={busy}>{busy ? "Saving password…" : "Set password securely"}</button>
    </form>}
    <Link className="back-link" href="/staff/login">← Back to sign in</Link>
  </main>;
}
