"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/car-api";
import { BrandLogo } from "@/components/public-site";

export default function PasswordResetRequest() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setBusy(true);
    const email = String(new FormData(event.currentTarget).get("email") ?? "").trim();
    try {
      await api("/api/auth/password-reset/", { method: "POST", body: JSON.stringify({ email }) });
      setSent(true);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to submit the request. Try again shortly."); }
    finally { setBusy(false); }
  }
  return <main className="auth-card account-auth-card">
    <BrandLogo className="login-logo" priority />
    <p className="eyebrow">SSP · STAFF PORTAL</p>
    <h1>Reset your password</h1>
    {sent ? <p className="account-reset-success" role="status">If an active account matches that email address, a reset link has been sent. Check your inbox.</p> : <>
      <p className="description">Enter your account email. For privacy, the confirmation is the same whether or not it matches an active account.</p>
      <form className="login-form" onSubmit={submit}>
        <label>Email<input name="email" type="email" autoComplete="email" required /></label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button disabled={busy}>{busy ? "Sending…" : "Send reset link"}</button>
      </form>
    </>}
    <Link className="back-link" href="/staff/login">← Back to sign in</Link>
  </main>;
}
