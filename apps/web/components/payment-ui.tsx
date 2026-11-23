"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, API } from "@/lib/car-api";

export type PaymentRecord = {
  reference: string; sale_reference: string | null; reservation_reference: string | null; import_reference: string | null;
  customer_name: string; amount_lkr: string; method: string; transaction_reference: string;
  payment_date: string; notes: string; recorded_by_name: string; created_at: string;
  status: "pending" | "verified" | "rejected"; verified_by_name: string | null;
  verified_at: string | null; rejected_by_name: string | null; rejected_at: string | null;
  rejection_reason: string; evidence_attached: boolean; evidence_url: string | null;
};
type PaymentSummary = {
  sale_reference?: string; reservation_reference?: string; import_reference?: string; linked_sale_reference?: string | null;
  sale_price_lkr?: string; agreed_price_lkr?: string;
  advance_declared_unverified_lkr?: string; verified_received_lkr?: string;
  pending_verification_lkr?: string; outstanding_balance_lkr?: string;
  verified_amount_lkr?: string; pending_amount_lkr?: string; rejected_amount_lkr?: string;
};
const money = (v: string | number) => new Intl.NumberFormat("en-LK", { style: "currency", currency: "LKR", maximumFractionDigits: 2 }).format(Number(v || 0));
const slTime = (v: string | null) => v ? new Intl.DateTimeFormat("en-LK", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Colombo" }).format(new Date(v)) + " SLST" : "—";
const statusTitle = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export function PaymentPanel({ kind, reference, linkedReference, canRecord }: { kind: "sale" | "reservation" | "import"; reference: string; linkedReference?: string | null; canRecord: boolean }) {
  const [summary, setSummary] = useState<PaymentSummary | null>(null);
  const [payments, setPayments] = useState<PaymentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const summaryPath = kind === "sale" ? `/api/manager/sales/${encodeURIComponent(reference)}/payments/summary/` : kind === "reservation" ? `/api/staff/reservations/${encodeURIComponent(reference)}/payments/summary/` : `/api/staff/imports/${encodeURIComponent(reference)}/payments/summary/`;
      const current = await api<PaymentSummary>(summaryPath);
      setSummary(current);
      const refs = new Set([reference, linkedReference || "", current.linked_sale_reference || ""].filter(Boolean));
      const chunks = await Promise.all([...refs].map((ref) => api<PaymentRecord[]>(`/api/staff/payments/?search=${encodeURIComponent(ref)}`)));
      setPayments([...new Map(chunks.flat().filter((p) => p.sale_reference === reference || p.reservation_reference === reference || p.import_reference === reference || p.sale_reference === linkedReference || p.reservation_reference === linkedReference || p.sale_reference === current.linked_sale_reference || p.reservation_reference === current.linked_sale_reference).map((p) => [p.reference, p])).values()]);
    } catch (e) { setError(e instanceof Error ? e.message : "Payment information could not be loaded."); }
    finally { setLoading(false); }
  }, [kind, reference, linkedReference]);
  useEffect(() => { void load(); }, [load]);
  const price = kind === "import" ? undefined : summary?.sale_price_lkr ?? summary?.agreed_price_lkr ?? (summary ? Number(summary.verified_received_lkr || 0) + Number(summary.outstanding_balance_lkr || 0) : undefined);
  const verified = kind === "import" ? summary?.verified_amount_lkr : summary?.verified_received_lkr;
  const pending = kind === "import" ? summary?.pending_amount_lkr : summary?.pending_verification_lkr;
  const targetType = kind;
  return <section className="payment-panel">
    <div className="payment-panel-heading"><div><p className="eyebrow">PAYMENTS</p><h3>Payment summary</h3></div>{canRecord && <Link className="primary-button" href={`/staff/payments?target_type=${targetType}&reference=${encodeURIComponent(reference)}`}>Record payment</Link>}</div>
    {loading ? <p className="public-state">Loading payment summary…</p> : error ? <p className="reservation-feedback is-error" role="alert">{error}</p> : <>
      {summary?.advance_declared_unverified_lkr !== undefined && <p className="payment-declared">Declared reservation advance · not a recorded or verified payment: <strong>{money(summary.advance_declared_unverified_lkr)}</strong></p>}
      <div className="payment-summary-grid">{price !== undefined && <article><span>Agreed price</span><strong>{money(price)}</strong></article>}<article><span>Verified received</span><strong>{money(verified || 0)}</strong></article><article><span>Pending verification</span><strong>{money(pending || 0)}</strong></article>{kind === "import" ? <article><span>Rejected</span><strong>{money(summary?.rejected_amount_lkr || 0)}</strong></article> : <article><span>Outstanding balance</span><strong>{money(summary?.outstanding_balance_lkr || 0)}</strong></article>}</div>
      <div className="payment-history"><h4>Payment history</h4>{payments.length === 0 ? <p>No recorded payments for this transaction.</p> : <div className="payment-history-list">{payments.map((p) => <article key={p.reference}><div><strong>{p.reference}</strong><span className={`payment-status is-${p.status}`}>{statusTitle(p.status)}</span></div><p>{money(p.amount_lkr)} · {p.method.replaceAll("_", " ")} · {p.payment_date}</p><small>Recorded by {p.recorded_by_name}</small>{p.evidence_attached && p.evidence_url && <a href={`${API}${p.evidence_url}`} target="_blank" rel="noreferrer">Open private evidence</a>}</article>)}</div>}</div>
    </>}
  </section>;
}

