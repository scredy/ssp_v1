"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/car-api";

type Bracket = { minimum_lkr: string; maximum_lkr: string | null; percentage: string; effective_date: string; active: boolean };
type Rule = { key: string; value: Bracket[]; updated_at: string };
type PolicyChange = { actor: string | null; created_at: string; previous: Bracket[] | null; current: Bracket[] };
type CurrentUser = { role: string };

const blankBracket = (): Bracket => ({ minimum_lkr: "", maximum_lkr: null, percentage: "", effective_date: "", active: true });
const amount = (value: string | null) => value === null || value === "" ? "No upper limit" : new Intl.NumberFormat("en-LK", { style: "currency", currency: "LKR", maximumFractionDigits: 2 }).format(Number(value));
const dateLabel = (value: string) => new Intl.DateTimeFormat("en-LK", { dateStyle: "medium", timeZone: "Asia/Colombo" }).format(new Date(`${value}T00:00:00`));
const timestamp = (value: string) => new Intl.DateTimeFormat("en-LK", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Colombo" }).format(new Date(value));

function validate(rows: Bracket[]) {
  if (!rows.length) return "Add at least one bracket to the policy schedule.";
  for (let index = 0; index < rows.length; index++) {
    const row = rows[index];
    if (!row.minimum_lkr.trim() || !row.percentage.trim() || !row.effective_date) return `Bracket ${index + 1}: minimum value, percentage, and effective date are required.`;
    const minimum = Number(row.minimum_lkr);
    const maximum = row.maximum_lkr === null || row.maximum_lkr === "" ? null : Number(row.maximum_lkr);
    const percentage = Number(row.percentage);
    if (!Number.isFinite(minimum) || minimum < 0 || (maximum !== null && (!Number.isFinite(maximum) || maximum <= minimum))) return `Bracket ${index + 1}: enter a non-negative minimum and a maximum greater than the minimum, or leave maximum blank for no upper limit.`;
    if (!Number.isFinite(percentage) || percentage <= 0 || percentage > 100) return `Bracket ${index + 1}: percentage must be above 0 and at most 100.`;
    if (Number.isNaN(Date.parse(`${row.effective_date}T00:00:00`))) return `Bracket ${index + 1}: enter a valid effective date.`;
  }
  const active = rows.filter((row) => row.active).map((row) => ({ ...row, low: Number(row.minimum_lkr), high: row.maximum_lkr ? Number(row.maximum_lkr) : Infinity }));
  for (let index = 0; index < active.length; index++) {
    for (const next of active.slice(index + 1)) {
      if (active[index].effective_date === next.effective_date && active[index].low < next.high && next.low < active[index].high) {
        return `Active brackets ${index + 1} and ${active.indexOf(next) + 1} overlap on ${active[index].effective_date}.`;
      }
    }
  }
  return "";
}

export default function CommissionPolicy() {
  const [rows, setRows] = useState<Bracket[]>([]);
  const [changes, setChanges] = useState<PolicyChange[]>([]);
  const [canManage, setCanManage] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [rules, history, user] = await Promise.all([
        api<Rule[]>("/api/commission-rules/"),
        api<PolicyChange[]>("/api/commission-rules/?history=1"),
        api<CurrentUser>("/api/auth/me/"),
      ]);
      const schedule = rules.find((rule) => rule.key === "brackets")?.value ?? [];
      setRows(schedule.map((row) => ({ ...row, maximum_lkr: row.maximum_lkr ?? "" })));
      setChanges(history);
      setCanManage(user.role === "ceo");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Commission policy could not be loaded.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const byDate = useMemo(() => {
    const groups = new Map<string, Bracket[]>();
    for (const row of rows) if (row.active) groups.set(row.effective_date, [...(groups.get(row.effective_date) ?? []), row]);
    return [...groups.entries()].sort(([a], [b]) => b.localeCompare(a));
  }, [rows]);
  const todayParts = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: "Asia/Colombo" }).formatToParts(new Date());
  const today = `${todayParts.find((part) => part.type === "year")?.value}-${todayParts.find((part) => part.type === "month")?.value}-${todayParts.find((part) => part.type === "day")?.value}`;
  const currentDate = byDate.find(([effective]) => effective <= today)?.[0];

  function changeRow(index: number, field: keyof Bracket, value: string | boolean) {
    setRows((current) => current.map((row, i) => i === index ? { ...row, [field]: value } : row));
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(""); setNotice("");
    const validationError = validate(rows);
    if (validationError) { setError(validationError); return; }
    setSaving(true);
    try {
      const payload = rows.map((row) => ({ ...row, maximum_lkr: row.maximum_lkr || null }));
      await api("/api/commission-rules/brackets/", { method: "PUT", body: JSON.stringify(payload) });
      setNotice("Commission policy saved. The change has been recorded in policy history.");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Commission policy could not be saved.");
    } finally { setSaving(false); }
  }

  return <main className="workspace-page commission-policy-page">
    <header className="handover-page-heading"><div><p className="eyebrow">LEADERSHIP · COMMISSION POLICY</p><h2>Vehicle selling-value brackets</h2><p>One effective-dated rate schedule applies uniformly to all eligible employees.</p></div></header>
    <p className="commission-policy-rule">Commission eligibility begins only after a vehicle handover is finalized. This screen manages rates only; it does not assign recipients, calculate earlier sales, or provide payout actions.</p>
    {error && <p className="state-card state-error" role="alert">{error}</p>}
    {notice && <p className="commission-policy-notice" role="status">{notice}</p>}
    {loading ? <p className="public-state">Loading commission policy…</p> : <>
      <section className="reservation-workspace commission-policy-overview">
        <article className="reservation-detail"><p className="eyebrow">EFFECTIVE POLICY</p><h3>{currentDate ? `Effective from ${dateLabel(currentDate)}` : "No active policy in effect"}</h3>{currentDate ? <BracketTable rows={byDate.find(([date]) => date === currentDate)?.[1] ?? []} /> : <p>No active bracket schedule has an effective date on or before today.</p>}</article>
        <article className="reservation-detail"><p className="eyebrow">POLICY SCHEDULE</p><h3>Effective dates</h3>{byDate.length ? <ul className="commission-date-list">{byDate.map(([date, brackets]) => <li key={date}><strong>{dateLabel(date)}</strong><span>{date > today ? "Scheduled" : date === currentDate ? "Current" : "Earlier"} · {brackets.length} active {brackets.length === 1 ? "bracket" : "brackets"}</span></li>)}</ul> : <p>No active brackets are configured.</p>}</article>
      </section>

      <section className="reservation-workspace commission-history-section"><div className="reservation-detail"><p className="eyebrow">AUDIT TRAIL</p><h3>Policy-change history</h3>{changes.length ? <ol className="commission-history-list">{changes.map((change, index) => <li key={`${change.created_at}-${index}`}><div><strong>{timestamp(change.created_at)}</strong><span>Changed by {change.actor ?? "Former account"}</span></div><details><summary>View before and after schedules</summary><h4>Previous policy</h4>{change.previous === null ? <p>No earlier policy.</p> : <BracketTable rows={change.previous} />}<h4>Saved policy</h4><BracketTable rows={change.current} /></details></li>)}</ol> : <p>No policy changes have been recorded yet.</p>}</div></section>

      <form className="reservation-form commission-editor" onSubmit={save}>
        <div className="reservation-form-heading"><div><p className="eyebrow">{canManage ? "CEO POLICY CONTROLS" : "READ ONLY"}</p><h2>{canManage ? "Edit bracket schedule" : "Bracket schedule"}</h2></div>{canManage && <button type="button" className="primary-button" onClick={() => setRows((current) => [...current, blankBracket()])}>Add bracket</button>}</div>
        <p className="commission-policy-rule">Enter boundaries as LKR. Brackets include the minimum and exclude the maximum; leave the maximum blank for no upper limit. Keep historical effective dates when adding a new schedule date.</p>
        {!rows.length && <p className="reservation-empty">No brackets configured yet.{canManage ? " Add a bracket to create the first policy." : ""}</p>}
        {rows.map((row, index) => <fieldset className="commission-bracket-editor" key={index} disabled={!canManage || saving}><legend>Bracket {index + 1}</legend><div className="reservation-form-grid">
          <label>Minimum selling value (LKR) *<input required type="number" min="0" step="0.01" value={row.minimum_lkr} onChange={(event) => changeRow(index, "minimum_lkr", event.target.value)} /></label>
          <label>Maximum selling value (LKR)<input type="number" min="0.01" step="0.01" value={row.maximum_lkr ?? ""} onChange={(event) => changeRow(index, "maximum_lkr", event.target.value)} placeholder="No upper limit" /></label>
          <label>Commission percentage *<input required type="number" min="0.001" max="100" step="0.001" value={row.percentage} onChange={(event) => changeRow(index, "percentage", event.target.value)} /></label>
          <label>Effective date *<input required type="date" value={row.effective_date} onChange={(event) => changeRow(index, "effective_date", event.target.value)} /></label>
          <label className="commission-active-toggle"><input type="checkbox" checked={row.active} onChange={(event) => changeRow(index, "active", event.target.checked)} /> Active bracket</label>
          {canManage && <button type="button" className="inventory-secondary commission-remove" disabled={saving} onClick={() => setRows((current) => current.filter((_, i) => i !== index))}>Remove bracket</button>}
        </div></fieldset>)}
        {canManage ? <button className="primary-button" disabled={saving || loading}>{saving ? "Saving policy…" : "Save commission policy"}</button> : <p className="reservation-hint">MD/Manager can review this policy but cannot edit it. The server enforces this permission.</p>}
      </form>
    </>}
  </main>;
}

function BracketTable({ rows }: { rows: Bracket[] }) {
  return rows.length ? <div className="reservation-table-wrap"><table className="reservation-table commission-bracket-table"><thead><tr><th>Selling-value range</th><th>Rate</th><th>Effective date</th><th>Status</th></tr></thead><tbody>{rows.map((row, index) => <tr key={`${row.effective_date}-${row.minimum_lkr}-${index}`}><td>{amount(row.minimum_lkr)} – {amount(row.maximum_lkr)}</td><td>{row.percentage}%</td><td>{row.effective_date ? dateLabel(row.effective_date) : "Date missing"}</td><td>{row.active ? "Active" : "Inactive"}</td></tr>)}</tbody></table></div> : <p>No brackets in this policy version.</p>;
}
