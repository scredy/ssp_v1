"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/car-api";
import { paidLeaderboardRows } from "@/lib/commission-ui.mjs";

type Entry = { sale_reference: string; vehicle_reference: string; handover_reference: string; finalized_at: string; sale_price_lkr: string; commission_rate_percent: string | null; commission_amount_lkr: string | null; status: string; created_at: string; payout_reference: string | null; payout_date: string | null; payout_amount_lkr: string | null };
type PaidSummary = { rep_name: string; paid_entries: number; paid_total_lkr: string; status: "paid" };
const money = (value: string | number | null) => new Intl.NumberFormat("en-LK", { style: "currency", currency: "LKR", maximumFractionDigits: 2 }).format(Number(value || 0));
const date = (value: string | null) => value ? new Intl.DateTimeFormat("en-LK", { dateStyle: "medium", timeZone: "Asia/Colombo" }).format(new Date(value)) : "—";

export default function RepCommissions() {
  const [items, setItems] = useState<Entry[]>([]);
  const [paidSummary, setPaidSummary] = useState<PaidSummary[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const params = new URLSearchParams(); if (search.trim()) params.set("search", search.trim()); const [ledger, leaderboard] = await Promise.all([api<Entry[]>(`/api/rep/commissions/?${params}`), api<PaidSummary[]>("/api/rep/commissions/?view=leaderboard")]); setItems(ledger); setPaidSummary(leaderboard.map((row) => ({ ...row, status: "paid" }))); }
    catch (e) { setError(e instanceof Error ? e.message : "Your commission ledger could not be loaded."); }
    finally { setLoading(false); }
  }, [search]);
  useEffect(() => { void load(); }, [load]);
  return <main className="workspace-page rep-commissions-page"><header className="handover-page-heading"><div><p className="eyebrow">REPRESENTATIVE WORKSPACE</p><h2>My commission ledger</h2><p>Entries begin after finalized handover. Payouts are recorded manually by management; no money transfer is initiated here.</p></div></header>
    {error && <p className="reservation-feedback is-error" role="alert">{error}</p>}
    <section className="reservation-detail rep-paid-leaderboard"><p className="eyebrow">PAID COMMISSIONS · PRIVATE TO YOUR ACCOUNT</p><h3>My paid leaderboard total</h3><p>Only paid, non-reversed entries count.</p>{paidLeaderboardRows(paidSummary).map((row) => <div className="rep-paid-total" key={row.rep_name}><strong>{money(row.paid_total_lkr)}</strong><span>{row.paid_entries} paid {row.paid_entries === 1 ? "entry" : "entries"}</span></div>)}{!paidLeaderboardRows(paidSummary).length && <p>No paid commission entries yet.</p>}</section>
    <div className="reservation-toolbar"><label>Search<input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Sale, handover, or vehicle"/></label><span>{items.length} entries</span></div>
    <section className="reservation-workspace"><div className="reservation-table-wrap">{loading ? <p className="public-state">Loading your ledger…</p> : items.length === 0 ? <div className="reservation-empty"><h3>No eligible commission entries</h3><p>A confirmed sale alone does not qualify. An entry will appear after its handover is finalized and your Rep profile is assigned to the sale.</p></div> : <table className="reservation-table"><thead><tr><th>Sale / handover</th><th>Finalized</th><th>Selling price</th><th>Rate</th><th>Commission</th><th>Status / payout</th></tr></thead><tbody>{items.map((entry) => <tr key={`${entry.sale_reference}-${entry.handover_reference}`}><td><strong>{entry.sale_reference}</strong><small>{entry.vehicle_reference} · {entry.handover_reference}</small></td><td>{date(entry.finalized_at)}</td><td>{money(entry.sale_price_lkr)}</td><td>{entry.commission_rate_percent === null ? "Rate unavailable" : `${entry.commission_rate_percent}%`}</td><td>{entry.commission_amount_lkr === null ? "Not calculated" : money(entry.commission_amount_lkr)}</td><td><span className={`reservation-status is-${entry.status}`}>{entry.status}</span>{entry.status === "paid" && <small>{entry.payout_reference} · {date(entry.payout_date)} · {money(entry.payout_amount_lkr)}</small>}</td></tr>)}</tbody></table>}</div></section>
  </main>;
}
