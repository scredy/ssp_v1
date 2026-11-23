"use client";

import Link from "next/link";
import { BrandLogo } from "@/components/public-site";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/car-api";

type Account = { id: number; username: string; first_name: string; last_name: string; email: string; phone: string | null; role: string; account_type: "internal" | "external"; is_active: boolean };
type AuditEvent = { action: string; actor: string | null; subject: string; created_at: string };
type User = { username: string; first_name: string; last_name: string; role: string; account_type: string };

const roles = ["admin", "ceo", "manager", "staff", "rep"];
const roleLabels: Record<string, string> = { admin: "Admin", ceo: "CEO", manager: "MD/Manager", staff: "Staff", rep: "Rep" };
const dateTime = (value: string) => new Intl.DateTimeFormat("en-LK", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Colombo" }).format(new Date(value));
const actionName = (value: string) => value.split(/[._]/).filter(Boolean).map((part) => part[0].toUpperCase() + part.slice(1)).join(" ");

export default function AdminDashboard({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([api<Account[]>("/api/accounts/"), api<AuditEvent[]>("/api/activity/recent/")])
      .then(([accountData, activityData]) => {
        if (active) { setAccounts(accountData); setEvents(activityData); }
      })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : "Unable to load Admin overview."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const roleCounts = useMemo(() => Object.fromEntries(roles.map((role) => [role, accounts.filter((account) => account.role === role).length])), [accounts]);
  const activeCount = accounts.filter((account) => account.is_active).length;

  return <div className="admin-shell">
    <aside className="admin-sidebar">
      <BrandLogo href="/staff" className="admin-sidebar-logo" priority />
      <p className="admin-nav-label">ADMIN</p>
      <nav aria-label="Admin navigation">
        <Link className="admin-nav-link is-current" href="/staff">Overview</Link>
        <Link className="admin-nav-link" href="/staff/accounts">Accounts</Link>
        <Link className="admin-nav-link" href="/staff/activity">Activity history</Link>
      </nav>
      <div className="admin-sidebar-user"><span className="admin-avatar">{(user.first_name || user.username).slice(0, 1).toUpperCase()}</span><div><strong>{[user.first_name, user.last_name].filter(Boolean).join(" ") || user.username}</strong><small>Administrator</small></div></div>
    </aside>
    <main className="admin-main">
      <header className="admin-topbar"><div><p className="admin-kicker">ACCOUNT ADMINISTRATION</p><h1>Account overview</h1></div><div className="admin-topbar-actions"><BrandLogo className="admin-header-logo" /><button className="admin-button admin-button-secondary" onClick={onSignOut}>Sign out</button></div></header>
      {error && <div className="admin-alert" role="alert">{error} <button className="admin-link-button" onClick={() => location.reload()}>Reload overview</button></div>}
      {loading ? <p className="admin-state" role="status">Loading account data…</p> : <>
        <section className="admin-metrics" aria-label="Account summary">
          <article><span>Total accounts</span><strong>{accounts.length}</strong></article>
          <article><span>Active</span><strong>{activeCount}</strong></article>
          <article><span>Inactive</span><strong>{accounts.length - activeCount}</strong></article>
          <article><span>Internal</span><strong>{accounts.filter((account) => account.account_type === "internal").length}</strong></article>
          <article><span>External</span><strong>{accounts.filter((account) => account.account_type === "external").length}</strong></article>
        </section>
        <div className="admin-overview-grid">
          <section className="admin-panel"><div className="admin-panel-heading"><div><p className="admin-kicker">DISTRIBUTION</p><h2>Accounts by role</h2></div><Link className="admin-text-link" href="/staff/accounts">Manage accounts <span aria-hidden="true">→</span></Link></div>
            <div className="role-counts">{roles.map((role) => <div key={role}><span>{roleLabels[role]}</span><strong>{roleCounts[role]}</strong></div>)}</div>
          </section>
          <section className="admin-panel admin-quick-links"><p className="admin-kicker">SHORTCUTS</p><h2>Administration</h2><Link href="/staff/accounts">Manage accounts <span aria-hidden="true">→</span></Link><Link href="/staff/activity">Review activity history <span aria-hidden="true">→</span></Link></section>
        </div>
        <section className="admin-panel admin-recent"><div className="admin-panel-heading"><div><p className="admin-kicker">LATEST EVENTS</p><h2>Recent account activity</h2></div><Link className="admin-text-link" href="/staff/activity">View all activity <span aria-hidden="true">→</span></Link></div>
          {events.length ? <div className="admin-event-list">{events.slice(0, 6).map((event, index) => <article className="admin-event" key={`${event.created_at}-${event.action}-${index}`}><div><strong>{actionName(event.action)}</strong><span>{event.actor || "System"}{event.subject ? ` · ${event.subject}` : ""}</span></div><time dateTime={event.created_at}>{dateTime(event.created_at)}</time></article>)}</div> : <p className="admin-state">No recent activity is available.</p>}
        </section>
      </>}
    </main>
  </div>;
}
