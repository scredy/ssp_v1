"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, API } from "@/lib/car-api";

type BLRequest = { id: number; reference: string; import_reference: string; request_note: string; status: "pending" | "approved" | "rejected"; requested_by_name: string; requested_at: string; decided_by_name: string | null; decided_at: string | null; rejection_reason: string };
type ImportRow = { reference: string; customer_name: string; vehicle_reference: string | null; vehicle_description: string; country_of_origin: string; bl_requests: BLRequest[] };
type InboxItem = BLRequest & Pick<ImportRow, "customer_name" | "vehicle_reference" | "vehicle_description" | "country_of_origin">;
const when = (v: string | null) => v ? new Intl.DateTimeFormat("en-LK", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Colombo" }).format(new Date(v)) + " SLST" : "—";
const title = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export default function StaffBLRequests() {
  const router = useRouter();
  const [role, setRole] = useState("");
  const [items, setItems] = useState<InboxItem[]>([]);
  const [selected, setSelected] = useState<InboxItem | null>(null);
  const [filter, setFilter] = useState("pending");
  const [rejecting, setRejecting] = useState(false);
  const [rejectionReason, setRejectionReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    fetch(`${API}/api/auth/me/`, { credentials: "include" }).then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .then((user: { role: string }) => { if (user.role !== "ceo") throw new Error(); setRole(user.role); })
      .catch(() => router.replace("/staff"));
  }, [router]);

  const load = useCallback(async () => {
    if (role !== "ceo") return;
    setLoading(true); setError("");
    try {
      const imports = await api<ImportRow[]>("/api/staff/imports/");
      const requests = imports.flatMap((item) => (item.bl_requests || []).map((request) => ({ ...request, customer_name: item.customer_name, vehicle_reference: item.vehicle_reference, vehicle_description: item.vehicle_description, country_of_origin: item.country_of_origin })));
      setItems(requests);
      setSelected((current) => current ? requests.find((r) => r.id === current.id) || null : requests.find((r) => r.status === "pending") || requests[0] || null);
    } catch (e) { setError(e instanceof Error ? e.message : "BL requests could not be loaded."); }
    finally { setLoading(false); }
  }, [role]);
  useEffect(() => { void load(); }, [load]);

  const visible = items.filter((item) => filter === "all" || item.status === filter);
  const countBy = (s: string) => items.filter((x) => x.status === s).length;

  async function decide(decision: "approved" | "rejected") {
    if (!selected || busy || (decision === "rejected" && !rejectionReason.trim())) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<BLRequest>(`/api/staff/bl-requests/${selected.id}/decision/`, { method: "POST", body: JSON.stringify({ decision, rejection_reason: decision === "rejected" ? rejectionReason.trim() : "" }) });
      setNotice(`${selected.reference} ${decision}.`); setRejecting(false); setRejectionReason(""); await load();
      setSelected((current) => current ? { ...current, ...result } : null);
    } catch (e) { setError(e instanceof Error ? e.message : "The BL request could not be processed."); }
    finally { setBusy(false); }
  }

  return <div className="bl-inbox-page">
    <div className="imports-heading"><div><p className="eyebrow">CEO WORKSPACE</p><h2>BL approval requests</h2><p>Review staff requests for bill of lading approval. Approval does not record that a BL has been issued.</p></div></div>
    {error && <p className="reservation-feedback is-error" role="alert">{error}</p>}{notice && <p className="reservation-feedback" role="status">{notice}</p>}
    <div className="bl-status-tabs" aria-label="BL request status filter">{[["pending", `Pending (${countBy("pending")})`], ["approved", `Approved (${countBy("approved")})`], ["rejected", `Rejected (${countBy("rejected")})`], ["all", `All (${items.length})`]].map(([value, label]) => <button key={value} className={filter === value ? "is-active" : ""} onClick={() => setFilter(value)}>{label}</button>)}</div>
    <section className="bl-inbox-layout">{loading ? <p className="public-state">Loading BL requests…</p> : <div className="reservation-table-wrap"><table className="reservation-table bl-request-table"><thead><tr><th>Request</th><th>Import / vehicle</th><th>Customer</th><th>Origin</th><th>Requested by</th><th>Requested</th><th>Status</th></tr></thead><tbody>{visible.map((item) => <tr key={item.id} className={selected?.id === item.id ? "is-selected" : ""} onClick={() => setSelected(item)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setSelected(item)}><td><strong>{item.reference}</strong></td><td>{item.import_reference}<small>{item.vehicle_reference || item.vehicle_description}</small></td><td>{item.customer_name}</td><td>{item.country_of_origin}</td><td>{item.requested_by_name}</td><td>{when(item.requested_at)}</td><td><span className={`import-status is-${item.status}`}>{title(item.status)}</span></td></tr>)}</tbody></table>{visible.length === 0 && <div className="reservation-empty"><h3>No requests in this view</h3><p>Requests are shown here after staff submit them for CEO approval.</p></div>}</div>}
      {selected && <aside className="bl-request-detail"><div className="import-detail-head"><div><p className="eyebrow">REQUEST DETAIL</p><h3>{selected.reference}</h3></div><span className={`import-status is-${selected.status}`}>{title(selected.status)}</span></div><dl><div><dt>Import</dt><dd>{selected.import_reference}</dd></div><div><dt>Vehicle</dt><dd>{selected.vehicle_description}<small>{selected.vehicle_reference || "Not linked to stock"}</small></dd></div><div><dt>Customer</dt><dd>{selected.customer_name}</dd></div><div><dt>Country of origin</dt><dd>{selected.country_of_origin}</dd></div><div><dt>Requested by</dt><dd>{selected.requested_by_name}<small>{when(selected.requested_at)}</small></dd></div>{selected.decided_by_name && <div><dt>Decision recorded by</dt><dd>{selected.decided_by_name}<small>{when(selected.decided_at)}</small></dd></div>}</dl><section className="bl-request-note"><h4>Staff request details</h4><p>{selected.request_note || "No additional note was provided."}</p></section>
        {selected.status === "pending" && <div className="bl-decision-actions"><button className="primary-button" disabled={busy} onClick={() => { if (window.confirm(`Approve BL request ${selected.reference} for ${selected.import_reference}? This approval is not a BL issuance.`)) void decide("approved"); }}>{busy ? "Saving…" : "Approve request"}</button><button className="inventory-danger" disabled={busy} onClick={() => { setRejectionReason(""); setRejecting(true); }}>Reject request</button></div>}
        {selected.status === "rejected" && <section className="bl-request-note"><h4>Rejection reason</h4><p>{selected.rejection_reason}</p></section>}
        {selected.status === "approved" && <p className="import-form-note">CEO approval is recorded. Staff must separately record BL issuance as an operational milestone.</p>}
      </aside>}
    </section>
    {rejecting && selected && <div className="reservation-dialog-backdrop" role="presentation"><section className="reservation-dialog" role="dialog" aria-modal="true" aria-labelledby="bl-reject-title"><p className="eyebrow">BL APPROVAL</p><h2 id="bl-reject-title">Reject {selected.reference}?</h2><p>The rejection will be recorded in the request history.</p><label>Rejection reason *<textarea rows={4} maxLength={1000} value={rejectionReason} onChange={(e) => setRejectionReason(e.target.value)}/></label><div><button className="inventory-secondary" disabled={busy} onClick={() => setRejecting(false)}>Cancel</button><button className="inventory-danger" disabled={busy || !rejectionReason.trim()} onClick={() => void decide("rejected")}>{busy ? "Saving…" : "Confirm rejection"}</button></div></section></div>}
  </div>;
}
