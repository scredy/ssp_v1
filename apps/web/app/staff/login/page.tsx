"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect } from "react";
import { BrandLogo } from "@/components/public-site";
import { api } from "@/lib/car-api";

export default function StaffLogin() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("setup") === "complete") setNotice("Your password is set. Sign in with your new password.");
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    const form = new FormData(event.currentTarget);
    try {
      await api("/api/auth/login/", {
        method: "POST", body: JSON.stringify({ username: form.get("username"), password: form.get("password") }),
      });
      router.replace("/staff");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to contact the sign-in service.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-card">
      <BrandLogo className="login-logo" priority />
      <p className="eyebrow">SSP · Staff portal</p>
      <h1>Sign in</h1>
      <p className="description">Use the account provided by your administrator.</p>
      {notice && <p className="account-reset-success" role="status">{notice}</p>}
      <form className="login-form" onSubmit={submit}>
        <label>Username<input name="username" autoComplete="username" required /></label>
        <label>Password<input name="password" type="password" autoComplete="current-password" required /></label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button disabled={busy}>{busy ? "Signing in…" : "Sign in securely"}</button>
      </form>
      <Link className="back-link" href="/staff/password-reset">Forgot your password?</Link>
      <a className="back-link" href="/">← Back to public website</a>
    </main>
  );
}
