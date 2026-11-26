"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/car-api";

type Sale = { reference: string; vehicle_reference: string; vehicle_name: string; customer_name: string; sale_type: string; agreed_price_lkr: string; sale_date: string; status: "draft" | "confirmed"; confirmed_at: string | null; handover_status: "preparing" | "pending_md_review" | "pending_ceo_approval" | "ceo_approved" | "finalized" | null; handover_finalized_at: string | null };
const money = (value: string | number) => new Intl.NumberFormat("en-LK", { style: "currency", currency: "LKR", maximumFractionDigits: 2 }).format(Number(value || 0));
const date = (value: string | null) => value ? new Intl.DateTimeFormat("en-LK", { dateStyle: "medium", timeZone: "Asia/Colombo" }).format(new Date(value)) : "—";

export default function RepSales() {
  const [items, setItems] = useState<Sale[]>([]);
  const [selected, setSelected] = useState<Sale | null>(null);
  const [search, setSearch] = useState("");
  const [state, setState] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const params = new URLSearchParams(); if (search.trim()) params.set("search", search.trim()); if (state) params.set("status", state); setItems(await api<Sale[]>(`/api/rep/sales/?${params}`)); }
    catch (e) { setError(e instanceof Error ? e.message : "Your sales could not be loaded."); }
    finally { setLoading(false); }
  }, [search, state]);
  useEffect(() => { void load(); }, [load]);
  async function openSale(reference: string) {
    setError("");
    try { setSelected(await api<Sale>(`/api/rep/sales/${encodeURIComponent(reference)}/`)); }
    catch (e) { setError(e instanceof Error ? e.message : "Sale detail could not be loaded."); }
  }

  return <main className="workspace-page rep-sales-page"><header className="handover-page-heading"><div><p className="eyebrow">REPRESENTATIVE WORKSPACE</p><h2>My sales</h2><p>Only sales explicitly assigned to your Rep account appear here.</p></div></header>
    {error && <p className="reservation-feedback is-error" role="alert">{error}</p>}
    <div className="reservation-toolbar"><label>Search<input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Sale, vehicle, or customer"/></label><label>Status<select value={state} onChange={(e) => setState(e.target.value)}><option value="">All statuses</option><option value="draft">Draft</option><option value="confirmed">Confirmed</option></select></label><span>{items.length} records</span></div>
    <section className="reservation-workspace"><div className="reservation-table-wrap">{loading ? <p className="public-state">Loading your sales…</p> : items.length === 0 ? <div className="reservation-empty"><h3>No assigned sales found</h3><p>{search || state ? "Try a different search or status." : "Ask the MD/Manager to assign your representative profile to a sale."}</p></div> : <table className="reservation-table"><thead><tr><th>Sale</th><th>Vehicle</th><th>Customer</th><th>Sale date</th><th>Price</th><th>Status</th></tr></thead><tbody>{items.map((sale) => <tr key={sale.reference} className={selected?.reference === sale.reference ? "is-selected" : ""}><td><button className="table-link-button" onClick={() => void openSale(sale.reference)}>{sale.reference}</button><small>{sale.sale_type}</small></td><td>{sale.vehicle_name}<small>{sale.vehicle_reference}</small></td><td>{sale.customer_name}</td><td>{date(sale.sale_date)}</td><td>{money(sale.agreed_price_lkr)}</td><td><span className={`reservation-status is-${sale.status}`}>{sale.status}</span></td></tr>)}</tbody></table>}</div>
      {selected && <aside className="reservation-detail"><div className="reservation-detail-heading"><div><p className="eyebrow">MY SALE DETAIL</p><h3>{selected.reference}</h3></div><button className="inventory-secondary" onClick={() => setSelected(null)} aria-label="Close sale details">×</button></div><span className={`reservation-status is-${selected.status}`}>{selected.status}</span><dl><div><dt>Vehicle</dt><dd>{selected.vehicle_name} · {selected.vehicle_reference}</dd></div><div><dt>Customer</dt><dd>{selected.customer_name}</dd></div><div><dt>Selling price</dt><dd>{money(selected.agreed_price_lkr)}</dd></div><div><dt>Sale date</dt><dd>{date(selected.sale_date)}</dd></div><div><dt>Confirmed</dt><dd>{date(selected.confirmed_at)}</dd></div><div><dt>Handover</dt><dd>{selected.handover_status?.replaceAll("_", " ") || "Not started"}</dd></div><div><dt>Handover finalized</dt><dd>{date(selected.handover_finalized_at)}</dd></div></dl><p className="reservation-hint">Commission eligibility begins only after MD/Manager finalizes the handover. See your commission ledger for eligible entries.</p></aside>}
    </section>
  </main>;
}
