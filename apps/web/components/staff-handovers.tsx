"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, API, User } from "@/lib/car-api";

type Checklist = Record<string, boolean>;
type FinancialSummary = { sale_price_lkr: string; verified_received_lkr: string; pending_verification_lkr: string; outstanding_balance_lkr: string; balance_review_required: boolean; required_down_payment_lkr: string; down_payment_verified_lkr: string; down_payment_remaining_lkr: string; down_payment_satisfied: boolean };
type DocumentReceipt = { reference: string; issued_at: string; issued_by_name: string; items_handed_over: { key: string; label: string }[]; download_url: string };
type EligibleSale = { reference: string; vehicle_reference: string; vehicle_name: string; customer_name: string; agreed_price_lkr: string };
type HandoverStatus = "preparing" | "pending_md_review" | "pending_ceo_approval" | "ceo_approved" | "finalized";
type Approval = { reviewer_name: string; reviewer_role: string; decision: string; status_before: string; status_after: string; comments: string; created_at: string };
type CompletionEmail = {
  status: "no_email" | "queued" | "sending" | "sent" | "failed";
  sent_at: string | null;
  error: string;
};

type Handover = { completion_email?: CompletionEmail | null; id: number; reference: string; sale_reference: string; customer_name: string; vehicle_reference: string; vehicle_name: string; status: HandoverStatus; delivery_date: string | null; vehicle_condition_checklist: Checklist; keys_documents_checklist: Checklist; customer_acknowledgement: string; customer_acknowledged_at: string | null; evidence_attached: boolean; evidence_url: string | null; document_receipt: DocumentReceipt | null; internal_notes: string; prepared_by_name: string; created_at: string; updated_at: string; md_approved_by_name: string | null; md_approved_at: string | null; ceo_approved_by_name: string | null; ceo_approved_at: string | null; approval_history: Approval[]; finalized_by_name: string | null; finalized_at: string | null; financial_summary: FinancialSummary; commission_eligible: boolean };
type FormState = { sale_reference: string; delivery_date: string; vehicle_condition_checklist: Checklist; keys_documents_checklist: Checklist; customer_acknowledgement: string; internal_notes: string; supporting_evidence: File | null };
const conditionLabels: Record<string, string> = { bodywork: "Bodywork", interior: "Interior", tyres: "Tyres", lights: "Lights", odometer: "Odometer" };
const documentLabels: Record<string, string> = { keys: "Keys", registration_documents: "Registration documents", insurance_documents: "Insurance documents", service_documents: "Service documents" };
const emptyForm = (): FormState => ({ sale_reference: "", delivery_date: "", vehicle_condition_checklist: {}, keys_documents_checklist: {}, customer_acknowledgement: "", internal_notes: "", supporting_evidence: null });
const money = (value?: string | number) => new Intl.NumberFormat("en-LK", { style: "currency", currency: "LKR", maximumFractionDigits: 2 }).format(Number(value || 0));
const dateTime = (value: string | null) => value ? new Intl.DateTimeFormat("en-LK", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Colombo" }).format(new Date(value)) + " SLST" : "—";
const label = (status: string) => status.split("_").map((word) => word.toUpperCase() === "MD" || word.toUpperCase() === "CEO" ? word.toUpperCase() : word[0]?.toUpperCase() + word.slice(1)).join(" ");

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
  const evidenceInput = useRef<HTMLInputElement>(null);
  const [evidenceError, setEvidenceError] = useState("");
  const [returnDialog, setReturnDialog] = useState(false);
  const [returnReason, setReturnReason] = useState("");

  const preparationFormRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    if (editing && preparationFormRef.current) {
      preparationFormRef.current.focus({ preventScroll: true });
      preparationFormRef.current.scrollIntoView({
        behavior: "auto",
        block: "start"
      });
    }
  }, [editing]);

  const canCreate = user?.role === "staff";
  const canEdit = user?.role === "staff";
  const canManagePayments = user?.role === "ceo" || user?.role === "manager";
  const canIssueDocumentReceipt = user?.role === "staff" || user?.role === "manager";
  const canApproveMD = user?.role === "manager";
  const canApproveCEO = user?.role === "ceo";
  const canFinalize = user?.role === "manager";

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
    e.preventDefault(); if (busy) return; setBusy(true); setError(""); setNotice("");
    try {
      const body = { ...(editing && selected ? {} : { sale_reference: form.sale_reference.trim() }), delivery_date: form.delivery_date || null, vehicle_condition_checklist: form.vehicle_condition_checklist, keys_documents_checklist: form.keys_documents_checklist, customer_acknowledgement: form.customer_acknowledgement, internal_notes: form.internal_notes };
      let result = await api<Handover>(editing && selected ? `/api/staff/handovers/${encodeURIComponent(selected.reference)}/` : "/api/staff/handovers/", { method: editing && selected ? "PATCH" : "POST", body: JSON.stringify(body) });
      // Retain the created record before uploading optional evidence so a failed upload can be retried as an edit.
      setSelected(result);
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
  async function approveMD() {
    if (!selected || busy) return;
    setBusy(true); setError(""); setNotice("");
    try { const result = await api<Handover>(`/api/staff/handovers/${encodeURIComponent(selected.reference)}/approve-md/`, { method: "POST", body: "{}" }); setSelected(result); setNotice("MD review approved and submitted to the CEO."); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "MD review could not be completed."); }
    finally { setBusy(false); }
  }
  async function approveCEO() {
    if (!selected || busy) return;
    setBusy(true); setError(""); setNotice("");
    try { const result = await api<Handover>(`/api/staff/handovers/${encodeURIComponent(selected.reference)}/approve-ceo/`, { method: "POST", body: "{}" }); setSelected(result); setNotice("CEO approval recorded. The MD can finalize after delivery checks."); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "CEO approval could not be completed."); }
    finally { setBusy(false); }
  }
  async function returnForCorrection() {
    if (!selected || busy || !returnReason.trim()) return;
    setBusy(true); setError(""); setNotice("");
    try { const result = await api<Handover>(`/api/staff/handovers/${encodeURIComponent(selected.reference)}/return/`, { method: "POST", body: JSON.stringify({ comments: returnReason.trim() }) }); setSelected(result); setReturnDialog(false); setReturnReason(""); setNotice(result.status === "preparing" ? "Handover returned to Staff for correction." : "Handover returned to MD review."); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "Handover could not be returned."); }
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
    if (!selected || selected.status !== "finalized" || !canIssueDocumentReceipt) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const receipt = await api<DocumentReceipt>(`/api/staff/handovers/${encodeURIComponent(selected.reference)}/document-receipt/`, { method: "POST", body: "{}" });
      const fresh = await api<Handover>(`/api/staff/handovers/${encodeURIComponent(selected.reference)}/`);
      setSelected(fresh); setNotice(`Document acknowledgment ${receipt.reference} issued. It does not confirm payment.`);
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Document acknowledgment could not be issued."); }
    finally { setBusy(false); }
  }
  async function refreshCompletionEmail(retry = false) {
    if (!selected || busy || selected.status !== "finalized") return;

    const reference = selected.reference;
    const emailStatus = selected.completion_email?.status;
    const canRetry = user?.role === "manager" || user?.role === "ceo";

    if (retry) {
      if (!canRetry || !emailStatus ||
          !["failed", "no_email", "queued"].includes(emailStatus)) {
        return;
      }

      if (emailStatus === "failed" && !window.confirm(
        "Have you verified with the mail provider that the previous email was NOT accepted? Only continue if confirmed."
      )) {
        return;
      }
    }

    setBusy(true);
    setError("");
    setNotice("");

    try {
      const base = `/api/staff/handovers/${encodeURIComponent(reference)}/`;

      const result = retry
        ? await api<Handover>(`${base}retry-email/`, {
            method: "POST",
            body: JSON.stringify({
              confirmed_not_accepted: emailStatus === "failed"
            })
          })
        : await api<Handover>(base);

      setSelected(current =>
        current?.reference === reference ? result : current
      );

      setItems(current =>
        current.map(item =>
          item.reference === reference ? result : item
        )
      );

      setNotice(retry
        ? "Email retry processed. Check the updated delivery status."
        : "Email delivery status refreshed.");

    } catch (e) {
      setError(e instanceof Error
        ? e.message
        : "Unable to update email delivery status.");
    } finally {
      setBusy(false);
    }
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

  const counts = { total: items.length, preparing: items.filter((item) => item.status === "preparing").length, review: items.filter((item) => item.status === "pending_md_review" || item.status === "pending_ceo_approval" || item.status === "ceo_approved").length, finalized: items.filter((item) => item.status === "finalized").length };
  const checksComplete = (selected ? Object.values(conditionLabels).length === Object.keys(conditionLabels).length && Object.keys(conditionLabels).every((key) => selected.vehicle_condition_checklist?.[key] === true) && Object.keys(documentLabels).every((key) => selected.keys_documents_checklist?.[key] === true) : false);
  const preparationComplete = Boolean(
    selected &&
    checksComplete &&
    selected.delivery_date &&
    selected.customer_acknowledgement?.trim() &&
    selected.customer_acknowledged_at
  );

  const workflowSteps = ["Preparation", "MD Review", "CEO Approval", "Finalized"];
  const workflowIndex = selected ? ({ preparing: 0, pending_md_review: 1, pending_ceo_approval: 2, ceo_approved: 3, finalized: 3 } as Record<HandoverStatus, number>)[selected.status] : 0;
  const workflowRole = selected ? ({ preparing: "Staff", pending_md_review: "MD/Manager", pending_ceo_approval: "CEO", ceo_approved: "MD/Manager — delivery finalization", finalized: "Complete" } as Record<HandoverStatus, string>)[selected.status] : "Staff";
  const outstandingRequirements = selected ? [
    ...Object.entries(conditionLabels).filter(([key]) => selected.vehicle_condition_checklist?.[key] !== true).map(([, text]) => `${text} condition check`),
    ...Object.entries(documentLabels).filter(([key]) => selected.keys_documents_checklist?.[key] !== true).map(([, text]) => `${text} confirmation`),
    ...(!selected.delivery_date ? ["Delivery date"] : []),
    ...(!selected.customer_acknowledgement?.trim() || !selected.customer_acknowledged_at ? ["Recorded customer acknowledgement"] : []),
    ...(!selected.financial_summary.down_payment_satisfied ? ["Verified required reservation down payment"] : []),
  ] : [];
  const chooseEvidence = (file?: File) => {
    setEvidenceError("");
    if (!file) return;
    if (!["image/jpeg", "image/png", "application/pdf"].includes(file.type) || file.size > 10 * 1024 * 1024) {
      setEvidenceError("Choose a JPEG, PNG or PDF file up to 10 MB.");
      if (evidenceInput.current) evidenceInput.current.value = "";
      return;
    }
    setForm((current) => ({ ...current, supporting_evidence: file }));
  };

  return <main className="handover-page">
    <header className="handover-page-heading"><div><p className="eyebrow">VEHICLE DELIVERY OPERATIONS</p><h2>Handover directory</h2><p>Prepare delivery records, review required documents and finalize authorized handovers.</p></div>{canCreate && <button className="primary-button handover-prepare-button" onClick={beginCreate}><span aria-hidden="true">＋</span> Prepare handover</button>}</header>
    <section className="reservation-stats handover-stats" aria-label="Handover counts">
      <article className="is-active"><span className="handover-stat-icon" aria-hidden="true">▱</span><div><span>All handovers</span><strong>{counts.total}</strong></div></article>
      <article><span className="handover-stat-icon" aria-hidden="true">▤</span><div><span>Preparing</span><strong>{counts.preparing}</strong></div></article>
      <article><span className="handover-stat-icon" aria-hidden="true">⌕</span><div><span>Ready for review</span><strong>{counts.review}</strong></div></article>
      <article><span className="handover-stat-icon" aria-hidden="true">✓</span><div><span>Finalized</span><strong>{counts.finalized}</strong></div></article>
    </section>
    {error && <p className="reservation-feedback is-error" role="alert">{error}</p>}{notice && <p className="reservation-feedback" role="status">{notice}</p>}
    {editing && canCreate && <form ref={preparationFormRef} tabIndex={-1} className="reservation-form handover-form" onSubmit={save}>
      <div className="reservation-form-heading"><div><p className="eyebrow">{selected ? "PREPARATION RECORD" : "NEW HANDOVER"}</p><h3>{selected ? `Edit ${selected.reference}` : "Prepare a confirmed sale"}</h3></div><button type="button" className="inventory-secondary" onClick={() => setEditing(false)}>Cancel</button></div>
      <div className="handover-form-grid">
        <section className="handover-form-card handover-sale-card"><header><span aria-hidden="true">♧</span><div><h4>Sale &amp; Delivery Information</h4><p>Select the confirmed sale and set the delivery details.</p></div></header><div className="handover-card-body">
          {!selected && <label><span>Search confirmed sales <b>*</b></span><input type="search" autoComplete="off" value={saleSearch} onChange={(e) => setSaleSearch(e.target.value)} placeholder="Sale, vehicle, or customer"/><select required value={form.sale_reference} onChange={(e) => setForm({ ...form, sale_reference: e.target.value })}><option value="">Select an eligible sale</option>{eligibleSales.map((sale) => <option key={sale.reference} value={sale.reference}>{sale.reference} · {sale.vehicle_name} · {sale.customer_name} · {money(sale.agreed_price_lkr)}</option>)}</select><small>Only confirmed, sold vehicles without an existing handover are listed.</small></label>}
          {selected && <div className="handover-selected-sale"><strong>{selected.sale_reference}</strong><span>{selected.vehicle_name}</span><small>{selected.customer_name} · {money(selected.financial_summary.sale_price_lkr)}</small></div>}
          <label><span>Delivery date <b>*</b></span><input type="date" required value={form.delivery_date} onChange={(e) => setForm({ ...form, delivery_date: e.target.value })}/></label>
          <label><span>Customer acknowledgement <b>*</b></span><textarea required maxLength={2000} rows={3} value={form.customer_acknowledgement} onChange={(e) => setForm({ ...form, customer_acknowledgement: e.target.value })} placeholder="Record the customer's acknowledgement"/></label>
        </div></section>
        <section className="handover-form-card"><header><span aria-hidden="true">♢</span><div><h4>Vehicle Condition</h4><p>Confirm the condition of the vehicle before delivery.</p></div></header><div className="handover-checklist handover-card-body">{Object.entries(conditionLabels).map(([key, text]) => <label key={key}><input type="checkbox" checked={form.vehicle_condition_checklist[key] === true} onChange={(e) => updateCheck("vehicle_condition_checklist", key, e.target.checked)}/>{text}</label>)}</div></section>
        <section className="handover-form-card"><header><span aria-hidden="true">▤</span><div><h4>Keys and Documents</h4><p>Ensure all keys and required documents are ready.</p></div></header><div className="handover-checklist handover-card-body">{Object.entries(documentLabels).map(([key, text]) => <label key={key}><input type="checkbox" checked={form.keys_documents_checklist[key] === true} onChange={(e) => updateCheck("keys_documents_checklist", key, e.target.checked)}/>{text}</label>)}</div></section>
        <section className="handover-form-card"><header><span aria-hidden="true">▧</span><div><h4>Private Supporting Evidence</h4><p>Attach evidence for authorized staff.</p></div></header><div className="handover-card-body"><div className="handover-dropzone" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); chooseEvidence(e.dataTransfer.files[0]); }}><span aria-hidden="true">⇧</span><p><button type="button" className="table-link-button" onClick={() => evidenceInput.current?.click()}>Choose files</button> or drag and drop</p><small>JPEG, PNG or PDF · up to 10 MB each</small><input ref={evidenceInput} type="file" accept="image/jpeg,image/png,application/pdf" aria-label="Choose private supporting evidence" onChange={(e) => chooseEvidence(e.target.files?.[0])}/></div>{form.supporting_evidence && <div className="handover-file-selected"><span>{form.supporting_evidence.name}</span><button type="button" className="table-link-button" onClick={() => { setForm((current) => ({ ...current, supporting_evidence: null })); if (evidenceInput.current) evidenceInput.current.value = ""; }}>Clear file</button></div>}{selected?.evidence_attached && !form.supporting_evidence && <small>Private evidence is already attached. Selecting a file will replace it.</small>}{evidenceError && <small className="handover-file-error" role="alert">{evidenceError}</small>}</div></section>
        <section className="handover-form-card"><header><span aria-hidden="true">▧</span><div><h4>Internal Notes / Balance Arrangement</h4><p>Visible to staff only.</p></div></header><div className="handover-card-body"><label className="handover-notes-label"><textarea rows={4} maxLength={5000} value={form.internal_notes} onChange={(e) => setForm({ ...form, internal_notes: e.target.value })} placeholder="Internal only. If a balance remains, record the manager-approved payment arrangement here. Notes do not count as payment."/></label></div></section>
      </div>
      <button className="primary-button handover-save-button" disabled={busy || !form.sale_reference.trim() && !selected}>{busy ? "Saving…" : "▣  Save preparation"}</button>    </form>}
    <div className="reservation-toolbar handover-toolbar"><label>Search<input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Handover, sale, vehicle or customer"/></label><label>Status<select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}><option value="">All statuses</option><option value="preparing">Preparing</option><option value="pending_md_review">Pending MD review</option><option value="pending_ceo_approval">Pending CEO approval</option><option value="ceo_approved">CEO approved</option><option value="finalized">Finalized</option></select></label><span>{items.length} records</span></div>
    <section className="reservation-workspace handover-workspace"><div className="reservation-table-wrap">{loading ? <p className="public-state">Loading handovers…</p> : items.length === 0 ? <div className="reservation-empty"><h3>No handovers found</h3><p>{query || statusFilter ? "Try another search or filter." : "Confirmed sale handovers will appear here."}</p>{canCreate && !query && !statusFilter && <button className="primary-button" onClick={beginCreate}>Prepare first handover</button>}</div> : <table className="reservation-table handover-table"><thead><tr><th>Reference</th><th>Vehicle</th><th>Customer</th><th>Sale</th><th>Delivery date</th><th>Status</th><th>Prepared by</th><th>Finalized</th></tr></thead><tbody>{items.map((item) => <tr key={item.reference} className={selected?.reference === item.reference ? "is-selected" : ""} onClick={() => { setSelected(item); setEditing(false); }} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setSelected(item)}><td><strong>{item.reference}</strong></td><td>{item.vehicle_name}<small>{item.vehicle_reference}</small></td><td>{item.customer_name}</td><td>{item.sale_reference}</td><td>{item.delivery_date || "—"}</td><td><span className={`reservation-status is-${item.status}`}>{label(item.status)}</span></td><td>{item.prepared_by_name}</td><td>{item.finalized_at ? dateTime(item.finalized_at) : "—"}</td></tr>)}</tbody></table>}</div>
      {selected && <aside className="reservation-detail handover-detail"><div className="reservation-detail-heading"><div><p className="eyebrow">HANDOVER DETAIL</p><h3>{selected.reference}</h3></div><button className="inventory-secondary" aria-label="Close detail" onClick={() => { setSelected(null); setEditing(false); }}>×</button></div>
        <span className={`reservation-status is-${selected.status}`}>{label(selected.status)}</span><h4>{selected.vehicle_name}</h4><p>{selected.vehicle_reference} · Sale {selected.sale_reference}</p>
        <dl><div><dt>Customer</dt><dd>{selected.customer_name}</dd></div><div><dt>Agreed sale price</dt><dd>{money(selected.financial_summary.sale_price_lkr)}</dd></div><div><dt>Delivery date</dt><dd>{selected.delivery_date || "Not set"}</dd></div><div><dt>Prepared by</dt><dd>{selected.prepared_by_name} · {dateTime(selected.created_at)}</dd></div><div><dt>Last updated</dt><dd>{dateTime(selected.updated_at)}</dd></div>{selected.finalized_at && <><div><dt>Finalized by</dt><dd>{selected.finalized_by_name}</dd></div><div><dt>Finalized at</dt><dd>{dateTime(selected.finalized_at)}</dd></div></>}</dl>
        <section className="handover-approval-progress" aria-labelledby="handover-progress-title"><h4 id="handover-progress-title">Approval progress</h4><p><strong>Current stage:</strong> {label(selected.status)} · <strong>Reviewing role:</strong> {workflowRole}</p><ol>{workflowSteps.map((step, index) => <li key={step} className={index < workflowIndex || selected.status === "finalized" ? "is-complete" : index === workflowIndex ? "is-current" : ""}><span>{index + 1}</span><strong>{step}</strong></li>)}</ol><dl><div><dt>MD reviewer</dt><dd>{selected.md_approved_by_name ? `${selected.md_approved_by_name}${selected.md_approved_at ? ` · ${dateTime(selected.md_approved_at)}` : ""}` : "Awaiting MD review"}</dd></div><div><dt>CEO reviewer</dt><dd>{selected.ceo_approved_by_name ? `${selected.ceo_approved_by_name}${selected.ceo_approved_at ? ` · ${dateTime(selected.ceo_approved_at)}` : ""}` : "Awaiting CEO approval"}</dd></div><div><dt>Next permitted action</dt><dd>{selected.status === "preparing" ? "Staff submits for MD review" : selected.status === "pending_md_review" ? "MD approves to CEO or returns to Staff" : selected.status === "pending_ceo_approval" ? "CEO approves or returns to MD" : selected.status === "ceo_approved" ? "MD finalizes after delivery verification" : "Handover complete"}</dd></div></dl>{outstandingRequirements.length > 0 && selected.status !== "finalized" && <div className="handover-outstanding"><strong>Outstanding requirements</strong><ul>{outstandingRequirements.map((item) => <li key={item}>{item}</li>)}</ul></div>}</section>
        <section className="handover-approval-history" id="approval-history"><h4>Approval history</h4>{selected.approval_history?.length ? <ol>{selected.approval_history.map((entry, index) => <li key={`${entry.created_at}-${index}`}><div><strong>{label(entry.decision)}</strong><time>{dateTime(entry.created_at)}</time></div><p>{entry.reviewer_name} · {label(entry.reviewer_role)} · {label(entry.status_before)} → {label(entry.status_after)}</p>{entry.comments && <blockquote>{entry.comments}</blockquote>}</li>)}</ol> : <p>No review decisions recorded yet.</p>}</section>
        <section className="handover-review-section"><h4>Vehicle condition</h4><ul>{Object.entries(conditionLabels).map(([key, text]) => <li key={key} className={selected.vehicle_condition_checklist?.[key] ? "is-done" : "is-missing"}>{text}<strong>{selected.vehicle_condition_checklist?.[key] ? "Complete" : "Incomplete"}</strong></li>)}</ul><h4>Keys and documents</h4><ul>{Object.entries(documentLabels).map(([key, text]) => <li key={key} className={selected.keys_documents_checklist?.[key] ? "is-done" : "is-missing"}>{text}<strong>{selected.keys_documents_checklist?.[key] ? "Complete" : "Incomplete"}</strong></li>)}</ul>
          <p className={`handover-acknowledgement ${selected.customer_acknowledgement ? "is-done" : "is-missing"}`}><strong>Customer acknowledgement</strong><span>{selected.customer_acknowledgement || "Not recorded"}</span>{selected.customer_acknowledged_at && <small>{dateTime(selected.customer_acknowledged_at)}</small>}</p>
          {selected.evidence_attached && <button className="inventory-secondary" onClick={() => void openEvidence()}>Download private evidence</button>}
          {selected.internal_notes && (
            <div className="handover-internal-notes">
              <strong>Historical internal notes</strong>
              <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                {selected.internal_notes}
              </p>
              <small>
                Original preparation notes retained for audit purposes.
                Refer to the current payment review for the latest balance.
              </small>
              {Number(selected.financial_summary.outstanding_balance_lkr) === 0 && (
                <p role="status" style={{ color: "#15803d", fontWeight: 600 }}>
                  Current outstanding balance: {money(0)}.
                  No outstanding payment remains.
                </p>
              )}
            </div>
          )}
        </section>
        <section className={`handover-financial-review ${selected.financial_summary.balance_review_required ? "has-balance" : ""}`}><h4>Payment review</h4><dl>{Number(selected.financial_summary.required_down_payment_lkr) > 0 && <><div><dt>Required reservation down payment</dt><dd>{money(selected.financial_summary.required_down_payment_lkr)}</dd></div><div><dt>Verified toward down payment</dt><dd>{money(selected.financial_summary.down_payment_verified_lkr)}</dd></div></>}<div><dt>Verified payments</dt><dd>{money(selected.financial_summary.verified_received_lkr)}</dd></div><div><dt>Legacy pending</dt><dd>{money(selected.financial_summary.pending_verification_lkr)}</dd></div><div><dt>Outstanding balance</dt><dd>{money(selected.financial_summary.outstanding_balance_lkr)}</dd></div></dl>{selected.financial_summary.balance_review_required ? (
            <p>
              {selected.status === "finalized"
                ? "The outstanding balance remains due after handover."
                : "An outstanding balance remains on this sale."}
              {" "}Record settlement only after funds have been received and cleared.
            </p>
          ) : Number(selected.financial_summary.outstanding_balance_lkr) === 0 ? (
            <p role="status" style={{ color: "#15803d", fontWeight: 600 }}>
              Fully settled - no outstanding payment remains.
            </p>
          ) : null}{canManagePayments && <Link className="inventory-secondary" href={`/staff/payments?target_type=sale&reference=${encodeURIComponent(selected.sale_reference)}`}>Record payment against this sale</Link>}</section>
        {selected.status === "finalized" && (
          <section className="handover-document-receipt">
            <h4>Customer handover confirmation email</h4>
            <p>Automatic confirmation of completed vehicle delivery.</p>

            {selected.completion_email ? (
              <>
                <dl>
                  <div>
                    <dt>Delivery status</dt>
                    <dd>
                      <strong>
                        {{
                          no_email: "No valid email address",
                          queued: "Queued",
                          sending: "Sending",
                          sent: "Accepted by mail service",
                          failed: "Sending failed"
                        }[selected.completion_email.status]}
                      </strong>
                    </dd>
                  </div>

                  {selected.completion_email.sent_at && (
                    <div>
                      <dt>Sent at</dt>
                      <dd>{dateTime(selected.completion_email.sent_at)}</dd>
                    </div>
                  )}
                </dl>

                                <div className="handover-actions">
                  <button
                    type="button"
                    className="inventory-secondary"
                    disabled={busy}
                    onClick={() => void refreshCompletionEmail()}
                  >
                    Refresh status
                  </button>

                  {(user?.role === "manager" || user?.role === "ceo") &&
                    ["failed", "no_email", "queued"].includes(
                      selected.completion_email.status
                    ) && (
                      <button
                        type="button"
                        className="primary-button"
                        disabled={busy}
                        onClick={() => void refreshCompletionEmail(true)}
                      >
                        {busy ? "Processing..." : "Retry email"}
                      </button>
                    )}
                </div>

                {selected.completion_email.status === "sent" && (
                  <p role="status">
                    The customer's handover confirmation was accepted
                    by the mail service.
                  </p>
                )}

                {selected.completion_email.error && (
                  <p className="reservation-feedback is-error" role="alert">
                    {selected.completion_email.error}
                  </p>
                )}

                {selected.completion_email.status === "no_email" && (
                  <p>Please verify the customer's email address.</p>
                )}
              </>
            ) : (
              <p>No email delivery record exists for this handover.</p>
            )}
          </section>
        )}

        <section className="handover-document-receipt"><h4>Customer document acknowledgment</h4><p>This receipt records delivery of the listed company/vehicle items only; it is not proof of payment.</p>{selected.document_receipt ? <><p role="status">{selected.document_receipt.reference} issued by {selected.document_receipt.issued_by_name} · {dateTime(selected.document_receipt.issued_at)}</p><p>Items: {selected.document_receipt.items_handed_over.map((item) => item.label).join(", ")}</p><button className="primary-button" disabled={busy} onClick={() => void downloadDocumentReceipt()}>Download / print acknowledgment PDF</button></> : canIssueDocumentReceipt && selected.status === "finalized" && <button className="primary-button" disabled={busy} onClick={() => void issueDocumentReceipt()}>{busy ? "Issuing…" : "Issue document acknowledgment"}</button>}</section>
        {canEdit && selected.status !== "finalized" && <div className="handover-actions">{selected.status === "preparing" ? <><button type="button" className="inventory-secondary" disabled={busy || editing} onClick={beginEdit}>{editing ? "Editing preparation" : "Edit preparation"}</button><button type="button" className="primary-button" disabled={busy || editing || !preparationComplete} onClick={() => void submitReview()}>{busy ? "Submitting…" : "Submit for MD Review"}</button>
{editing ? <p className="reservation-hint">Save your preparation changes before submitting for review.</p> : !preparationComplete && <p className="reservation-hint">Complete and save all required preparation items before submitting for MD review.</p>}</> : <a className="inventory-secondary" href="#approval-history">View Review Status</a>}</div>}
        {canApproveMD && selected.status === "pending_md_review" && <div className="handover-actions"><button className="inventory-secondary" disabled={busy} onClick={() => { setReturnReason(""); setReturnDialog(true); }}>Return to Staff with reason</button><button className="primary-button" disabled={busy || outstandingRequirements.length > 0} onClick={() => void approveMD()}>{busy ? "Submitting…" : "Approve & Submit to CEO"}</button></div>}
        {canApproveCEO && selected.status === "pending_ceo_approval" && <div className="handover-actions"><button className="inventory-secondary" disabled={busy} onClick={() => { setReturnReason(""); setReturnDialog(true); }}>Return to MD with reason</button><button className="primary-button" disabled={busy || outstandingRequirements.length > 0} onClick={() => void approveCEO()}>{busy ? "Approving…" : "Approve Handover"}</button></div>}
        {canFinalize && selected.status === "ceo_approved" && <div className="handover-actions"><button className="inventory-secondary" disabled={busy} onClick={() => { setReturnReason(""); setReturnDialog(true); }}>Return to Staff with reason</button><button className="primary-button" disabled={outstandingRequirements.length > 0} onClick={() => setConfirm(true)}>Finalize Handover</button></div>}

        {selected.status === "finalized" && <p className="handover-finalized-note">Finalized handovers are locked. Commission eligibility begins only after this finalized state; no commission is calculated here.</p>}
        {user?.role === "ceo" && <p className="reservation-hint">CEO approval authorizes delivery but does not finalize the handover or create commission eligibility.</p>}
      </aside>}
    </section>
    {returnDialog && selected && <div className="reservation-dialog-backdrop" role="presentation"><section className="reservation-dialog handover-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="handover-return-title"><p className="eyebrow">REVIEW DECISION</p><h3 id="handover-return-title">Return {selected.reference} for correction?</h3><p>The reason is recorded in the permanent handover approval history and shared with the next responsible role.</p><label>Reason <textarea required autoFocus maxLength={2000} rows={4} value={returnReason} onChange={(event) => setReturnReason(event.target.value)} placeholder="Explain what needs correction"/></label><footer><button type="button" className="inventory-secondary" disabled={busy} onClick={() => setReturnDialog(false)}>Cancel</button><button type="button" className="primary-button" disabled={busy || !returnReason.trim()} onClick={() => void returnForCorrection()}>{busy ? "Returning…" : "Confirm return"}</button></footer></section></div>}    {confirm && selected && <div className="reservation-dialog-backdrop" role="presentation"><section className="reservation-dialog handover-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="handover-confirm-title"><p className="eyebrow">MD FINAL REVIEW</p><h3 id="handover-confirm-title">Finalize {selected.reference}?</h3><p>This records actual delivery of <strong>{selected.vehicle_name}</strong> to <strong>{selected.customer_name}</strong> after MD and CEO approval and changes vehicle status to Handed Over.</p><ul>{Object.entries(conditionLabels).map(([key, text]) => <li key={key}>{text}: {selected.vehicle_condition_checklist?.[key] ? "Complete" : "Incomplete"}</li>)}{Object.entries(documentLabels).map(([key, text]) => <li key={key}>{text}: {selected.keys_documents_checklist?.[key] ? "Complete" : "Incomplete"}</li>)}</ul><dl><div><dt>Verified payments</dt><dd>{money(selected.financial_summary.verified_received_lkr)}</dd></div><div><dt>Outstanding balance</dt><dd>{money(selected.financial_summary.outstanding_balance_lkr)}</dd></div></dl>{selected.financial_summary.balance_review_required && <p className="handover-balance-warning">The outstanding finance balance remains due after the authorized release; handover does not record it as paid.</p>}<p>Only finalize after delivery, checklist, customer acknowledgement and down-payment verification are complete. This action is permanent.</p><footer><button className="inventory-secondary" disabled={busy} onClick={() => setConfirm(false)}>Cancel</button><button className="primary-button" disabled={busy || !checksComplete || !selected.customer_acknowledgement || !selected.delivery_date || !selected.financial_summary.down_payment_satisfied} onClick={() => void finalize()}>{busy ? "Finalizing…" : "Confirm handover finalization"}</button></footer></section></div>}
  </main>;
}