type CurrentUser = { role: string; username: string };
type DashboardSummary = { pending_count: number; verified_count: number; rejected_count: number; pending_amount_lkr: string; verified_amount_lkr: string };
const today = () => { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); };

export default function StaffPayments() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [rows, setRows] = useState<PaymentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [method, setMethod] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [selected, setSelected] = useState<PaymentRecord | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [targetType, setTargetType] = useState<"sale" | "reservation" | "import">("sale");
  const [reference, setReference] = useState("");
  const [amount, setAmount] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("cash");
  const [transactionReference, setTransactionReference] = useState("");
  const [paymentDate, setPaymentDate] = useState(today());
  const [evidence, setEvidence] = useState<File | null>(null);
  const [notes, setNotes] = useState("");
  const [formSummary, setFormSummary] = useState<PaymentSummary | null>(null);
  const [summaryError, setSummaryError] = useState("");
  const [busy, setBusy] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const submitLock = useRef(false);

  useEffect(() => {
    fetch(`${API}/api/auth/me/`, { credentials: "include" }).then((r) => { if (!r.ok) throw new Error(); return r.json(); }).then((u: CurrentUser) => {
      if (!["staff", "manager", "ceo"].includes(u.role)) throw new Error(); setUser(u);
    }).catch(() => { window.location.assign("/staff/login"); });
    const params = new URLSearchParams(window.location.search);
    const type = params.get("target_type"); if (type === "sale" || type === "reservation" || type === "import") { setTargetType(type); setShowForm(true); }
    setReference(params.get("reference") || "");
  }, []);

  const load = useCallback(async () => {
    if (!user) return;
    setLoading(true); setError("");
    try {
      const p = new URLSearchParams(); if (search.trim()) p.set("search", search.trim()); if (status) p.set("status", status); if (method) p.set("method", method);
      let list = await api<PaymentRecord[]>(`/api/staff/payments/?${p}`);
      if (fromDate) list = list.filter((x) => x.payment_date >= fromDate);
      if (toDate) list = list.filter((x) => x.payment_date <= toDate);
      setRows(list);
    } catch (e) { setError(e instanceof Error ? e.message : "Payments could not be loaded."); }
    finally { setLoading(false); }
  }, [user, search, status, method, fromDate, toDate]);
  useEffect(() => { void load(); }, [load]);

  const summaryPath = (type: "sale" | "reservation" | "import", ref: string) => type === "sale" ? `/api/manager/sales/${encodeURIComponent(ref)}/payments/summary/` : type === "reservation" ? `/api/staff/reservations/${encodeURIComponent(ref)}/payments/summary/` : `/api/staff/imports/${encodeURIComponent(ref)}/payments/summary/`;
  async function refreshTargetSummary(type = targetType, ref = reference) {
    if (!ref.trim()) { setFormSummary(null); return; }
    setSummaryError("");
    try { setFormSummary(await api<PaymentSummary>(summaryPath(type, ref.trim()))); }
    catch (e) { setFormSummary(null); setSummaryError(e instanceof Error ? e.message : "Balance summary unavailable."); }
  }
  useEffect(() => { if (showForm && reference) void refreshTargetSummary(targetType, reference); /* prefilled target */ }, [showForm]);
  const canRecord = user?.role === "staff" || user?.role === "manager";
  const canReview = user?.role === "manager" || user?.role === "ceo";
  const pendingAllowance = Number(formSummary?.outstanding_balance_lkr || 0) - Number(formSummary?.pending_verification_lkr || 0);
  const amountInvalid = !amount || Number(amount) <= 0 || (targetType !== "import" && formSummary !== null && Number(amount) > Math.max(0, pendingAllowance));

  async function submit(e: React.FormEvent) {
    e.preventDefault(); if (submitLock.current || amountInvalid || !reference.trim()) return;
    submitLock.current = true;
    setBusy(true); setError(""); setNotice("");
    try {
      const data = new FormData(); data.set(targetType === "sale" ? "sale_reference" : targetType === "reservation" ? "reservation_reference" : "import_reference", reference.trim());
      data.set("amount_lkr", amount); data.set("method", paymentMethod); data.set("payment_date", paymentDate);
      data.set("transaction_reference", transactionReference.trim()); data.set("notes", notes.trim()); if (evidence) data.set("evidence", evidence);
      const created = await api<PaymentRecord>("/api/staff/payments/", { method: "POST", body: data });
      setNotice(`Payment ${created.reference} recorded as pending verification.`); setAmount(""); setTransactionReference(""); setEvidence(null); setNotes(""); await load(); await refreshTargetSummary();
    } catch (e) { setError(e instanceof Error ? e.message : "Payment could not be recorded."); }
    finally { submitLock.current = false; setBusy(false); }
  }

  async function review(action: "verify" | "reject") {
    if (!selected || busy || (action === "reject" && !rejectReason.trim())) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<PaymentRecord>(`/api/staff/payments/${encodeURIComponent(selected.reference)}/${action}/`, { method: "POST", body: JSON.stringify(action === "reject" ? { rejection_reason: rejectReason.trim() } : {}) });
      setSelected(result); setRejectReason(""); setNotice(`${result.reference} ${action === "verify" ? "verified" : "rejected"}.`); await load();
    } catch (e) { setError(e instanceof Error ? e.message : `Payment could not be ${action === "verify" ? "verified" : "rejected"}.`); }
    finally { setBusy(false); }
  }

  return <div className="payments-page">
    <div className="payments-title-row"><div><p className="eyebrow">PAYMENT OPERATIONS</p><h2>Payments directory</h2><p>Review recorded payments and their verification status.</p></div>{canRecord && <button className="primary-button" onClick={() => { setShowForm((v) => !v); setError(""); }}>+ Record payment</button>}</div>
    {error && <p className="reservation-feedback is-error" role="alert">{error}</p>}{notice && <p className="reservation-feedback" role="status">{notice}</p>}
    {showForm && canRecord && <form className="reservation-form payment-form" onSubmit={submit}>
      <div className="reservation-form-heading"><div><p className="eyebrow">NEW PAYMENT</p><h2>Record payment</h2></div><button type="button" className="inventory-secondary" onClick={() => setShowForm(false)}>Close</button></div>
      <div className="payment-target-switch" role="group" aria-label="Payment target"><button type="button" className={targetType === "sale" ? "is-active" : ""} onClick={() => { setTargetType("sale"); setFormSummary(null); }}>Sale</button><button type="button" className={targetType === "reservation" ? "is-active" : ""} onClick={() => { setTargetType("reservation"); setFormSummary(null); }}>Reservation</button><button type="button" className={targetType === "import" ? "is-active" : ""} onClick={() => { setTargetType("import"); setFormSummary(null); }}>Import Order</button></div>
      <div className="reservation-form-grid">
        <label>{targetType === "sale" ? "Sale reference" : targetType === "reservation" ? "Reservation reference" : "Import reference"} *<div className="payment-reference-field"><input required value={reference} onChange={(e) => { setReference(e.target.value); setFormSummary(null); }} onBlur={() => void refreshTargetSummary()} placeholder={targetType === "sale" ? "e.g. SAL-0001" : targetType === "reservation" ? "e.g. RSV-0001" : "e.g. IMP-…"}/>{targetType !== "import" && <button type="button" className="inventory-secondary" disabled={!reference.trim()} onClick={() => void refreshTargetSummary()}>Check balance</button>}</div></label>
        <label>Amount (LKR) *<input required type="number" min="0.01" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)}/></label>
        <label>Payment method *<select required value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value)}><option value="cash">Cash</option><option value="bank_transfer">Bank transfer</option><option value="cheque">Cheque</option><option value="other">Other</option></select></label>
        <label>Payment date *<input required type="date" value={paymentDate} onChange={(e) => setPaymentDate(e.target.value)}/></label>
        <label>Transaction reference<input maxLength={120} value={transactionReference} onChange={(e) => setTransactionReference(e.target.value)}/></label>
        <label>Receipt / evidence<input type="file" accept="image/jpeg,image/png,application/pdf" onChange={(e) => setEvidence(e.target.files?.[0] || null)}/><small>JPEG, PNG or PDF · up to 10 MB</small></label>
        <label className="reservation-wide">Staff notes<textarea rows={3} maxLength={3000} value={notes} onChange={(e) => setNotes(e.target.value)}/></label>
        {summaryError && <p className="reservation-wide reservation-feedback is-error" role="alert">{summaryError}</p>}
        {formSummary && <div className="reservation-wide payment-form-balance"><strong>{targetType === "import" ? "Import payment summary" : "Balance summary"}</strong>{targetType === "import" ? <><span>Verified payments: {money(formSummary.verified_amount_lkr || 0)}</span><span>Pending verification: {money(formSummary.pending_amount_lkr || 0)}</span><span>No contract price is recorded, so no outstanding balance is calculated.</span></> : <><span>Agreed amount: {money(formSummary.sale_price_lkr ?? formSummary.agreed_price_lkr ?? (Number(formSummary.verified_received_lkr || 0) + Number(formSummary.outstanding_balance_lkr || 0)))}</span><span>Verified received: {money(formSummary.verified_received_lkr || 0)}</span><span>Pending verification: {money(formSummary.pending_verification_lkr || 0)}</span><span>Available balance after pending: {money(Math.max(0, pendingAllowance))}</span>{formSummary.advance_declared_unverified_lkr !== undefined && <span className="payment-declared">Declared advance · unverified: {money(formSummary.advance_declared_unverified_lkr)}</span>}</>}</div>}
        {targetType !== "import" && formSummary && Number(amount) > Math.max(0, pendingAllowance) && Number(amount) > 0 && <p className="reservation-wide payment-field-error">Amount exceeds the remaining balance after pending payments.</p>}
      </div><p className="payment-note">New payments remain pending until an authorized reviewer verifies them. This form does not treat declared advances as confirmed funds.</p>
      <button className="primary-button" disabled={busy || amountInvalid || !reference.trim()}>{busy ? "Recording…" : "Record payment"}</button>
    </form>}
    <div className="payments-filters"><label>Search<input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Payment, sale, reservation, import or customer"/></label><label>Status<select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All statuses</option><option value="pending">Pending</option><option value="verified">Verified</option><option value="rejected">Rejected</option></select></label><label>Method<select value={method} onChange={(e) => setMethod(e.target.value)}><option value="">All methods</option><option value="cash">Cash</option><option value="bank_transfer">Bank transfer</option><option value="cheque">Cheque</option><option value="other">Other</option></select></label><label>From<input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)}/></label><label>To<input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)}/></label><span>{rows.length} records · latest 250</span></div>
    <section className="payment-directory-layout"><div className="reservation-table-wrap payment-table-wrap">{loading ? <p className="public-state">Loading payments…</p> : rows.length === 0 ? <div className="reservation-empty"><h2>No payments found</h2><p>{search || status || method || fromDate || toDate ? "Try adjusting your filters." : "Recorded payment transactions will appear here."}</p></div> : <table className="reservation-table payment-table"><thead><tr><th>Payment reference</th><th>Sale / reservation / import</th><th>Customer</th><th>Amount</th><th>Method</th><th>Date</th><th>Status</th></tr></thead><tbody>{rows.map((p) => <tr key={p.reference} className={selected?.reference === p.reference ? "is-selected" : ""} onClick={() => setSelected(p)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setSelected(p)}><td><strong>{p.reference}</strong></td><td>{p.sale_reference || p.reservation_reference || "—"}</td><td>{p.customer_name || "—"}</td><td>{money(p.amount_lkr)}</td><td>{p.method.replaceAll("_", " ")}</td><td>{p.payment_date}</td><td><span className={`payment-status is-${p.status}`}>{statusTitle(p.status)}</span></td></tr>)}</tbody></table>}</div>
    {selected && <aside className="reservation-detail payment-detail" aria-label="Payment details"><div className="reservation-detail-heading"><div><p className="eyebrow">PAYMENT DETAIL</p><h2>{selected.reference}</h2></div><button className="inventory-secondary" onClick={() => setSelected(null)} aria-label="Close payment details">×</button></div><span className={`payment-status is-${selected.status}`}>{statusTitle(selected.status)}</span><dl><div><dt>Amount</dt><dd>{money(selected.amount_lkr)}</dd></div><div><dt>Sale / reservation / import</dt><dd>{selected.sale_reference || selected.reservation_reference || "—"}</dd></div><div><dt>Customer</dt><dd>{selected.customer_name || "—"}</dd></div><div><dt>Method</dt><dd>{selected.method.replaceAll("_", " ")}</dd></div><div><dt>Transaction reference</dt><dd>{selected.transaction_reference || "—"}</dd></div><div><dt>Payment date</dt><dd>{selected.payment_date}</dd></div><div><dt>Recorded by</dt><dd>{selected.recorded_by_name}<small>{slTime(selected.created_at)}</small></dd></div>{selected.verified_at && <div><dt>Verified by</dt><dd>{selected.verified_by_name || "—"}<small>{slTime(selected.verified_at)}</small></dd></div>}{selected.rejected_at && <div><dt>Rejected by</dt><dd>{selected.rejected_by_name || "—"}<small>{slTime(selected.rejected_at)}</small></dd></div>}</dl>{selected.notes && <section><h4>Staff notes</h4><p>{selected.notes}</p></section>}{selected.rejection_reason && <section><h4>Rejection reason</h4><p>{selected.rejection_reason}</p></section>}{selected.evidence_attached && selected.evidence_url ? <a className="inventory-secondary" href={`${API}${selected.evidence_url}`} target="_blank" rel="noreferrer">Review private evidence</a> : <p className="payment-note">No evidence attached.</p>}
      {canReview && selected.status === "pending" && <div className="payment-review-actions">{selected.recorded_by_name === user?.username ? <p className="payment-note">You cannot verify a payment you recorded.</p> : <button className="primary-button" disabled={busy} onClick={() => { if (window.confirm(`Verify ${selected.reference} for ${money(selected.amount_lkr)}?`)) void review("verify"); }}>Verify payment</button>}<label>Rejection reason *<textarea rows={3} maxLength={1000} value={rejectReason} onChange={(e) => setRejectReason(e.target.value)}/></label><button className="inventory-danger" disabled={busy || !rejectReason.trim()} onClick={() => void review("reject")}>{busy ? "Saving…" : "Reject payment"}</button></div>}
    </aside>}</section>
  </div>;
}
