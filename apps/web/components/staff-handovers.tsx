"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, API, User } from "@/lib/car-api";

type Checklist = Record<string, boolean>;
type FinancialSummary = { sale_price_lkr: string; verified_received_lkr: string; pending_verification_lkr: string; outstanding_balance_lkr: string; balance_review_required: boolean; required_down_payment_lkr: string; down_payment_verified_lkr: string; down_payment_remaining_lkr: string; down_payment_satisfied: boolean };
type DocumentReceipt = { reference: string; issued_at: string; issued_by_name: string; items_handed_over: { key: string; label: string }[]; download_url: string };
type EligibleSale = { reference: string; vehicle_reference: string; vehicle_name: string; customer_name: string; agreed_price_lkr: string };
type Handover = { id: number; reference: string; sale_reference: string; customer_name: string; vehicle_reference: string; vehicle_name: string; status: "preparing" | "ready_for_review" | "finalized"; delivery_date: string | null; vehicle_condition_checklist: Checklist; keys_documents_checklist: Checklist; customer_acknowledgement: string; customer_acknowledged_at: string | null; evidence_attached: boolean; evidence_url: string | null; document_receipt: DocumentReceipt | null; internal_notes: string; prepared_by_name: string; created_at: string; updated_at: string; finalized_by_name: string | null; finalized_at: string | null; financial_summary: FinancialSummary; commission_eligible: boolean };
type FormState = { sale_reference: string; delivery_date: string; vehicle_condition_checklist: Checklist; keys_documents_checklist: Checklist; customer_acknowledgement: string; internal_notes: string; supporting_evidence: File | null };
const conditionLabels: Record<string, string> = { bodywork: "Bodywork", interior: "Interior", tyres: "Tyres", lights: "Lights", odometer: "Odometer" };
const documentLabels: Record<string, string> = { keys: "Keys", registration_documents: "Registration documents", insurance_documents: "Insurance documents", service_documents: "Service documents" };
const emptyForm = (): FormState => ({ sale_reference: "", delivery_date: "", vehicle_condition_checklist: {}, keys_documents_checklist: {}, customer_acknowledgement: "", internal_notes: "", supporting_evidence: null });
const money = (value?: string | number) => new Intl.NumberFormat("en-LK", { style: "currency", currency: "LKR", maximumFractionDigits: 2 }).format(Number(value || 0));
const dateTime = (value: string | null) => value ? new Intl.DateTimeFormat("en-LK", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Colombo" }).format(new Date(value)) + " SLST" : "—";
const label = (status: string) => status.replaceAll("_", " ");

export default function StaffHandovers() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [items, setItems] = useState<Handover[]>([]);
  const [eligibleSales, setEligibleSales] = useState<EligibleSale[]>([]);
  const [saleSearch, setSaleSearch] = useState("");
  const [selected, setSelected] = useState<Handover | null>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [form, setForm] = useState<FormState>(emptyForm());
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const canCreate = user?.role === "staff" || user?.role === "manager";
  const canEdit = user?.role === "staff" || user?.role === "manager";
  const canFinalize = user?.role === "manager" || user?.role === "ceo";

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const params = new URLSearchParams();
      if (query.trim()) params.set("search", query.trim());
      if (statusFilter) params.set("status", statusFilter);
      const rows = await api<Handover[]>(`/api/staff/handovers/?${params}`);
      setItems(rows);
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to load handovers."); }
    finally { setLoading(false); }
  }, [query, statusFilter]);

  useEffect(() => {
    api<User>("/api/auth/me/").then((current) => {
      if (!["staff", "manager", "ceo"].includes(current.role)) throw new Error("Your account cannot access handovers.");
      setUser(current);
    }).catch(() => router.replace("/staff/login"));
  }, [router]);
  useEffect(() => { if (user) void load(); }, [user, load]);
  useEffect(() => {
    if (!editing || selected || !canCreate) return;
    const params = new URLSearchParams();
    if (saleSearch.trim()) params.set("search", saleSearch.trim());
    api<EligibleSale[]>(`/api/staff/handovers/eligible-sales/?${params}`).then(setEligibleSales)
      .catch((e) => setError(e instanceof Error ? e.message : "Eligible sales could not be loaded."));
  }, [editing, selected, canCreate, saleSearch]);
  useEffect(() => {
    const saleRef = new URLSearchParams(window.location.search).get("sale_reference");
    if (saleRef && canCreate) { setForm((current) => ({ ...current, sale_reference: saleRef })); setSaleSearch(saleRef); setEditing(true); }
  }, [canCreate]);

  const beginCreate = () => { setSelected(null); setForm(emptyForm()); setSaleSearch(""); setEditing(true); setError(""); setNotice(""); };
  const beginEdit = () => {
    if (!selected) return;
    setForm({ sale_reference: selected.sale_reference, delivery_date: selected.delivery_date || "", vehicle_condition_checklist: selected.vehicle_condition_checklist || {}, keys_documents_checklist: selected.keys_documents_checklist || {}, customer_acknowledgement: selected.customer_acknowledgement || "", internal_notes: selected.internal_notes || "", supporting_evidence: null });
    setEditing(true); setError("");
  };
  const updateCheck = (group: "vehicle_condition_checklist" | "keys_documents_checklist", key: string, checked: boolean) => setForm((current) => ({ ...current, [group]: { ...current[group], [key]: checked } }));
  async function save(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      const body = { ...(editing && selected ? {} : { sale_reference: form.sale_reference.trim() }), delivery_date: form.delivery_date || null, vehicle_condition_checklist: form.vehicle_condition_checklist, keys_documents_checklist: form.keys_documents_checklist, customer_acknowledgement: form.customer_acknowledgement, internal_notes: form.internal_notes };
      let result = await api<Handover>(editing && selected ? `/api/staff/handovers/${encodeURIComponent(selected.reference)}/` : "/api/staff/handovers/", { method: editing && selected ? "PATCH" : "POST", body: JSON.stringify(body) });
      if (form.supporting_evidence) {
        const evidence = new FormData(); evidence.set("supporting_evidence", form.supporting_evidence);
        result = await api<Handover>(`/api/staff/handovers/${encodeURIComponent(result.reference)}/`, { method: "PATCH", body: evidence });
      }
      setSelected(result); setEditing(false); setNotice(`${result.reference} saved.`); await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Handover could not be saved."); }
    finally { setBusy(false); }
  }
  async function submitReview() {
    if (!selected) return;
    setBusy(true); setError(""); setNotice("");
    try { const result = await api<Handover>(`/api/staff/handovers/${encodeURIComponent(selected.reference)}/submit/`, { method: "POST", body: "{}" }); setSelected(result); setNotice("Handover submitted for MD review."); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to submit for review."); }
    finally { setBusy(false); }
  }
  async function finalize() {
    if (!selected) return;
    setBusy(true); setError(""); setNotice("");
    try { const result = await api<Handover>(`/api/staff/handovers/${encodeURIComponent(selected.reference)}/finalize/`, { method: "POST", body: "{}" }); setSelected(result); setConfirm(false); setNotice(`${result.reference} finalized. Vehicle status is now Handed Over.`); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "Handover could not be finalized."); }
    finally { setBusy(false); }
  }
  async function issueDocumentReceipt() {
    if (!selected || selected.status !== "finalized" || !canEdit) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const receipt = await api<DocumentReceipt>(`/api/staff/handovers/${encodeURIComponent(selected.reference)}/document-receipt/`, { method: "POST", body: "{}" });
      const fresh = await api<Handover>(`/api/staff/handovers/${encodeURIComponent(selected.reference)}/`);
      setSelected(fresh); setNotice(`Document acknowledgment ${receipt.reference} issued. It does not confirm payment.`);
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Document acknowledgment could not be issued."); }
    finally { setBusy(false); }
  }
  async function downloadDocumentReceipt() {
    if (!selected?.document_receipt) return;
    try {
      const response = await fetch(`${API}${selected.document_receipt.download_url}`, { credentials: "include" });
      if (!response.ok) throw new Error(`Document acknowledgment could not be downloaded (HTTP ${response.status}).`);
      const blob = await response.blob(); const url = URL.createObjectURL(blob); const anchor = document.createElement("a");
      anchor.href = url; anchor.download = `${selected.document_receipt.reference}.pdf`; document.body.appendChild(anchor); anchor.click(); anchor.remove();
      // Let the browser finish consuming the blob before releasing its URL.
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      setNotice(`Acknowledgment ${selected.document_receipt.reference} download started.`);
    } catch (e) { setError(e instanceof Error ? e.message : "Document acknowledgment could not be downloaded."); }
  }
  async function openEvidence() {
    if (!selected?.evidence_url) return;
    try {
      const response = await fetch(`${API}${selected.evidence_url}`, { credentials: "include" });
      if (!response.ok) throw new Error(`Evidence could not be opened (${response.status}).`);
      const blob = await response.blob(); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `handover-evidence-${selected.reference}`; anchor.click(); URL.revokeObjectURL(url);
    } catch (e) { setError(e instanceof Error ? e.message : "Evidence could not be opened."); }
  }

  const counts = { total: items.length, preparing: items.filter((item) => item.status === "preparing").length, review: items.filter((item) => item.status === "ready_for_review").length, finalized: items.filter((item) => item.status === "finalized").length };
  const checksComplete = (selected ? Object.values(conditionLabels).length === Object.keys(conditionLabels).length && Object.keys(conditionLabels).every((key) => selected.vehicle_condition_checklist?.[key] === true) && Object.keys(documentLabels).every((key) => selected.keys_documents_checklist?.[key] === true) : false);

  return <main className="handover-page">
    <header className="handover-page-heading"><div><p className="eyebrow">VEHICLE DELIVERY OPERATIONS</p><h2>Handover directory</h2><p>Prepare delivery records, review required documents and finalize authorized handovers.</p></div>{canCreate && <button className="primary-button" onClick={beginCreate}>+ Prepare handover</button>}</header>
    <section className="reservation-stats handover-stats" aria-label="Handover counts"><article><span>All handovers</span><strong>{counts.total}</strong></article><article><span>Preparing</span><strong>{counts.preparing}</strong></article><article><span>Ready for review</span><strong>{counts.review}</strong></article><article><span>Finalized</span><strong>{counts.finalized}</strong></article></section>
    {error && <p className="reservation-feedback is-error" role="alert">{error}</p>}{notice && <p className="reservation-feedback" role="status">{notice}</p>}
    {editing && canCreate && <form className="reservation-form handover-form" onSubmit={save}>
      <div className="reservation-form-heading"><div><p className="eyebrow">{selected ? "PREPARATION RECORD" : "NEW HANDOVER"}</p><h3>{selected ? `Edit ${selected.reference}` : "Prepare a confirmed sale"}</h3></div><button type="button" className="inventory-secondary" onClick={() => setEditing(false)}>Cancel</button></div>
      {!selected && <div className="reservation-form-grid"><label>Search confirmed sales<input type="search" autoComplete="off" value={saleSearch} onChange={(e) => setSaleSearch(e.target.value)} placeholder="Sale, vehicle, or customer"/><select required value={form.sale_reference} onChange={(e) => setForm({ ...form, sale_reference: e.target.value })}><option value="">Select an eligible sale</option>{eligibleSales.map((sale) => <option key={sale.reference} value={sale.reference}>{sale.reference} · {sale.vehicle_name} · {sale.customer_name} · {money(sale.agreed_price_lkr)}</option>)}</select><small>Only confirmed, sold vehicles without an existing handover are listed. Contact details and representative records are not included.</small></label></div>}
      <div className="reservation-form-grid">
        <label>Delivery date *<input type="date" required value={form.delivery_date} onChange={(e) => setForm({ ...form, delivery_date: e.target.value })}/></label>
        <label>Customer acknowledgement *<textarea required maxLength={2000} rows={3} value={form.customer_acknowledgement} onChange={(e) => setForm({ ...form, customer_acknowledgement: e.target.value })} placeholder="Record the customer's acknowledgement"/></label>
        <fieldset className="handover-checklist"><legend>Vehicle condition *</legend>{Object.entries(conditionLabels).map(([key, text]) => <label key={key}><input type="checkbox" checked={form.vehicle_condition_checklist[key] === true} onChange={(e) => updateCheck("vehicle_condition_checklist", key, e.target.checked)}/>{text}</label>)}</fieldset>
        <fieldset className="handover-checklist"><legend>Keys and documents *</legend>{Object.entries(documentLabels).map(([key, text]) => <label key={key}><input type="checkbox" checked={form.keys_documents_checklist[key] === true} onChange={(e) => updateCheck("keys_documents_checklist", key, e.target.checked)}/>{text}</label>)}</fieldset>
        <label>Private supporting evidence<input type="file" accept="image/jpeg,image/png,application/pdf" onChange={(e) => setForm({ ...form, supporting_evidence: e.target.files?.[0] || null })}/><small>Evidence is stored privately and available only to authorized staff.</small></label>
        <label>Internal notes / balance arrangement<textarea rows={3} maxLength={5000} value={form.internal_notes} onChange={(e) => setForm({ ...form, internal_notes: e.target.value })}/><small>Internal only. If a balance remains, record the manager-approved payment arrangement here. Notes do not count as payment.</small></label>
      </div>
      <button className="primary-button" disabled={busy || !form.sale_reference.trim() && !selected}>{busy ? "Saving…" : "Save preparation"}</button>
    </form>}
    <div className="reservation-toolbar handover-toolbar"><label>Search<input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Handover, sale, vehicle or customer"/></label><label>Status<select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}><option value="">All statuses</option><option value="preparing">Preparing</option><option value="ready_for_review">Ready for review</option><option value="finalized">Finalized</option></select></label><span>{items.length} records</span></div>
    <section className="reservation-workspace handover-workspace"><div className="reservation-table-wrap">{loading ? <p className="public-state">Loading handovers…</p> : items.length === 0 ? <div className="reservation-empty"><h3>No handovers found</h3><p>{query || statusFilter ? "Try another search or filter." : "Confirmed sale handovers will appear here."}</p>{canCreate && !query && !statusFilter && <button className="primary-button" onClick={beginCreate}>Prepare first handover</button>}</div> : <table className="reservation-table handover-table"><thead><tr><th>Reference</th><th>Vehicle</th><th>Customer</th><th>Sale</th><th>Delivery date</th><th>Status</th><th>Prepared by</th><th>Finalized</th></tr></thead><tbody>{items.map((item) => <tr key={item.reference} className={selected?.reference === item.reference ? "is-selected" : ""} onClick={() => { setSelected(item); setEditing(false); }} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setSelected(item)}><td><strong>{item.reference}</strong></td><td>{item.vehicle_name}<small>{item.vehicle_reference}</small></td><td>{item.customer_name}</td><td>{item.sale_reference}</td><td>{item.delivery_date || "—"}</td><td><span className={`reservation-status is-${item.status}`}>{label(item.status)}</span></td><td>{item.prepared_by_name}</td><td>{item.finalized_at ? dateTime(item.finalized_at) : "—"}</td></tr>)}</tbody></table>}</div>
      {selected && <aside className="reservation-detail handover-detail"><div className="reservation-detail-heading"><div><p className="eyebrow">HANDOVER DETAIL</p><h3>{selected.reference}</h3></div><button className="inventory-secondary" aria-label="Close detail" onClick={() => { setSelected(null); setEditing(false); }}>×</button></div>
        <span className={`reservation-status is-${selected.status}`}>{label(selected.status)}</span><h4>{selected.vehicle_name}</h4><p>{selected.vehicle_reference} · Sale {selected.sale_reference}</p>
        <dl><div><dt>Customer</dt><dd>{selected.customer_name}</dd></div><div><dt>Agreed sale price</dt><dd>{money(selected.financial_summary.sale_price_lkr)}</dd></div><div><dt>Delivery date</dt><dd>{selected.delivery_date || "Not set"}</dd></div><div><dt>Prepared by</dt><dd>{selected.prepared_by_name} · {dateTime(selected.created_at)}</dd></div><div><dt>Last updated</dt><dd>{dateTime(selected.updated_at)}</dd></div>{selected.finalized_at && <><div><dt>Finalized by</dt><dd>{selected.finalized_by_name}</dd></div><div><dt>Finalized at</dt><dd>{dateTime(selected.finalized_at)}</dd></div></>}</dl>
        <section className="handover-review-section"><h4>Vehicle condition</h4><ul>{Object.entries(conditionLabels).map(([key, text]) => <li key={key} className={selected.vehicle_condition_checklist?.[key] ? "is-done" : "is-missing"}>{text}<strong>{selected.vehicle_condition_checklist?.[key] ? "Complete" : "Incomplete"}</strong></li>)}</ul><h4>Keys and documents</h4><ul>{Object.entries(documentLabels).map(([key, text]) => <li key={key} className={selected.keys_documents_checklist?.[key] ? "is-done" : "is-missing"}>{text}<strong>{selected.keys_documents_checklist?.[key] ? "Complete" : "Incomplete"}</strong></li>)}</ul>
          <p className={`handover-acknowledgement ${selected.customer_acknowledgement ? "is-done" : "is-missing"}`}><strong>Customer acknowledgement</strong><span>{selected.customer_acknowledgement || "Not recorded"}</span>{selected.customer_acknowledged_at && <small>{dateTime(selected.customer_acknowledged_at)}</small>}</p>
          {selected.evidence_attached && <button className="inventory-secondary" onClick={() => void openEvidence()}>Download private evidence</button>}
          {selected.internal_notes && <p className="handover-internal-notes"><strong>Internal notes</strong><span>{selected.internal_notes}</span></p>}
        </section>
        <section className={`handover-financial-review ${selected.financial_summary.balance_review_required ? "has-balance" : ""}`}><h4>Payment review</h4><dl>{Number(selected.financial_summary.required_down_payment_lkr) > 0 && <><div><dt>Required reservation down payment</dt><dd>{money(selected.financial_summary.required_down_payment_lkr)}</dd></div><div><dt>Verified toward down payment</dt><dd>{money(selected.financial_summary.down_payment_verified_lkr)}</dd></div></>}<div><dt>Verified payments</dt><dd>{money(selected.financial_summary.verified_received_lkr)}</dd></div><div><dt>Pending verification</dt><dd>{money(selected.financial_summary.pending_verification_lkr)}</dd></div><div><dt>Outstanding balance</dt><dd>{money(selected.financial_summary.outstanding_balance_lkr)}</dd></div></dl>{selected.financial_summary.balance_review_required && <p>The outstanding balance remains due and unpaid after handover. Record finance settlement only after funds are received and follow the existing verification process.</p>}{canEdit && <Link className="inventory-secondary" href={`/staff/payments?target_type=sale&reference=${encodeURIComponent(selected.sale_reference)}`}>Record payment against this sale</Link>}</section>
        <section className="handover-document-receipt"><h4>Customer document acknowledgment</h4><p>This receipt records delivery of the listed company/vehicle items only; it is not proof of payment.</p>{selected.document_receipt ? <><p role="status">{selected.document_receipt.reference} issued by {selected.document_receipt.issued_by_name} · {dateTime(selected.document_receipt.issued_at)}</p><p>Items: {selected.document_receipt.items_handed_over.map((item) => item.label).join(", ")}</p><button className="primary-button" disabled={busy} onClick={() => void downloadDocumentReceipt()}>Download / print acknowledgment PDF</button></> : canEdit && selected.status === "finalized" && <button className="primary-button" disabled={busy} onClick={() => void issueDocumentReceipt()}>{busy ? "Issuing…" : "Issue document acknowledgment"}</button>}</section>
        {canEdit && selected.status !== "finalized" && <div className="handover-actions"><button className="inventory-secondary" onClick={beginEdit}>Edit preparation</button>{selected.status === "preparing" && <button className="primary-button" disabled={busy} onClick={() => void submitReview()}>{busy ? "Submitting…" : "Submit for MD review"}</button>}</div>}
        {canFinalize && selected.status === "ready_for_review" && <div className="handover-actions"><button className="primary-button" onClick={() => setConfirm(true)}>Review and finalize</button></div>}
        {selected.status === "finalized" && <p className="handover-finalized-note">Finalized handovers are locked. Commission eligibility begins only after this finalized state; no commission is calculated here.</p>}
        {user?.role === "ceo" && <p className="reservation-hint">CEO review can finalize a complete handover. Preparation and submission remain with Staff and MD/Manager.</p>}
      </aside>}
    </section>
    {confirm && selected && <div className="reservation-dialog-backdrop" role="presentation"><section className="reservation-dialog handover-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="handover-confirm-title"><p className="eyebrow">MD FINAL REVIEW</p><h3 id="handover-confirm-title">Finalize {selected.reference}?</h3><p>This permanently records delivery of <strong>{selected.vehicle_name}</strong> to <strong>{selected.customer_name}</strong> and changes the vehicle status to Handed Over.</p><ul>{Object.entries(conditionLabels).map(([key, text]) => <li key={key}>{text}: {selected.vehicle_condition_checklist?.[key] ? "Complete" : "Incomplete"}</li>)}{Object.entries(documentLabels).map(([key, text]) => <li key={key}>{text}: {selected.keys_documents_checklist?.[key] ? "Complete" : "Incomplete"}</li>)}</ul><dl><div><dt>Verified payments</dt><dd>{money(selected.financial_summary.verified_received_lkr)}</dd></div><div><dt>Outstanding balance</dt><dd>{money(selected.financial_summary.outstanding_balance_lkr)}</dd></div></dl>{selected.financial_summary.balance_review_required && <p className="handover-balance-warning">The outstanding finance balance remains due after the authorized release; handover does not record it as paid.</p>}<p>Only finalize if delivery and customer acknowledgement have been reviewed. This action is permanent.</p><footer><button className="inventory-secondary" disabled={busy} onClick={() => setConfirm(false)}>Cancel</button><button className="primary-button" disabled={busy || !checksComplete || !selected.customer_acknowledgement || !selected.delivery_date || !selected.financial_summary.down_payment_satisfied} onClick={() => void finalize()}>{busy ? "Finalizing…" : "Confirm handover finalization"}</button></footer></section></div>}
  </main>;
}
