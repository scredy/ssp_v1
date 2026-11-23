"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/car-api";
import { commissionActions, paidLeaderboardRows, CommissionStatus } from "@/lib/commission-ui.mjs";

type Entry = {
  id: number; sale_reference: string; handover_reference: string; vehicle_reference: string; recipient_name: string | null;
  sale_price_lkr: string; commission_rate_percent: string | null; commission_amount_lkr: string | null; status: CommissionStatus;
  created_at: string; payout_reference: string; payout_date: string | null; payout_amount_lkr: string | null;
  approved_by: string | null; paid_by: string | null; reversed_by: string | null; reversal_reason: string;
};
type Leader = { rep_name: string; paid_entries: number; paid_total_lkr: string; status: "paid" };
type ActionForm = { entry: Entry; action: "paid" | "reversed"; payout_reference: string; payout_date: string; payout_amount_lkr: string; reason: string };

const money = (value: string | number | null) => value === null ? "—" : new Intl.NumberFormat("en-LK", { style: "currency", currency: "LKR", maximumFractionDigits: 2 }).format(Number(value));
const today = () => new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: "Asia/Colombo" }).format(new Date());

export default function CommissionManagement() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [leaders, setLeaders] = useState<Leader[]>([]);
  const [role, setRole] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [form, setForm] = useState<ActionForm | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [ledger, leaderboard, user] = await Promise.all([
        api<Entry[]>("/api/commissions/"), api<Leader[]>("/api/commissions/?view=leaderboard"), api<{ role: string }>("/api/auth/me/"),
      ]);
      setEntries(ledger); setLeaders(leaderboard.map((row) => ({ ...row, status: "paid" }))); setRole(user.role);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Commission records could not be loaded."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const shown = useMemo(() => entries.filter((entry) => !search.trim() || [entry.sale_reference, entry.handover_reference, entry.vehicle_reference, entry.recipient_name ?? ""].some((value) => value.toLowerCase().includes(search.trim().toLowerCase()))), [entries, search]);
  const paidTotal = leaders.reduce((total, row) => total + Number(row.paid_total_lkr), 0);

  async function transition(entry: Entry, target: "approved" | "paid" | "reversed", values: ActionForm | null = null) {
    setSaving(true); setError(""); setNotice("");
      const payload = target === "approved" ? { status: target } : target === "paid" ? {
      status: target, payout_reference: values?.payout_reference.trim(), payout_date: values?.payout_date,
      payout_amount_lkr: values?.payout_amount_lkr,
    } : { status: target, reason: values?.reason.trim() };
    try {
      await api(`/api/commissions/${entry.id}/transition/`, { method: "POST", body: JSON.stringify(payload) });
      setNotice(`Commission for ${entry.sale_reference} is now ${target}.`); setForm(null); await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Commission state could not be updated."); }
    finally { setSaving(false); }
  }

  function beginAction(entry: Entry, action: "paid" | "reversed") {
    setError(""); setForm({ entry, action, payout_reference: "", payout_date: today(), payout_amount_lkr: entry.commission_amount_lkr ?? "", reason: "" });
  }

  return <main className="workspace-page commission-management-page">
    <header className="handover-page-heading"><div><p className="eyebrow">LEADERSHIP · COMMISSIONS</p><h2>Commission payout ledger</h2><p>Review pending handover-earned entries and record approved, paid, or reversed states.</p></div></header>
    <p className="commission-policy-rule">Payout actions record manual payment details only; they do not transfer money. Sale price, CEO policy rate, and finalized handover snapshot remain unchanged. Entries without an assigned Rep or calculated rate cannot be approved.</p>
    {error && <p className="reservation-feedback is-error" role="alert">{error}</p>}{notice && <p className="commission-policy-notice" role="status">{notice}</p>}
    <section className="staff-dashboard-metrics commission-payout-metrics"><article><span>Ledger entries</span><strong>{loading ? "—" : entries.length}</strong></article><article><span>Paid entries</span><strong>{loading ? "—" : leaders.reduce((sum, row) => sum + row.paid_entries, 0)}</strong></article><article><span>Total paid</span><strong>{loading ? "—" : money(paidTotal)}</strong></article></section>
    <section className="reservation-detail commission-leaderboard"><p className="eyebrow">PAID ONLY</p><h3>Representative leaderboard</h3><p>Totals include paid entries only. Reversed, pending, and approved entries are excluded.</p><div className="reservation-table-wrap"><table className="reservation-table"><thead><tr><th>Rank</th><th>Representative</th><th>Paid entries</th><th>Total paid</th></tr></thead><tbody>{loading ? <tr><td colSpan={4}>Loading leaderboard…</td></tr> : paidLeaderboardRows(leaders).length ? paidLeaderboardRows(leaders).map((row, index) => <tr key={`${row.rep_name}-${index}`}><td>{index + 1}</td><td>{row.rep_name}</td><td>{row.paid_entries}</td><td>{money(row.paid_total_lkr)}</td></tr>) : <tr><td colSpan={4}>No paid commission entries yet.</td></tr>}</tbody></table></div></section>
    <div className="reservation-toolbar"><label>Search ledger<input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Sale, handover, vehicle, or Rep" /></label><span>{shown.length} entries</span></div>
    <section className="reservation-detail"><div className="reservation-table-wrap"><table className="reservation-table commission-ledger-table"><thead><tr><th>Sale / handover</th><th>Rep</th><th>Sale price</th><th>Rate</th><th>Commission</th><th>Status / payout</th><th>Actions</th></tr></thead><tbody>{loading ? <tr><td colSpan={7}>Loading commission ledger…</td></tr> : shown.length ? shown.map((entry) => <tr key={entry.id}><td><strong>{entry.sale_reference}</strong><small>{entry.vehicle_reference} · {entry.handover_reference}</small></td><td>{entry.recipient_name ?? "No Rep assigned"}</td><td>{money(entry.sale_price_lkr)}</td><td>{entry.commission_rate_percent === null ? "Rate unavailable" : `${entry.commission_rate_percent}%`}</td><td>{money(entry.commission_amount_lkr)}</td><td><span className={`reservation-status is-${entry.status}`}>{entry.status}</span>{entry.status === "approved" && <small>Approved by {entry.approved_by ?? "—"}</small>}{entry.status === "paid" && <small>{entry.payout_reference} · {entry.payout_date} · {money(entry.payout_amount_lkr)} · by {entry.paid_by}</small>}{entry.status === "reversed" && <small>{entry.reversal_reason} · by {entry.reversed_by}</small>}</td><td><div className="commission-row-actions">{commissionActions(role, entry.status).map((action) => action === "approved" ? <button key={action} className="inventory-secondary" disabled={saving || !entry.recipient_name || entry.commission_amount_lkr === null} title={!entry.recipient_name || entry.commission_amount_lkr === null ? "This entry needs an assigned Rep and calculated rate before approval." : undefined} onClick={() => void transition(entry, "approved")}>Approve</button> : <button key={action} className="inventory-secondary" disabled={saving} onClick={() => beginAction(entry, action as "paid" | "reversed")}>{action === "paid" ? "Record payout" : "Reverse"}</button>)}</div></td></tr>) : <tr><td colSpan={7}>No commission entries match.</td></tr>}</tbody></table></div></section>
    {form && <div className="reservation-dialog-backdrop" role="presentation"><form className="reservation-dialog" role="dialog" aria-modal="true" aria-labelledby="commission-action-title" onSubmit={(event) => { event.preventDefault(); void transition(form.entry, form.action, form); }}><p className="eyebrow">{form.action === "paid" ? "RECORD MANUAL PAYOUT" : "REVERSE COMMISSION"}</p><h3 id="commission-action-title">{form.action === "paid" ? `Pay ${form.entry.sale_reference}` : `Reverse ${form.entry.sale_reference}`}</h3>{form.action === "paid" ? <div className="reservation-form-grid"><label>Payout reference *<input required maxLength={100} value={form.payout_reference} onChange={(event) => setForm({ ...form, payout_reference: event.target.value })} /></label><label>Payout date *<input required type="date" value={form.payout_date} onChange={(event) => setForm({ ...form, payout_date: event.target.value })} /></label><label>Amount (LKR) *<input required type="number" min="0.01" step="0.01" value={form.payout_amount_lkr} onChange={(event) => setForm({ ...form, payout_amount_lkr: event.target.value })} /><small>Must equal the immutable commission amount: {money(form.entry.commission_amount_lkr)}</small></label></div> : <label>Reason for reversal *<textarea required rows={4} value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} /></label>}{error && <p className="reservation-feedback is-error" role="alert">{error}</p>}<footer><button type="button" className="inventory-secondary" disabled={saving} onClick={() => setForm(null)}>Cancel</button><button className="primary-button" disabled={saving}>{saving ? "Saving…" : form.action === "paid" ? "Record payout" : "Confirm reversal"}</button></footer></form></div>}
  </main>;
}
