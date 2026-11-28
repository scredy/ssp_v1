"use client";

import financeStyles from "./quotation-finance-options.module.css";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { API, api, User, Vehicle } from "@/lib/car-api";
import { amountFinanced, isDownPaymentValid, monthlyEstimate } from "@/lib/quotation-finance.mjs";

type QuoteStatus = "draft" | "issued" | "expired" | "voided";
type Customer = { id: number; full_name: string; email: string; phone: string };
type ImportOrder = { id: number; reference: string; customer_id: number; customer_name: string; vehicle_id: number | null; vehicle_description: string };
type Quotation = {
  id: number; reference: string; customer: number; customer_name: string; vehicle: number | null; vehicle_reference: string | null;
  import_order: number | null; import_reference: string | null; vehicle_description: string; vehicle_specifications: Record<string, unknown>;
  vehicle_selling_price_lkr: string; additional_charges_lkr: string; discount_lkr: string; quotation_total_lkr: string;
  issue_date: string; expiry_date: string; internal_notes: string; customer_terms: string; finance_term: string; finance_terms: string[];
  finance_down_payment_lkr: string; status: QuoteStatus; responsible_staff_name: string; issued_at: string | null;
  issued_snapshot: Record<string, unknown> | null; void_reason: string; created_at: string; updated_at: string;
};
type QuoteForm = {
  customer: string; vehicle: string; import_order: string; vehicle_description: string; vehicle_specifications: string;
  vehicle_selling_price_lkr: string; additional_charges_lkr: string; discount_lkr: string; issue_date: string;
  expiry_date: string; customer_terms: string; internal_notes: string; finance_terms: string[]; finance_down_payment_lkr: string;
};
type FinanceOption = { id: string; label: string; rate_per_100k_lkr: string; unit_amount_lkr: string };
const today = () => { const date = new Date(); return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 10); };
const addDays = (date: string, count: number) => { const value = new Date(`${date}T12:00:00`); value.setDate(value.getDate() + count); return value.toISOString().slice(0, 10); };
const initialForm = (): QuoteForm => { const issueDate = today(); return { customer: "", vehicle: "", import_order: "", vehicle_description: "", vehicle_specifications: "", vehicle_selling_price_lkr: "", additional_charges_lkr: "0", discount_lkr: "0", issue_date: issueDate, expiry_date: addDays(issueDate, 30), customer_terms: "", internal_notes: "", finance_terms: [], finance_down_payment_lkr: "0" }; };
const lkr = (amount: number | string) => new Intl.NumberFormat("en-LK", { style: "currency", currency: "LKR", maximumFractionDigits: 2 }).format(Number(amount || 0));
const dateLabel = (value: string) => value ? new Intl.DateTimeFormat("en-LK", { dateStyle: "medium", timeZone: "Asia/Colombo" }).format(new Date(`${value}T12:00:00`)) : "—";
const title = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);
const specText = (specs?: Record<string, unknown> | null) => Object.entries(specs || {}).filter(([, value]) => value !== null && value !== "").map(([key, value]) => `${key.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())}: ${String(value)}`).join("\n");
const parseSpecs = (value: string) => Object.fromEntries(value.split("\n").map((line) => line.split(":")).filter((parts) => parts.length >= 2 && parts[0].trim()).map(([key, ...rest]) => [key.trim().toLowerCase().replaceAll(" ", "_"), rest.join(":").trim()]));

