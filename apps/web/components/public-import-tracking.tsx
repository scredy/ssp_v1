"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/car-api";

type PublicTracking = { tracking_reference: string; import_reference: string; status: string; estimated_arrival: string | null; customer_updates: string; milestones: { kind: string; occurred_at: string; description: string }[] };
const when = (v: string) => new Intl.DateTimeFormat("en-LK", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Colombo" }).format(new Date(v)) + " SLST";
const label = (v: string) => v.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());

export default function PublicImportTracking() {
  const [reference, setReference] = useState("");
  const [pin, setPin] = useState("");
  const [result, setResult] = useState<PublicTracking | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const submitLock = useRef(false);

  async function track(event: React.FormEvent) {
    event.preventDefault();
    if (submitLock.current || !reference.trim() || !pin) return;
    submitLock.current = true; setLoading(true); setError(""); setResult(null);
    const enteredPin = pin;
    setPin("");
    try {
      setResult(await api<PublicTracking>("/api/public/import-tracking/", { method: "POST", body: JSON.stringify({ tracking_reference: reference.trim(), pin: enteredPin }) }));
    } catch (e) {
      const message = e instanceof Error ? e.message : "";
      setError(message.toLowerCase().includes("throttled") ? "Too many attempts. Please wait before trying again." : "Tracking reference or PIN could not be verified. Check the details and try again.");
    } finally { submitLock.current = false; setLoading(false); }
  }

  const currentIndex = (result?.milestones.length || 0) - 1;
  return <main className="public-main tracking-main">
    <section className="public-page-heading"><p className="public-eyebrow">SECURE IMPORT TRACKING</p><h1>Track your vehicle</h1><p>Enter the tracking reference and PIN provided by SSP to view approved import updates.</p></section>
    <div className="public-tracking-layout"><form className="public-tracking-form" onSubmit={track}>
      <h2>Access your tracking</h2><p>Tracking credentials are checked securely and are never added to the page address.</p>
      <label>Tracking reference *<input required autoComplete="off" maxLength={32} value={reference} onChange={(e) => setReference(e.target.value)} placeholder="TRK-…"/></label>
      <label>PIN *<input required type="password" autoComplete="one-time-code" maxLength={128} value={pin} onChange={(e) => setPin(e.target.value)} placeholder="Enter your secure PIN"/></label>
      {error && <p className="public-tracking-error" role="alert">{error}</p>}
      <button className="public-button public-button-red" disabled={loading || !reference.trim() || !pin}>{loading ? "Checking…" : "Track vehicle"}</button>
      <small>Your PIN is cleared from this form after each attempt. It is not saved in browser storage.</small>
    </form>
    <section className="public-tracking-result" aria-live="polite">{result ? <>
      <div className="public-track-summary"><div><p className="public-eyebrow">TRACKING RESULT</p><h2>{result.import_reference}</h2></div><span className="import-status is-current">{label(result.status)}</span></div>
      <dl><div><dt>Import reference</dt><dd>{result.import_reference}</dd></div><div><dt>Current import status</dt><dd>{label(result.status)}</dd></div><div><dt>Estimated arrival</dt><dd>{result.estimated_arrival || "Not available"}</dd></div></dl>
      {result.customer_updates && <section className="public-tracking-update"><p className="public-eyebrow">CUSTOMER UPDATE</p><p>{result.customer_updates}</p></section>}
      <div className="public-track-timeline"><h3>Progress timeline</h3>{result.milestones.length ? <ol>{result.milestones.map((item, index) => <li key={`${item.kind}-${item.occurred_at}`} className={index === currentIndex ? "is-current" : "is-complete"}><span className="public-track-dot"/><div><strong>{label(item.kind)}</strong>{index === currentIndex && <span className="public-track-current-tag">Current milestone</span>}<time>{when(item.occurred_at)}</time><p>{item.description}</p></div></li>)}</ol> : <p>No customer-visible milestones are available yet.</p>}</div>
      <p className="public-track-note">This page shows only customer-approved progress updates. It does not confirm payment or handover unless a specific milestone is displayed.</p>
    </> : <div className="public-track-empty"><span aria-hidden="true">◎</span><h2>Tracking details will appear here</h2><p>After verifying your reference and PIN, you can review import progress and customer updates.</p></div>}</section></div>
  </main>;
}
