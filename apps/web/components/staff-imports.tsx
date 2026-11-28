"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, API, Vehicle } from "@/lib/car-api";
import { PaymentPanel } from "@/components/payment-ui";

type InventoryVehicle = Vehicle & { has_import_link?: boolean };

type ImportStatus = "new" | "booking_confirmed" | "lc_opened" | "bl_issued" | "shipping" | "arrived" | "customs_clearance" | "ready_for_collection" | "handed_over";
type ImportRecord = {
  id: number; reference: string; customer_id?: number; customer_name: string; vehicle_id?: number | null;
  vehicle_reference: string | null; vehicle_description: string; vehicle_details?: string;
  country_of_origin: string; status: ImportStatus; shipping_information?: string; estimated_arrival: string | null;
  internal_notes?: string; customer_updates: string; responsible_staff_name: string; created_at: string; updated_at: string;
  milestones?: Milestone[]; bl_requests?: BLRequest[]; advance_verified?: boolean;
};
type Milestone = { id: number; kind: string; occurred_at: string; actor_name: string; customer_description: string; created_at: string };
type BLRequest = { id: number; reference: string; import_reference: string; request_note: string; status: "pending" | "approved" | "rejected"; requested_by_name: string; requested_at: string; decided_by_name: string | null; decided_at: string | null; rejection_reason: string };
type Customer = { id: number; full_name: string; email: string; phone: string };
type Summary = { total_count: number; status_counts: Record<string, number>; pending_bl_approval_count: number };
type TrackingAccessResult = { tracking_reference: string; pin: string; issued_at: string };
const statuses: ImportStatus[] = ["new", "booking_confirmed", "lc_opened", "bl_issued", "shipping", "arrived", "customs_clearance", "ready_for_collection", "handed_over"];
const milestones = [
  ["booking_confirmed", "Booking confirmed"], ["payment_verified", "Advance / payment verified"], ["lc_opened", "LC opened"],
  ["bl_issued", "BL issued"], ["shipping", "Shipping"], ["arrival", "Arrival"],
  ["customs_clearance", "Customs clearance"], ["ready_for_collection", "Ready for collection"],
] as const;
const title = (v: string) => v.replaceAll("_", " ").replace(/\b\w/g, (x) => x.toUpperCase());
const when = (v: string | null) => v ? new Intl.DateTimeFormat("en-LK", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Colombo" }).format(new Date(v)) + " SLST" : "—";
const blankImport = { customer_id: "", vehicle_id: "", vehicle_details: "", country_of_origin: "", shipping_information: "", estimated_arrival: "", internal_notes: "", customer_updates: "" };

export default function StaffImports() {
  const router = useRouter();
  const [role, setRole] = useState("");
  const [items, setItems] = useState<ImportRecord[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [vehicles, setVehicles] = useState<InventoryVehicle[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [selected, setSelected] = useState<ImportRecord | null>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(blankImport);
  const [editForm, setEditForm] = useState<Partial<ImportRecord>>({});
  const [milestoneKind, setMilestoneKind] = useState("");
  const [milestoneDescription, setMilestoneDescription] = useState("");
  const [paymentReference, setPaymentReference] = useState("");
  const [requestNote, setRequestNote] = useState("");
  const [trackingAccess, setTrackingAccess] = useState<TrackingAccessResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const isCEO = role === "ceo";
  const isStaff = role === "staff";
  const canManage = isStaff || isCEO;
  const canEdit = Boolean(selected) && (
    isCEO || (isStaff && selected?.status === "new")
  );

  const availableMilestones = milestones.filter(([kind]) =>
    Boolean(selected?.milestones) &&
    (isCEO || (isStaff && kind === "booking_confirmed")) &&
    !selected?.milestones?.some((m) => m.kind === kind)
  );

  const canRequestBL = isStaff &&
    Boolean(selected?.vehicle_id) &&
    Boolean(selected?.advance_verified) &&
    Boolean(selected?.milestones?.some(
      (m) => m.kind === "booking_confirmed"
    )) &&
    !selected?.bl_requests?.some(
      (r) => r.status === "pending" || r.status === "approved"
    );

  useEffect(() => {
    fetch(`${API}/api/auth/me/`, { credentials: "include" }).then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .then((u: { role: string }) => { if (!["staff", "ceo"].includes(u.role)) { router.replace("/staff"); return; } setRole(u.role); })
      .catch(() => router.replace("/staff/login"));
  }, [router]);

  const load = useCallback(async () => {
    if (!role) return;
    setLoading(true); setError("");
    try {
      const p = new URLSearchParams(); if (query.trim()) p.set("search", query.trim()); if (statusFilter) p.set("status", statusFilter);
      const [list, stats] = await Promise.all([api<ImportRecord[]>(`/api/staff/imports/?${p}`), api<Summary>("/api/staff/imports/summary/")]);
      setItems(list); setSummary(stats);
      if (canManage) {
        const [customerRows, vehicleRows] = await Promise.all([api<Customer[]>("/api/staff/customers/"), api<InventoryVehicle[]>("/api/staff/inventory/")]);
        setCustomers(customerRows); setVehicles(vehicleRows);
      }
    } catch (e) { setError(e instanceof Error ? e.message : "Imports could not be loaded."); }
    finally { setLoading(false); }
  }, [role, query, statusFilter, canManage]);
  useEffect(() => { void load(); }, [load]);

  async function openDetail(item: ImportRecord) {
    setSelected(item); setEditing(false); setTrackingAccess(null); setError("");
    setMilestoneKind(""); setMilestoneDescription(""); setPaymentReference(""); setRequestNote("");
    try { setSelected(await api<ImportRecord>(`/api/staff/imports/${encodeURIComponent(item.reference)}/`)); }
    catch (e) { setError(e instanceof Error ? e.message : "Import detail could not be loaded."); }
  }

  async function createImport(e: React.FormEvent) {
    e.preventDefault(); if (busy || !canManage || !form.vehicle_id) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const body = { ...form, customer_id: Number(form.customer_id), vehicle_id: Number(form.vehicle_id), estimated_arrival: form.estimated_arrival || null };
      const created = await api<ImportRecord>("/api/staff/imports/", { method: "POST", body: JSON.stringify(body) });
      setForm(blankImport); setCreating(false); setNotice(`Import ${created.reference} created.`); await load(); await openDetail(created);
    } catch (e) { setError(e instanceof Error ? e.message : "Import could not be created."); }
    finally { setBusy(false); }
  }

  function startEdit() {
    if (!selected || !canEdit) return;
    setEditForm({ vehicle_id: selected.vehicle_id ?? null, vehicle_details: selected.vehicle_details || "", country_of_origin: selected.country_of_origin,
      shipping_information: selected.shipping_information || "", estimated_arrival: selected.estimated_arrival || "", internal_notes: selected.internal_notes || "", customer_updates: selected.customer_updates || "" });
    setEditing(true);
  }
  async function saveEdit(e: React.FormEvent) {
    e.preventDefault(); if (!selected || busy || !canEdit || !editForm.vehicle_id) return;
    setBusy(true); setError(""); setNotice("");
    try { const saved = await api<ImportRecord>(`/api/staff/imports/${encodeURIComponent(selected.reference)}/`, { method: "PATCH", body: JSON.stringify({ ...editForm, vehicle_id: editForm.vehicle_id ?? null, estimated_arrival: editForm.estimated_arrival || null }) }); setSelected(await api<ImportRecord>(`/api/staff/imports/${encodeURIComponent(saved.reference)}/`)); setEditing(false); setNotice("Import details updated."); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "Import details could not be saved."); }
    finally { setBusy(false); }
  }
  async function recordMilestone(e: React.FormEvent) {
    e.preventDefault(); if (!selected || busy || !availableMilestones.some(([kind]) => kind === milestoneKind)) return;
    setBusy(true); setError(""); setNotice("");
    const body: Record<string, string> = { kind: milestoneKind, customer_description: milestoneDescription.trim() };
    if (milestoneKind === "payment_verified") body.payment_reference = paymentReference.trim();
    try { await api<Milestone>(`/api/staff/imports/${encodeURIComponent(selected.reference)}/milestones/`, { method: "POST", body: JSON.stringify(body) }); setNotice("Milestone recorded in the import timeline."); setMilestoneKind(""); setMilestoneDescription(""); setPaymentReference(""); await openDetail(selected); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "Milestone could not be recorded."); }
    finally { setBusy(false); }
  }
  async function requestBL(e: React.FormEvent) {
    e.preventDefault(); if (!selected || busy || !canRequestBL) return;
    setBusy(true); setError(""); setNotice("");
    try { await api<BLRequest>(`/api/staff/imports/${encodeURIComponent(selected.reference)}/bl-requests/`, { method: "POST", body: JSON.stringify({ request_note: requestNote.trim() }) }); setNotice("BL approval request submitted to the CEO."); setRequestNote(""); await openDetail(selected); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "BL request could not be submitted."); }
    finally { setBusy(false); }
  }
  async function rotateTracking() {
    if (!selected || busy || !isCEO) return;
    if (!window.confirm(`Issue or rotate secure tracking access for ${selected.reference}? The new PIN will be shown once.`)) return;
    setBusy(true); setError(""); setNotice(""); setTrackingAccess(null);
    try { setTrackingAccess(await api<TrackingAccessResult>(`/api/staff/imports/${encodeURIComponent(selected.reference)}/tracking-access/`, { method: "POST", body: "{}" })); setNotice("Tracking access issued. Copy the PIN now; it will not be shown again."); }
    catch (e) { setError(e instanceof Error ? e.message : "Tracking access could not be issued."); }
    finally { setBusy(false); }
  }

  return <div className="imports-page">
    <div className="imports-heading"><div><p className="eyebrow">IMPORT OPERATIONS</p><h2>Import directory</h2><p>Follow import progress, BL approvals and customer-visible updates.</p></div>{canManage && <button className="primary-button" onClick={() => { setCreating((x) => !x); setError(""); }}>+ Create import</button>}</div>
    {summary && <section className="import-stats"><article><span>Total imports</span><strong>{summary.total_count}</strong></article><article><span>In progress</span><strong>{Object.entries(summary.status_counts).filter(([k]) => !["ready_for_collection", "handed_over"].includes(k)).reduce((n, [, v]) => n + v, 0)}</strong></article><article><span>Ready for collection</span><strong>{summary.status_counts.ready_for_collection || 0}</strong></article><article><span>Handed over</span><strong>{summary.status_counts.handed_over || 0}</strong></article><article><span>BL requests pending</span><strong>{summary.pending_bl_approval_count}</strong></article></section>}
    {error && <p className="reservation-feedback is-error" role="alert">{error}</p>}{notice && <p className="reservation-feedback" role="status">{notice}</p>}
    {creating && canManage && <form className="reservation-form import-form" onSubmit={createImport}><div className="reservation-form-heading"><div><p className="eyebrow">NEW IMPORT ORDER</p><h3>Create import</h3></div><button type="button" className="inventory-secondary" onClick={() => setCreating(false)}>Cancel</button></div><div className="reservation-form-grid">
      <label>Customer *<select required value={form.customer_id} onChange={(e) => setForm({ ...form, customer_id: e.target.value })}><option value="">Select customer</option>{customers.map((c) => <option key={c.id} value={c.id}>{c.full_name}{c.phone ? ` · ${c.phone}` : ""}</option>)}</select></label>
      <label>Linked draft vehicle *<select required value={form.vehicle_id} onChange={(e) => setForm({ ...form, vehicle_id: e.target.value })}><option value="">Select linked vehicle</option>{vehicles.filter((v) => v.status === "available" && v.visibility === "draft" && !v.has_import_link).map((v) => <option key={v.reference} value={v.id}>{v.reference} · {v.manufacture_year} {v.make} {v.model} · {title(v.status || "available")}</option>)}</select></label>
      <label>Country of origin *<input required maxLength={100} value={form.country_of_origin} onChange={(e) => setForm({ ...form, country_of_origin: e.target.value })}/></label>
      <label className="import-wide">Vehicle details<textarea rows={3} value={form.vehicle_details} onChange={(e) => setForm({ ...form, vehicle_details: e.target.value })}/></label>
      <label>Estimated arrival<input type="date" value={form.estimated_arrival} onChange={(e) => setForm({ ...form, estimated_arrival: e.target.value })}/></label>
      <label>Shipping information<textarea rows={2} value={form.shipping_information} onChange={(e) => setForm({ ...form, shipping_information: e.target.value })}/></label>
      <label>Customer-visible update<textarea rows={2} value={form.customer_updates} onChange={(e) => setForm({ ...form, customer_updates: e.target.value })}/></label>
      <label>Internal notes · Staff and CEO<textarea rows={2} value={form.internal_notes} onChange={(e) => setForm({ ...form, internal_notes: e.target.value })}/></label>
    </div><p className="import-form-note">Create an available draft vehicle in Inventory first, then link it here. Only the CEO can issue customer tracking access.</p><button className="primary-button" disabled={busy || !form.customer_id || !form.vehicle_id}>{busy ? "Saving…" : "Save import"}</button></form>}
    <div className="import-toolbar"><label>Search<input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Reference, customer, vehicle"/></label><label>Status<select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}><option value="">All statuses</option>{statuses.map((s) => <option key={s} value={s}>{title(s)}</option>)}</select></label><span>{items.length} imports</span></div>
    <section className="import-directory-area">{loading ? <p className="public-state">Loading imports…</p> : items.length === 0 ? <div className="reservation-empty"><h3>No imports found</h3><p>{query || statusFilter ? "Try another search or status." : "Import records will appear here when staff create them."}</p></div> : <div className="reservation-table-wrap"><table className="reservation-table import-table"><thead><tr><th>Reference</th><th>Customer</th><th>Vehicle</th><th>Origin</th><th>Milestone</th><th>BL status</th><th>ETA</th></tr></thead><tbody>{items.map((item) => <tr key={item.reference} onClick={() => void openDetail(item)} className={selected?.reference === item.reference ? "is-selected" : ""} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && void openDetail(item)}><td><strong>{item.reference}</strong></td><td>{item.customer_name}</td><td>{item.vehicle_description}<small>{item.vehicle_reference || "No linked stock record"}</small></td><td>{item.country_of_origin}</td><td><span className={`import-status is-${item.status}`}>{title(item.status)}</span></td><td>{item.bl_requests?.[0] ? <span className={`import-status is-${item.bl_requests[0].status}`}>{title(item.bl_requests[0].status)}</span> : "—"}</td><td>{item.estimated_arrival || "—"}</td></tr>)}</tbody></table></div>}
      {selected && <aside className="import-detail" aria-label="Import detail"><div className="import-detail-head"><div><p className="eyebrow">IMPORT DETAIL</p><h3>{selected.reference}</h3></div><div className="import-detail-head-actions"><span className={`import-status is-${selected.status}`}>{title(selected.status)}</span><button className="inventory-secondary" onClick={() => { setSelected(null); setEditing(false); setTrackingAccess(null); }} aria-label="Close import details">×</button></div></div>
        <div className="import-facts"><article><small>Customer</small><strong>{selected.customer_name}</strong></article><article><small>Vehicle</small><strong>{selected.vehicle_description}</strong><span>{selected.vehicle_reference || "No registered vehicle linked"}</span></article><article><small>Origin</small><strong>{selected.country_of_origin}</strong></article><article><small>Responsible staff</small><strong>{selected.responsible_staff_name}</strong></article></div>
        <div className="import-detail-actions">
          {canEdit && <button className="inventory-secondary" onClick={() => editing ? setEditing(false) : startEdit()}>{editing ? "Cancel edit" : "Edit import"}</button>}
          {isCEO && <button className="inventory-secondary" disabled={busy} onClick={() => void rotateTracking()}>{busy ? "Working…" : "Issue / rotate tracking access"}</button>}
          <button className="inventory-secondary" disabled={busy || editing} onClick={() => void openDetail(selected)}>Refresh details</button>
        </div>
        {editing && canEdit && <form className="import-edit-form" onSubmit={saveEdit}><h4>Edit import details</h4><div className="import-edit-grid"><label>Linked inventory vehicle *<select required value={String(editForm.vehicle_id ?? "")} onChange={(e) => setEditForm({ ...editForm, vehicle_id: e.target.value ? Number(e.target.value) : null })}><option value="">Select linked vehicle</option>{selected.vehicle_id && !vehicles.some((v) => v.id === selected.vehicle_id) && <option value={selected.vehicle_id}>{selected.vehicle_description}</option>}{vehicles.filter((v) => (v.status === "available" && v.visibility === "draft" && !v.has_import_link) || v.id === selected.vehicle_id).map((v) => <option key={v.reference} value={v.id}>{v.reference} · {v.manufacture_year} {v.make} {v.model} · {title(v.status || "available")}</option>)}</select></label><label>Country of origin<input required maxLength={100} value={editForm.country_of_origin || ""} onChange={(e) => setEditForm({ ...editForm, country_of_origin: e.target.value })}/></label><label>Estimated arrival<input type="date" value={editForm.estimated_arrival || ""} onChange={(e) => setEditForm({ ...editForm, estimated_arrival: e.target.value })}/></label><label>Shipping information<textarea rows={2} value={editForm.shipping_information || ""} onChange={(e) => setEditForm({ ...editForm, shipping_information: e.target.value })}/></label><label>Customer-visible updates<textarea rows={3} value={editForm.customer_updates || ""} onChange={(e) => setEditForm({ ...editForm, customer_updates: e.target.value })}/></label><label>Internal notes · Staff and CEO<textarea rows={3} value={editForm.internal_notes || ""} onChange={(e) => setEditForm({ ...editForm, internal_notes: e.target.value })}/></label><label className="import-wide">Vehicle details<textarea rows={2} value={editForm.vehicle_details || ""} onChange={(e) => setEditForm({ ...editForm, vehicle_details: e.target.value })}/></label></div><button className="primary-button" disabled={busy || !editForm.vehicle_id}>{busy ? "Saving…" : "Save changes"}</button></form>}
        <div className="import-detail-columns"><section className="import-timeline"><div className="import-section-heading"><h4>Milestone timeline</h4>{canManage && <span>Operational history</span>}</div>{selected.milestones?.length ? <ol>{selected.milestones.map((m) => <li key={m.id}><span className="import-timeline-dot"/><div><strong>{title(m.kind)}</strong><time>{when(m.occurred_at)}</time><p>{m.customer_description}</p><small>Recorded by {m.actor_name}</small></div></li>)}</ol> : <p className="import-subtle">No milestones have been recorded yet.</p>}
            {availableMilestones.length > 0 && <form className="import-action-form" onSubmit={recordMilestone}><h5>Record operational milestone</h5><label>Milestone<select required value={milestoneKind} onChange={(e) => setMilestoneKind(e.target.value)}><option value="">Select milestone</option>{availableMilestones.map(([kind, label]) => <option key={kind} value={kind}>{label}</option>)}</select></label>{milestoneKind === "payment_verified" && <label>Existing verified payment reference *<input required value={paymentReference} onChange={(e) => setPaymentReference(e.target.value)} placeholder="PAY-…"/><small>The API verifies that this payment is already verified and linked to this import.</small></label>}<label>Customer-safe description *<textarea required rows={2} maxLength={500} value={milestoneDescription} onChange={(e) => setMilestoneDescription(e.target.value)}/></label><button className="primary-button" disabled={busy || !milestoneKind}>{busy ? "Saving…" : "Add milestone"}</button></form>}
          </section><div className="import-side-sections"><PaymentPanel key={selected.reference} kind="import" reference={selected.reference} canRecord={isCEO}/><section className="import-customer-updates"><h4>Customer-visible updates</h4><p>{selected.customer_updates || "No customer update has been published."}</p><small>Estimated arrival: {selected.estimated_arrival || "Not provided"}</small></section>{canManage && <section className="import-internal-notes"><h4>Internal notes · Staff and CEO</h4><p>{selected.internal_notes || "No internal notes."}</p></section>}
            <section className="import-bl-section"><div className="import-section-heading"><h4>BL approval history</h4>{canManage && !selected.bl_requests?.some((x) => x.status === "pending") && <span>No pending request</span>}</div>{selected.bl_requests?.length ? selected.bl_requests.map((r) => <article className="import-bl-record" key={r.id}><div><strong>{r.reference}</strong><span className={`import-status is-${r.status}`}>{title(r.status)}</span></div><p>Requested by {r.requested_by_name} · {when(r.requested_at)}</p>{r.request_note && <p>{r.request_note}</p>}{r.decided_by_name && <small>{title(r.status)} by {r.decided_by_name} · {when(r.decided_at)}</small>}{r.rejection_reason && <p className="import-rejection-reason">{r.rejection_reason}</p>}</article>) : <p className="import-subtle">No BL approval requests recorded.</p>}
              {isStaff && !canRequestBL && !selected.bl_requests?.some((r) => r.status === "pending" || r.status === "approved") &&
                <p className="import-subtle">Confirm the booking and wait for CEO confirmation of the advance payment before requesting BL. Refresh details to check the latest status.</p>}
              {canRequestBL && <form className="import-action-form" onSubmit={requestBL}><label>Request note<textarea rows={2} maxLength={2000} value={requestNote} onChange={(e) => setRequestNote(e.target.value)} placeholder="Context for the CEO approval request"/></label><button className="primary-button" disabled={busy}>{busy ? "Submitting…" : "Request BL approval"}</button></form>}
            </section><section className="import-tracking-section"><h4>Secure customer tracking</h4><p>Only the CEO can issue or rotate tracking access. The PIN is shown once and cannot be recovered.</p>{trackingAccess && <div className="import-pin-issued" role="status"><strong>Copy this PIN now</strong><code>{trackingAccess.pin}</code><span>Tracking reference: {trackingAccess.tracking_reference}</span><small>Issued {when(trackingAccess.issued_at)}</small><button className="inventory-secondary" onClick={() => setTrackingAccess(null)}>Close and clear PIN</button></div>}</section>
          </div></div>
      </aside>}
    </section>
  </div>;
}
