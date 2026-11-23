"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/car-api";
import { BrandLogo } from "@/components/public-site";

type AuditEvent = {
  action: string; actor: string | null; actor_role: string | null; subject: string;
  created_at: string; details: Record<string, unknown>;
};
type AuditPage = { count: number; next: string | null; previous: string | null; results: AuditEvent[] };
type CurrentUser = { role: string };
type AuditFilters = { search: string; action: string; actor: string; role: string; date_from: string; date_to: string };

const roleNames: Record<string, string> = { admin: "Admin", ceo: "CEO", manager: "MD/Manager", staff: "Staff", rep: "Rep", system: "System" };
const actionName = (value: string) => value.split(/[._]/).filter(Boolean).map((part) => part[0].toUpperCase() + part.slice(1)).join(" ");
const emptyFilters: AuditFilters = { search: "", action: "", actor: "", role: "", date_from: "", date_to: "" };
const PAGE_SIZE = 25;

function formatSriLankaTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat("en-LK", {
    dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Colombo",
  }).format(date);
}

export default function AuditHistory({
  requiredRole, endpoint, title, description,
}: { requiredRole: "admin" | "ceo"; endpoint: string; title: string; description: string }) {
  const router = useRouter();
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [count, setCount] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState<AuditFilters>(emptyFilters);
  const [filters, setFilters] = useState<AuditFilters>(emptyFilters);

  const loadHistory = useCallback(async (nextOffset = 0) => {
    setLoading(true);
    setError("");
    const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(nextOffset) });
    Object.entries(filters).forEach(([key, value]) => { if (value) query.set(key, value); });
    try {
      const page = await api<AuditPage>(`${endpoint}?${query.toString()}`);
      setEvents(page.results);
      setCount(page.count);
      setOffset(nextOffset);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load audit history.");
    } finally { setLoading(false); }
  }, [endpoint, filters]);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const user = await api<CurrentUser>("/api/auth/me/");
        if (!active) return;
        if (user.role !== requiredRole) { setForbidden(true); return; }
        await loadHistory(0);
      } catch (cause) {
        if (!active) return;
        const message = cause instanceof Error ? cause.message : "Unable to check your session.";
        if (message.includes("(401)") || message.includes("(403)")) router.replace("/staff/login");
        else setError(message);
      } finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, [endpoint, requiredRole, router, loadHistory]);

  function updateDraft(field: keyof AuditFilters, value: string) {
    setDraft((current) => ({ ...current, [field]: value }));
  }
  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setOffset(0);
    setLoading(true);
    setFilters({ ...draft });
  }
  function clearFilters() {
    setDraft(emptyFilters);
    setFilters({ ...emptyFilters });
    setOffset(0);
    setLoading(true);
  }

  if (loading && events.length === 0 && !error) return <main className="workspace-page"><p className="state-card">Loading audit history…</p></main>;
  if (forbidden) return <main className="workspace-page"><Link className="text-link" href="/staff">← Staff workspace</Link><p className="state-card state-error" role="alert">Your role cannot view this audit history.</p></main>;

  const hasFilters = Object.values(filters).some(Boolean);
  const rangeStart = count === 0 ? 0 : offset + 1;
  const rangeEnd = Math.min(offset + events.length, count);
  const roleOptions = requiredRole === "ceo"
    ? [["manager", "MD/Manager"]]
    : [["admin", "Admin"], ["ceo", "CEO"], ["manager", "MD/Manager"], ["staff", "Staff"], ["rep", "Rep"], ["system", "System"]];

  return <main className={`workspace-page ${requiredRole === "admin" ? "admin-workspace" : ""}`}>
    <header className="site-header staff-brand-header"><BrandLogo href="/staff" className="staff-page-logo" priority /><span className="staff-brand-caption">{roleNames[requiredRole]} WORKSPACE</span><nav><Link href="/staff">Workspace</Link>{requiredRole === "admin" && <Link href="/staff/accounts">Accounts</Link>}</nav></header>
    <section className="workspace-hero"><p className="eyebrow">{requiredRole === "admin" ? "ACCOUNT ADMINISTRATION" : "LEADERSHIP OVERSIGHT"}</p><h1>{title}</h1><p>{description}</p></section>
    <p className="activity-limit">Search and filter the server-side audit history. Results are limited to {PAGE_SIZE} per page. Sensitive event details are omitted. Times use Sri Lanka time.</p>
    <form className="activity-filters audit-search-form" aria-label="Filter audit history" onSubmit={applyFilters}>
      <label>Search<input value={draft.search} onChange={(event) => updateDraft("search", event.target.value)} placeholder="Action, actor or record" maxLength={120} /></label>
      <label>Action<input value={draft.action} onChange={(event) => updateDraft("action", event.target.value)} placeholder="Exact action" maxLength={80} /></label>
      <label>Actor<input value={draft.actor} onChange={(event) => updateDraft("actor", event.target.value)} placeholder="Username contains…" maxLength={150} /></label>
      <label>Role<select value={draft.role} onChange={(event) => updateDraft("role", event.target.value)}><option value="">All permitted roles</option>{roleOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>From<input type="date" value={draft.date_from} onChange={(event) => updateDraft("date_from", event.target.value)} /></label>
      <label>To<input type="date" value={draft.date_to} onChange={(event) => updateDraft("date_to", event.target.value)} /></label>
      <div className="audit-filter-actions"><button className="primary-button" type="submit" disabled={loading}>{loading ? "Loading…" : "Apply filters"}</button><button className="quiet-button" type="button" disabled={loading || (!hasFilters && !Object.values(draft).some(Boolean))} onClick={clearFilters}>Clear</button></div>
    </form>
    {error ? <div className="state-card state-error" role="alert"><p>{error}</p><button className="quiet-button" onClick={() => void loadHistory(offset)}>Retry</button></div> : loading ? <p className="state-card" role="status">Loading audit history…</p> : count === 0 ? <p className="state-card">{hasFilters ? "No activity matches these filters." : "No audit activity is available."}</p> : <>
      <section className="audit-list" aria-label="Audit events" aria-live="polite">{events.map((event, index) => <article className="audit-row" key={`${event.created_at}-${event.action}-${index}`}>
        <div className="audit-event-heading"><span className="audit-action">{actionName(event.action)}</span><time dateTime={event.created_at}>{formatSriLankaTime(event.created_at)}</time></div>
        <p><span>Actor</span>{event.actor || "System"}</p>
        <p><span>Role</span>{roleNames[event.actor_role ?? "system"] ?? event.actor_role ?? "System"}</p>
        <p><span>Affected record</span>{event.subject || "—"}</p>
        {Object.keys(event.details).length > 0 && <div className="audit-safe-details">{Object.entries(event.details).map(([key, value]) => <p key={key}><span>{actionName(key)}</span>{typeof value === "object" && value !== null ? JSON.stringify(value) : String(value)}</p>)}</div>}
      </article>)}</section>
      <nav className="audit-pagination" aria-label="Audit history pages"><span>Showing {rangeStart}–{rangeEnd} of {count}</span><div><button className="quiet-button" disabled={loading || offset === 0} onClick={() => void loadHistory(Math.max(0, offset - PAGE_SIZE))}>Previous</button><button className="quiet-button" disabled={loading || offset + events.length >= count} onClick={() => void loadHistory(offset + PAGE_SIZE)}>Next</button></div></nav>
    </>}
  </main>;
}