export default function StaffQuotations() {
  const [user, setUser] = useState<User | null>(null);
  const [rows, setRows] = useState<Quotation[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [imports, setImports] = useState<ImportOrder[]>([]);
  const [financeOptions, setFinanceOptions] = useState<FinanceOption[]>([]);
  const [selected, setSelected] = useState<Quotation | null>(null);
  const [form, setForm] = useState<QuoteForm>(initialForm);
  const [editing, setEditing] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [voidTarget, setVoidTarget] = useState<string | null>(null);
  const [voidReason, setVoidReason] = useState("");
  const isCEO = user?.role === "ceo";
  const isMD = user?.role === "manager";
  const canManage = Boolean(user && ["staff", "manager", "ceo"].includes(user.role));
  const canManageQuote = (quote: Quotation) =>
    user?.role === "staff" ||
    (quote.import_order ? isCEO : isMD);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const params = new URLSearchParams();
      if (search.trim()) params.set("search", search.trim());
      const list = await api<Quotation[]>(`/api/staff/quotations/?${params}`);
      setRows(list);
    } catch (exception) { setError(exception instanceof Error ? exception.message : "Quotations could not be loaded."); }
    finally { setLoading(false); }
  }, [search]);

  useEffect(() => {
    let active = true;
    api<User>("/api/auth/me/").then(async (current) => {
      if (!active) return;
      setUser(current);
      if (!["staff", "manager", "ceo"].includes(current.role)) return;
      const [customerRows, vehicleRows, importRows, financeRows] = await Promise.all([
        api<Customer[]>("/api/staff/customers/"), api<Vehicle[]>("/api/staff/inventory/"), (current.role === "manager" ? Promise.resolve([] as ImportOrder[]) : api<ImportOrder[]>("/api/staff/imports/")),
        api<FinanceOption[]>("/api/staff/quotations/finance-options/"),
      ]);
      if (active) { setCustomers(customerRows); setVehicles(vehicleRows); setImports(importRows); setFinanceOptions(financeRows); }
    }).catch((exception) => { if (active) setError(exception instanceof Error ? exception.message : "Quotation workspace could not be loaded."); })
      .finally(() => { if (active) setLoading(false); });
    const params = new URLSearchParams(window.location.search);
    const customerId = params.get("customer") || params.get("customer_id") || "";
    const vehicleId = params.get("vehicle") || params.get("vehicle_id") || "";
    const importId = params.get("import_order") || "";
    if (customerId || vehicleId || importId) {
      setForm((value) => ({ ...value, customer: customerId, vehicle: vehicleId, import_order: importId }));
      setCreating(true);
    }
    return () => { active = false; };
  }, []);
  useEffect(() => { if (user && ["staff", "manager", "ceo"].includes(user.role)) void load(); }, [user, load]);

  const counts = useMemo(() => ({ all: rows.length, draft: rows.filter((item) => item.status === "draft").length, issued: rows.filter((item) => item.status === "issued").length, expired: rows.filter((item) => item.status === "expired").length, voided: rows.filter((item) => item.status === "voided").length }), [rows]);
  const visibleRows = statusFilter ? rows.filter((item) => item.status === statusFilter) : rows;
  const price = Number(form.vehicle_selling_price_lkr || 0);
  const charges = Number(form.additional_charges_lkr || 0);
  const discount = Number(form.discount_lkr || 0);
  const previewTotal = Math.max(0, price + charges - discount);
  const downPaymentValid = !form.vehicle_selling_price_lkr || isDownPaymentValid(form.vehicle_selling_price_lkr, form.finance_down_payment_lkr);
  const financedAmount = downPaymentValid && form.vehicle_selling_price_lkr ? amountFinanced(form.vehicle_selling_price_lkr, form.finance_down_payment_lkr) : null;
  const selectedFinanceOptions = financeOptions.filter((option) => form.finance_terms.includes(option.id));
  const liveFinanceEstimates = financedAmount === null ? [] : selectedFinanceOptions.map((option) => ({
    ...option, monthly: monthlyEstimate(financedAmount, option.rate_per_100k_lkr),
  }));

  function setField<K extends keyof QuoteForm>(key: K, value: QuoteForm[K]) { setForm((current) => ({ ...current, [key]: value })); }
  function openNew() {
    setSelected(null); setEditing(null); setError(""); setNotice(""); setForm(initialForm()); setCreating(true);
  }
  async function openDetail(row: Quotation) {
    setError(""); setNotice(""); setCreating(false); setEditing(null); setBusy(true);
    try { setSelected(await api<Quotation>(`/api/staff/quotations/${encodeURIComponent(row.reference)}/`)); }
    catch (exception) { setError(exception instanceof Error ? exception.message : "Quotation details could not be loaded."); }
    finally { setBusy(false); }
  }
  function editDraft(row: Quotation) {
    if (!canManageQuote(row)) return;
    setSelected(row); setEditing(row.reference); setCreating(true); setError(""); setNotice("");
    setForm({ customer: String(row.customer), vehicle: row.vehicle ? String(row.vehicle) : "", import_order: row.import_order ? String(row.import_order) : "",
      vehicle_description: row.vehicle_description, vehicle_specifications: specText(row.vehicle_specifications), vehicle_selling_price_lkr: row.vehicle_selling_price_lkr,
      additional_charges_lkr: row.additional_charges_lkr, discount_lkr: row.discount_lkr, issue_date: row.issue_date, expiry_date: row.expiry_date,
      customer_terms: row.customer_terms, internal_notes: row.internal_notes, finance_terms: row.finance_terms?.length ? row.finance_terms : row.finance_term ? [row.finance_term] : [], finance_down_payment_lkr: row.finance_down_payment_lkr });
  }
  function chooseVehicle(value: string) {
    const vehicle = vehicles.find((item) => String(item.id) === value);
    setForm((current) => ({ ...current, vehicle: value, import_order: "", vehicle_description: vehicle ? `${vehicle.manufacture_year} ${vehicle.make} ${vehicle.model} ${vehicle.variant}`.trim() : current.vehicle_description,
      vehicle_specifications: vehicle ? specText({ year: vehicle.manufacture_year, make: vehicle.make, model: vehicle.model, variant: vehicle.variant, mileage_km: vehicle.mileage_km, fuel_type: vehicle.fuel_type, transmission: vehicle.transmission, condition: vehicle.condition, colour: vehicle.color }) : current.vehicle_specifications,
      vehicle_selling_price_lkr: vehicle ? String(vehicle.asking_price_lkr) : current.vehicle_selling_price_lkr }));
  }
  function chooseImport(value: string) {
    const item = imports.find((order) => String(order.id) === value);
    setForm((current) => ({ ...current, import_order: value, vehicle: "", customer: item ? String(item.customer_id) : current.customer,
      vehicle_description: item ? item.vehicle_description : current.vehicle_description }));
  }

  async function submitDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !canManage || (isCEO && !form.import_order) || (isMD && Boolean(form.import_order)) || !form.customer || !form.vehicle_description.trim() || !form.vehicle_selling_price_lkr || discount > price + charges || !downPaymentValid) return;
    setBusy(true); setError(""); setNotice("");
    const payload = { customer: Number(form.customer), vehicle: form.vehicle ? Number(form.vehicle) : null, import_order: form.import_order ? Number(form.import_order) : null,
      vehicle_description: form.vehicle_description.trim(), vehicle_specifications: parseSpecs(form.vehicle_specifications), vehicle_selling_price_lkr: form.vehicle_selling_price_lkr,
      additional_charges_lkr: form.additional_charges_lkr || "0", discount_lkr: form.discount_lkr || "0", issue_date: form.issue_date, expiry_date: form.expiry_date,
      customer_terms: form.customer_terms, internal_notes: form.internal_notes, finance_terms: form.finance_terms, finance_term: form.finance_terms[0] || "", finance_down_payment_lkr: form.finance_down_payment_lkr || "0" };
    try {
      const saved = editing ? await api<Quotation>(`/api/staff/quotations/${encodeURIComponent(editing)}/`, { method: "PATCH", body: JSON.stringify(payload) })
        : await api<Quotation>("/api/staff/quotations/", { method: "POST", body: JSON.stringify(payload) });
      setNotice(`${saved.reference} saved as a draft.`); setCreating(false); setEditing(null); setSelected(saved); await load();
    } catch (exception) { setError(exception instanceof Error ? exception.message : "Draft could not be saved."); }
    finally { setBusy(false); }
  }
  async function issue(reference: string) {
    if (busy || !window.confirm(`Issue ${reference}? Its quotation details will be locked as an immutable snapshot.`)) return;
    setBusy(true); setError(""); setNotice("");
    try { const result = await api<Quotation>(`/api/staff/quotations/${encodeURIComponent(reference)}/issue/`, { method: "POST", body: "{}" }); setSelected(result); setNotice(`${reference} issued successfully.`); await load(); }
    catch (exception) { setError(exception instanceof Error ? exception.message : "Quotation could not be issued."); }
    finally { setBusy(false); }
  }
  async function voidQuotation() {
    if (!voidTarget || !voidReason.trim() || busy) return;
    setBusy(true); setError(""); setNotice("");
    try { const result = await api<Quotation>(`/api/staff/quotations/${encodeURIComponent(voidTarget)}/void/`, { method: "POST", body: JSON.stringify({ reason: voidReason.trim() }) }); setSelected(result); setNotice(`${voidTarget} voided.`); setVoidTarget(null); setVoidReason(""); await load(); }
    catch (exception) { setError(exception instanceof Error ? exception.message : "Quotation could not be voided."); }
    finally { setBusy(false); }
  }
  async function downloadPdf(quote: Quotation) {
    setBusy(true); setError("");
    try {
      const response = await fetch(`${API}/api/staff/quotations/${encodeURIComponent(quote.reference)}/pdf/`, { credentials: "include" });
      if (!response.ok) { let message = `PDF download failed (${response.status}).`; try { const body = await response.json(); if (body.detail) message = body.detail; } catch { /* non-JSON response */ } throw new Error(message); }
      const blob = await response.blob(); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${quote.reference}.pdf`; document.body.appendChild(anchor); anchor.click(); anchor.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (exception) { setError(exception instanceof Error ? exception.message : "PDF could not be downloaded."); }
    finally { setBusy(false); }
  }

  const preview = selected?.issued_snapshot as Record<string, unknown> | null;
  const displayedCustomer = preview?.customer as { full_name?: string; email?: string; phone?: string } | undefined;
  const displayedDescription = (preview?.vehicle_description as string) || selected?.vehicle_description;
  const displayedPrice = (preview?.vehicle_selling_price_lkr as string) || selected?.vehicle_selling_price_lkr;
  const displayedCharges = (preview?.additional_charges_lkr as string) || selected?.additional_charges_lkr;
  const displayedDiscount = (preview?.discount_lkr as string) || selected?.discount_lkr;
  const displayedTotal = (preview?.quotation_total_lkr as string) || selected?.quotation_total_lkr;
  const displayedSpecs = (preview?.vehicle_specifications as Record<string, unknown>) || selected?.vehicle_specifications;
  const customerInfo = displayedCustomer || customers.find((customer) => customer.id === selected?.customer);

  if (!user) return <section className="quotation-page"><p className="public-state">Loading quotation workspace…</p></section>;

  return <section className="quotation-page">
    <div className="quotation-page-heading"><div><p className="eyebrow">CUSTOMER DOCUMENTS</p><h2>Quotations</h2><p>Prepare, issue and review customer price quotations.</p></div>{canManage && <button className="primary-button" onClick={openNew}>+ Create quotation</button>}</div>
    {error && <p className="reservation-feedback is-error" role="alert">{error}</p>}{notice && <p className="reservation-feedback" role="status">{notice}</p>}
    <div className="quotation-status-tabs" role="group" aria-label="Filter quotation status">{[["", "All", counts.all], ["draft", "Draft", counts.draft], ["issued", "Issued", counts.issued], ["expired", "Expired", counts.expired], ["voided", "Voided", counts.voided]].map(([value, label, count]) => <button key={String(value)} type="button" className={statusFilter === value ? "is-active" : ""} onClick={() => setStatusFilter(String(value))}>{label} <span>{count}</span></button>)}</div>
    <div className="quotation-toolbar"><label>Search quotations<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Quotation reference, customer or vehicle" /></label><span>{rows.length} records</span></div>

    {creating && canManage && <form className="quotation-editor" onSubmit={submitDraft}>
      <div className="quotation-editor-heading"><div><p className="eyebrow">{editing ? "EDIT DRAFT" : "NEW CUSTOMER QUOTATION"}</p><h3>{editing ? `Edit ${editing}` : "Create quotation"}</h3><span className="quotation-status is-draft">Draft</span></div><div className="quotation-editor-actions"><button type="button" className="inventory-secondary" onClick={() => { setCreating(false); setEditing(null); }}>Cancel</button><button className="primary-button" disabled={busy || (isCEO && !form.import_order) || (isMD && Boolean(form.import_order)) || discount > price + charges || !downPaymentValid}>{busy ? "Saving…" : "Save as draft"}</button></div></div>
      <div className="quotation-editor-grid"><div className="quotation-editor-fields">
        <section className="quotation-form-section"><h4>Customer and vehicle</h4><div className="quotation-fields-grid">
          <label>Customer *<select required value={form.customer} onChange={(event) => setField("customer", event.target.value)}><option value="">Select customer</option>{customers.map((customer) => <option key={customer.id} value={customer.id}>{customer.full_name}{customer.phone ? ` · ${customer.phone}` : ""}</option>)}</select></label>
          {!isCEO && <label>Inventory vehicle<select value={form.vehicle} onChange={(event) => chooseVehicle(event.target.value)}><option value="">No registered vehicle</option>{vehicles.map((vehicle) => <option key={vehicle.id} value={vehicle.id}>{vehicle.reference} · {vehicle.manufacture_year} {vehicle.make} {vehicle.model} · {vehicle.status}</option>)}</select></label>}
          {!isMD && <label>{isCEO ? "Import order *" : "Import order (optional)"}<select required={isCEO} value={form.import_order} onChange={(event) => chooseImport(event.target.value)}><option value="">No import linked</option>{imports.map((order) => <option key={order.id} value={order.id}>{order.reference} · {order.customer_name} · {order.vehicle_description}</option>)}</select></label>}
          <label className="quotation-wide">Vehicle description *<input required maxLength={240} value={form.vehicle_description} onChange={(event) => setField("vehicle_description", event.target.value)} placeholder="Make, model and variant" /></label>
          <label className="quotation-wide">Vehicle specifications<textarea rows={3} value={form.vehicle_specifications} onChange={(event) => setField("vehicle_specifications", event.target.value)} placeholder="One per line, for example: Year: 2025&#10;Fuel type: Hybrid" /><small>Enter each specification as “Name: value”.</small></label>
        </div></section>
        <section className="quotation-form-section"><h4>Price breakdown</h4><div className="quotation-fields-grid"><label>Vehicle selling price (LKR) *<input required type="number" min="0.01" step="0.01" value={form.vehicle_selling_price_lkr} onChange={(event) => setField("vehicle_selling_price_lkr", event.target.value)} /></label><label>Additional charges (LKR)<input type="number" min="0" step="0.01" value={form.additional_charges_lkr} onChange={(event) => setField("additional_charges_lkr", event.target.value)} /></label><label>Discount (LKR)<input type="number" min="0" step="0.01" value={form.discount_lkr} onChange={(event) => setField("discount_lkr", event.target.value)} /></label><div className="quotation-total-preview"><span>Live total estimate</span><strong>{lkr(previewTotal)}</strong><small>Final total is calculated by the server when saved.</small></div>{discount > price + charges && <p className="quotation-validation">Discount cannot exceed the vehicle price plus charges.</p>}</div></section>
        <section className="quotation-form-section"><h4>Validity and terms</h4><div className="quotation-fields-grid"><label>Issue date *<input required type="date" value={form.issue_date} onChange={(event) => setField("issue_date", event.target.value)} /></label><label>Expiry date *<input required type="date" min={form.issue_date} value={form.expiry_date} onChange={(event) => setField("expiry_date", event.target.value)} /></label><label className="quotation-wide">Customer-visible terms<textarea rows={3} value={form.customer_terms} onChange={(event) => setField("customer_terms", event.target.value)} /></label><label className="quotation-wide">Internal notes · staff only<textarea rows={2} value={form.internal_notes} onChange={(event) => setField("internal_notes", event.target.value)} /></label></div></section>
        <section className="quotation-form-section"><h4>Optional finance estimates</h4><p className="quotation-finance-note">All figures are illustrative estimates, not a confirmed lender offer.</p><fieldset className={`quotation-finance-options ${financeStyles.options}`}><legend>Select finance options</legend><label><input type="checkbox" checked={financeOptions.length > 0 && selectedFinanceOptions.length === financeOptions.length} onChange={(event) => setField("finance_terms", event.target.checked ? financeOptions.map((option) => option.id) : [])} /><span>Select all</span></label>{financeOptions.map((option) => <label key={option.id}><input type="checkbox" checked={form.finance_terms.includes(option.id)} onChange={(event) => setField("finance_terms", event.target.checked ? [...new Set([...form.finance_terms, option.id])] : form.finance_terms.filter((term) => term !== option.id))} /><span><strong>{option.label}</strong><small>LKR {option.rate_per_100k_lkr} per month per LKR 100,000</small></span></label>)}</fieldset><label>Down payment (LKR)<input type="number" min="0" max={form.vehicle_selling_price_lkr || undefined} step="0.01" value={form.finance_down_payment_lkr} onChange={(event) => setField("finance_down_payment_lkr", event.target.value)} /></label>{form.vehicle_selling_price_lkr && !downPaymentValid && <p className="quotation-validation">Down payment must be zero or more and cannot exceed the vehicle selling price.</p>}{form.finance_terms.length === 0 && <p className="quotation-finance-note">Leave all options unchecked to omit finance estimates.</p>}</section>
      </div><aside className="quotation-live-preview"><p className="eyebrow">CUSTOMER PREVIEW</p><h4>Quotation preview</h4><span className="quotation-preview-reference">{editing || "Draft preview"}</span><div className="quotation-preview-customer"><small>Prepared for</small><strong>{customers.find((customer) => String(customer.id) === form.customer)?.full_name || "Customer name"}</strong></div><div className="quotation-preview-customer"><small>Vehicle</small><strong>{form.vehicle_description || "Vehicle details will appear here"}</strong></div><dl><div><dt>Vehicle selling price</dt><dd>{lkr(price)}</dd></div><div><dt>Additional charges</dt><dd>{lkr(charges)}</dd></div><div><dt>Discount</dt><dd>− {lkr(discount)}</dd></div><div className="quotation-preview-total"><dt>Quotation total</dt><dd>{lkr(previewTotal)}</dd></div><div><dt>Valid until</dt><dd>{dateLabel(form.expiry_date)}</dd></div>{liveFinanceEstimates.map((option) => <div key={option.id}><dt>{option.label} estimate</dt><dd>{option.monthly === null ? "—" : lkr(option.monthly)}</dd></div>)}</dl>{selectedFinanceOptions.length > 0 && <p className="quotation-preview-note">Illustrative estimates. Amount financed is vehicle price less down payment; each rate is per LKR 100,000 per month.</p>}<p className="quotation-preview-note">Preview only. The backend-calculated total is authoritative.</p></aside></div>
    </form>}

    <div className="quotation-table-wrap">{loading ? <p className="public-state">Loading quotations…</p> : visibleRows.length === 0 ? <div className="reservation-empty"><h3>No quotations found</h3><p>{search || statusFilter ? "Try adjusting your search or status filter." : "New quotations will appear here."}</p>{canManage && !search && !statusFilter && <button className="primary-button" onClick={openNew}>Create quotation</button>}</div> : <table className="reservation-table quotation-table"><thead><tr><th>Quotation no.</th><th>Customer</th><th>Vehicle</th><th>Selling price</th><th>Total (LKR)</th><th>Validity</th><th>Status</th><th>Actions</th></tr></thead><tbody>{visibleRows.map((quote) => <tr key={quote.reference} onDoubleClick={() => void openDetail(quote)}><td><button className="quotation-reference" onClick={() => void openDetail(quote)}>{quote.reference}</button></td><td>{quote.customer_name}</td><td>{quote.vehicle_description}<small>{quote.vehicle_reference || quote.import_reference || "Manual vehicle details"}</small></td><td>{lkr(quote.vehicle_selling_price_lkr)}</td><td><strong>{lkr(quote.quotation_total_lkr)}</strong></td><td>{dateLabel(quote.expiry_date)}<small>Issued {dateLabel(quote.issue_date)}</small></td><td><span className={`quotation-status is-${quote.status}`}>{title(quote.status)}</span></td><td><div className="quotation-row-actions"><button type="button" onClick={() => void openDetail(quote)}>View</button>{canManageQuote(quote) && quote.status === "draft" && <button type="button" onClick={() => editDraft(quote)}>Edit</button>}{canManageQuote(quote) && quote.status === "draft" && <button type="button" onClick={() => void issue(quote.reference)}>Issue</button>}{quote.issued_snapshot && <button type="button" onClick={() => void downloadPdf(quote)}>PDF</button>}{canManageQuote(quote) && ["issued", "expired"].includes(quote.status) && <button className="is-danger" type="button" onClick={() => { setVoidTarget(quote.reference); setVoidReason(""); }}>Void</button>}</div></td></tr>)}</tbody></table>}</div>

    {selected && !creating && <div className="quotation-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelected(null); }}><section className="quotation-preview-modal" role="dialog" aria-modal="true" aria-labelledby="quotation-preview-title"><header><div><p className="eyebrow">QUOTATION PREVIEW</p><h3 id="quotation-preview-title">{selected.reference}</h3></div><button className="inventory-secondary" onClick={() => setSelected(null)} aria-label="Close quotation preview">×</button></header><div className="quotation-preview-meta"><span className={`quotation-status is-${selected.status}`}>{title(selected.status)}</span><span>Issue date · {dateLabel((preview?.issue_date as string) || selected.issue_date)}</span><span>Valid until · {dateLabel((preview?.expiry_date as string) || selected.expiry_date)}</span></div><div className="quotation-preview-detail-grid"><article><small>Customer</small><strong>{displayedCustomer?.full_name || customerInfo?.full_name || selected.customer_name}</strong>{(displayedCustomer?.email || customerInfo?.email) && <span>{displayedCustomer?.email || customerInfo?.email}</span>}{(displayedCustomer?.phone || customerInfo?.phone) && <span>{displayedCustomer?.phone || customerInfo?.phone}</span>}</article><article><small>Vehicle</small><strong>{displayedDescription}</strong><span>{selected.vehicle_reference || selected.import_reference || "Manual vehicle details"}</span></article></div><section className="quotation-preview-breakdown"><h4>Price breakdown</h4><dl><div><dt>Vehicle selling price</dt><dd>{lkr(displayedPrice || 0)}</dd></div><div><dt>Additional charges</dt><dd>{lkr(displayedCharges || 0)}</dd></div><div><dt>Discount</dt><dd>− {lkr(displayedDiscount || 0)}</dd></div><div className="quotation-preview-total"><dt>Quotation total</dt><dd>{lkr(displayedTotal || 0)}</dd></div></dl></section>{selected.customer_terms && <section className="quotation-preview-terms"><h4>Customer-visible terms</h4><p>{selected.customer_terms}</p></section>}{selected.void_reason && <p className="quotation-void-reason"><strong>Void reason:</strong> {selected.void_reason}</p>}<footer>{canManageQuote(selected) && selected.status === "draft" && <><button className="inventory-secondary" onClick={() => editDraft(selected)}>Edit draft</button><button className="primary-button" disabled={busy} onClick={() => void issue(selected.reference)}>Issue quotation</button></>}{selected.issued_snapshot && <button className="primary-button" disabled={busy} onClick={() => void downloadPdf(selected)}>Download official PDF</button>}{canManageQuote(selected) && ["issued", "expired"].includes(selected.status) && <button className="inventory-danger" onClick={() => { setVoidTarget(selected.reference); setVoidReason(""); }}>Void quotation</button>}</footer></section></div>}

    {voidTarget && <div className="quotation-modal-backdrop" role="presentation"><section className="quotation-confirm-modal" role="dialog" aria-modal="true" aria-labelledby="void-quotation-title"><header><div><p className="eyebrow">CONFIRM ACTION</p><h3 id="void-quotation-title">Void {voidTarget}</h3></div><button className="inventory-secondary" onClick={() => setVoidTarget(null)} aria-label="Close">×</button></header><p>This quotation will remain in history and cannot be reissued. Enter the reason to continue.</p><label>Reason for voiding *<textarea rows={3} maxLength={1000} value={voidReason} onChange={(event) => setVoidReason(event.target.value)} /></label><footer><button className="inventory-secondary" disabled={busy} onClick={() => setVoidTarget(null)}>Cancel</button><button className="inventory-danger" disabled={busy || !voidReason.trim()} onClick={() => void voidQuotation()}>{busy ? "Voiding…" : "Confirm void"}</button></footer></section></div>}
  </section>;
}
