"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useStaffSession } from "@/components/staff-shell";
import { BrandLogo } from "@/components/public-site";
import { api, User } from "@/lib/car-api";

type CountRow = { date: string; count: number };
type CompanySummary = {
  sales: { draft_count: number; confirmed_count: number; confirmed_by_day: CountRow[] };
  inventory: Record<string, number>;
  reservations: { active_count: number; released_count: number };
  enquiries: { pending_count: number; appointment_count: number };
  quotations: Record<string, number>;
  handovers: Record<string, number>;
  imports: Record<string, number>;

  pending_bl_approvals?: number;
};
type Notice = { id: number; title: string; message: string; target_url: string; created_at: string };
type Account = { id: number; username: string; first_name: string; last_name: string; role: string; account_type: string; is_active: boolean };
type AuditEvent = { action: string; actor: string | null; subject: string; created_at: string };
type RepSummary = { profile_linked: boolean; draft_sales: number; confirmed_sales: number; handed_over_sales: number; pending_commissions: number; pending_commission_lkr: string; paid_commissions: number; paid_commission_lkr: string; unrated_commissions: number };
type RepProfile = { reference: string; full_name: string; email: string; phone: string | null; business_status: "active" | "inactive"; system_account_active: boolean };
type DashboardData = { company?: CompanySummary; notices: Notice[]; accounts?: Account[]; events?: AuditEvent[]; rep?: RepSummary; profile?: RepProfile | null; error: string; activityError: boolean };

const roleCopy: Record<string, { title: string; subtitle: string; eyebrow: string }> = {
  staff: { title: "Operations Dashboard", subtitle: "Sales, handovers, inventory and customer operations at a glance.", eyebrow: "STAFF WORKSPACE" },
  manager: { title: "Management Dashboard", subtitle: "Review sales, approvals and the operational work moving through your team.", eyebrow: "MD / MANAGER WORKSPACE" },
  ceo: { title: "Executive Dashboard", subtitle: "Business performance, financial oversight and strategic operations.", eyebrow: "EXECUTIVE WORKSPACE" },
  rep: { title: "Representative Dashboard", subtitle: "Track your assigned sales and commission entries in one place.", eyebrow: "REPRESENTATIVE WORKSPACE" },
  admin: { title: "Administration Dashboard", subtitle: "Monitor account access and recent administrative activity.", eyebrow: "ADMINISTRATION WORKSPACE" },
};

const roleLinks: Record<string, { title: string; description: string; href: string; icon: string }[]> = {
  staff: [
    { title: "Inventory", description: "Manage vehicles in stock", href: "/staff/inventory", icon: "car" },
    { title: "Reservations", description: "Manage vehicle holds", href: "/staff/reservations", icon: "calendar" },
    { title: "Handovers", description: "Prepare confirmed sales for delivery", href: "/staff/handovers", icon: "handover" },
    { title: "Imports", description: "Manage import records", href: "/staff/imports", icon: "box" },
    { title: "Quotations", description: "Create and manage quotations", href: "/staff/quotations", icon: "document" },
    { title: "Enquiries", description: "Review enquiries and appointments", href: "/staff/enquiries", icon: "chat" },
    { title: "Customers", description: "Manage customer directory", href: "/staff/customers", icon: "people" },
    { title: "Sales Summary", description: "View authorized sales totals", href: "/staff/sales-summary", icon: "chart" },
  ],
  manager: [
    { title: "Sales", description: "Create sales and manage payments", href: "/staff/sales", icon: "tag" },
    { title: "Payments", description: "Record and review payments", href: "/staff/payments", icon: "payment" },
    { title: "Handovers", description: "Review and finalize deliveries", href: "/staff/handovers", icon: "handover" },
    { title: "Inventory", description: "Review available vehicle stock", href: "/staff/inventory", icon: "car" },
    { title: "Quotations", description: "Manage customer quotations", href: "/staff/quotations", icon: "document" },
    { title: "Reservations", description: "Review vehicle reservations", href: "/staff/reservations", icon: "calendar" },
    { title: "Representatives", description: "Manage representative profiles", href: "/staff/reps", icon: "people" },
    { title: "Enquiries", description: "Review requests and schedules", href: "/staff/enquiries", icon: "chat" },
    { title: "Customers", description: "Authorized customer directory", href: "/staff/customers", icon: "people" },
    { title: "Commission Policy", description: "Review active commission rules", href: "/staff/commission-rules", icon: "chart" },
  ],
  ceo: [
    { title: "Sales", description: "Review confirmed transactions", href: "/staff/sales", icon: "tag" },
    { title: "Payments", description: "Manage confirmed payments and balances", href: "/staff/payments", icon: "payment" },
    { title: "Handovers", description: "Review vehicle deliveries", href: "/staff/handovers", icon: "handover" },
    { title: "BL Requests", description: "Review and decide approvals", href: "/staff/bl-requests", icon: "document" },
    { title: "Commission Policy", description: "Manage commission rules", href: "/staff/commission-rules", icon: "chart" },
    { title: "Quotations", description: "Review issued quotations", href: "/staff/quotations", icon: "document" },
    { title: "Imports", description: "Manage vehicle imports", href: "/staff/imports", icon: "box" },
    { title: "Inventory", description: "Review vehicle stock", href: "/staff/inventory", icon: "car" },
    { title: "Reservations", description: "Review vehicle reservations", href: "/staff/reservations", icon: "calendar" },
    { title: "Representatives", description: "Review linked profiles", href: "/staff/reps", icon: "people" },
    { title: "Enquiries", description: "Review requests and schedules", href: "/staff/enquiries", icon: "chat" },
    { title: "Leadership Oversight", description: "Review MD / Manager activity", href: "/staff/oversight/managers", icon: "chart" },
  ],
  rep: [
    { title: "My Sales", description: "Review your assigned sale records", href: "/staff/my-sales", icon: "tag" },
    { title: "My Commission Ledger", description: "Review your eligible entries and payouts", href: "/staff/my-commissions", icon: "chart" },
  ],
  admin: [
    { title: "Accounts", description: "Manage internal and external access", href: "/staff/accounts", icon: "people" },
    { title: "Activity History", description: "Review administrative audit events", href: "/staff/activity", icon: "chart" },
  ],
};

const money = (value: string | number) => new Intl.NumberFormat("en-LK", { style: "currency", currency: "LKR", maximumFractionDigits: 0 }).format(Number(value || 0));
const number = (value: unknown) => typeof value === "number" ? value : 0;
const dateTime = (value: string) => new Intl.DateTimeFormat("en-LK", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Colombo" }).format(new Date(value));
const actionName = (value: string) => value.split(/[._]/).filter(Boolean).map((part) => part[0].toUpperCase() + part.slice(1)).join(" ");

function Icon({ name }: { name: string }) {
  const paths: Record<string, string> = {
    car: "M3 13l2-6h14l2 6v6h-3v-3H6v3H3zM5 13h14M7 16h.01M17 16h.01",
    calendar: "M5 4h14v17H5zM8 2v4M16 2v4M5 9h14M8 13h3M8 17h7",
    handover: "M4 5h16v15H4zM8 3v4M16 3v4M8 12l2.5 2.5L16 9",
    box: "M4 7l8-4 8 4v10l-8 4-8-4zM4 7l8 4 8-4M12 11v10M9 5l8 4",
    document: "M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h7",
    chat: "M4 4h16v13H9l-5 4zM8 9h8M8 13h5",
    people: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4 21v-1a8 8 0 0 1 16 0v1zM17 4a4 4 0 0 1 0 7",
    chart: "M4 19V5m0 14h16M7 15l4-4 3 2 5-6M16 7h3v3",
    tag: "M3 12V5h7l11 11-7 7zM7.5 8.5h.01",
    payment: "M3 6h18v13H3zM3 10h18M7 15h4",
    bell: "M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4",
    shield: "M12 3l8 3v5c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6zM9 12l2 2 4-4",
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d={paths[name] || paths.chart} /></svg>;
}

function Kpi({ label, value, detail, icon, accent = false }: { label: string; value: string | number; detail: string; icon: string; accent?: boolean }) {
  return <article className={`role-kpi${accent ? " is-accent" : ""}`}><span className="role-kpi-icon"><Icon name={icon} /></span><div><span className="role-kpi-label">{label}</span><strong>{value}</strong><small>{detail}</small></div></article>;
}

function Hero({ role }: { role: string }) {
  const copy = roleCopy[role] || roleCopy.staff;
  return <section className="role-dashboard-hero"><div className="role-dashboard-brand"><BrandLogo className="role-dashboard-logo" href="/staff" priority /><span aria-hidden="true" /></div><div className="role-dashboard-headline"><p>{copy.eyebrow}</p><h2>SSP MOTOR TRADING</h2><h3>{copy.title}</h3><span>{copy.subtitle}</span></div><div className="role-dashboard-hero-mark" aria-hidden="true">SSP<i /></div></section>;
}

function SalesChart({ rows }: { rows: CountRow[] }) {
  const points = useMemo(() => {
    const countByDay = new Map(rows.map((row) => [row.date, row.count]));
    const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Colombo", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
    const end = new Date(`${today}T00:00:00Z`);
    return Array.from({ length: 30 }, (_, index) => {
      const day = new Date(end); day.setUTCDate(day.getUTCDate() - (29 - index));
      const key = day.toISOString().slice(0, 10);
      return { key, count: countByDay.get(key) || 0, label: new Intl.DateTimeFormat("en-LK", { month: "short", day: "numeric", timeZone: "UTC" }).format(day) };
    });
  }, [rows]);
  const max = Math.max(1, ...points.map((point) => point.count));
  const coords = points.map((point, index) => ({ x: 12 + index * (596 / 29), y: 157 - (point.count / max) * 125 }));
  const polyline = coords.map((point) => `${point.x},${point.y}`).join(" ");
  const area = `12,157 ${polyline} 608,157`;
  const total = points.reduce((sum, point) => sum + point.count, 0);
  return <section className="role-panel role-chart-panel"><div className="role-panel-heading"><div><p className="role-eyebrow">SALES ANALYTICS</p><h3>Sales Performance</h3><span>Confirmed sales over the last 30 days</span></div><Link href="/staff/sales-summary">View summary <b aria-hidden="true">→</b></Link></div>
    {total ? <><svg className="role-sales-chart" viewBox="0 0 620 195" role="img" aria-label={`Confirmed sales over the last 30 days. ${total} confirmed ${total === 1 ? "sale" : "sales"} across the displayed period.`} preserveAspectRatio="none"><defs><linearGradient id="salesArea" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#d71920" stopOpacity=".28"/><stop offset="1" stopColor="#d71920" stopOpacity=".02"/></linearGradient></defs><path d="M12 32H608M12 74H608M12 116H608M12 157H608" className="role-chart-gridline"/><polygon points={area} fill="url(#salesArea)"/><polyline points={polyline} className="role-chart-line"/>{coords.map((point, index) => points[index].count > 0 ? <circle key={points[index].key} cx={point.x} cy={point.y} r="3.6" className="role-chart-point"><title>{points[index].label}: {points[index].count} confirmed</title></circle> : null)}</svg><div className="role-chart-axis"><span>{points[0]?.label}</span><span>{points[14]?.label}</span><span>{points[29]?.label}</span></div></> : <div className="role-empty-inline"><span className="role-empty-icon"><Icon name="chart"/></span><strong>No confirmed sales in this period</strong><span>New confirmed records will appear here.</span></div>}
  </section>;
}

const handoverStatus: [string, string, string][] = [
  ["preparing", "Preparing", "#ed9b16"], ["pending_md_review", "Pending MD Review", "#1476bd"],
  ["pending_ceo_approval", "Pending CEO Approval", "#c8212b"], ["ceo_approved", "CEO Approved", "#6845b8"], ["finalized", "Finalized", "#18a64a"],
];

function HandoverChart({ statuses }: { statuses: Record<string, number> }) {
  const total = handoverStatus.reduce((sum, [key]) => sum + number(statuses[key]), 0);
  let consumed = 0;
  const slices = handoverStatus.map(([key, , color]) => {
    const count = number(statuses[key]); const start = consumed;
    consumed += total ? (count / total) * 100 : 0;
    return `${color} ${start}% ${consumed}%`;
  });
  return <section className="role-panel role-handover-panel"><div className="role-panel-heading"><div><p className="role-eyebrow">DELIVERY OPERATIONS</p><h3>Handovers Overview</h3><span>Current workflow status</span></div><Link href="/staff/handovers">Open handovers <b aria-hidden="true">→</b></Link></div>
    {total ? <div className="role-handover-summary"><div className="role-donut-wrap"><div className="role-donut" style={{ background: `conic-gradient(${slices.join(",")})` }}><div><strong>{total}</strong><span>Total</span></div></div></div><ul className="role-status-legend">{handoverStatus.map(([key, label, color]) => { const count = number(statuses[key]); return <li key={key}><i style={{ backgroundColor: color }}/><span>{label}</span><strong>{count}</strong></li>; })}</ul></div> : <div className="role-empty-inline"><span className="role-empty-icon"><Icon name="handover"/></span><strong>No handovers yet</strong><span>Prepared handovers will be summarized here.</span></div>}
  </section>;
}

function RecentActivity({ notices, error }: { notices: Notice[]; error: boolean }) {
  return <section className="role-panel role-activity-panel"><div className="role-panel-heading"><div><p className="role-eyebrow">YOUR WORK QUEUE</p><h3>Recent Activity</h3><span>Updates assigned to your account</span></div><Link href="/staff/notifications">View all <b aria-hidden="true">→</b></Link></div>
    {notices.length ? <div className="role-activity-list">{notices.slice(0, 5).map((notice) => { const route = notice.target_url.startsWith("/staff") ? notice.target_url : "/staff/notifications"; const icon = notice.title.toLowerCase().includes("payment") ? "payment" : notice.title.toLowerCase().includes("handover") ? "handover" : notice.title.toLowerCase().includes("appointment") ? "calendar" : notice.title.toLowerCase().includes("approval") ? "document" : "bell"; return <article key={notice.id}><span className="role-activity-icon"><Icon name={icon}/></span><div><strong>{notice.title}</strong><p>{notice.message}</p><Link href={route}>Open related work <b aria-hidden="true">→</b></Link></div><time dateTime={notice.created_at}>{new Intl.DateTimeFormat("en-LK", { timeStyle: "short", timeZone: "Asia/Colombo" }).format(new Date(notice.created_at))}</time></article>; })}</div> : <div className="role-empty-inline"><span className="role-empty-icon"><Icon name="bell"/></span><strong>{error ? "Activity is unavailable" : "No recent activity"}</strong><span>{error ? "You can open notifications and retry later." : "New updates assigned to you will appear here."}</span></div>}
  </section>;
}

function ActionRequired({ role, data }: { role: string; data: DashboardData }) {
  const company = data.company;
  if (!company || (role !== "manager" && role !== "ceo")) return null;
  const items = role === "ceo" ? [
    { label: "Handovers pending CEO approval", count: number(company.handovers.pending_ceo_approval), href: "/staff/handovers" },
    { label: "BL requests awaiting action", count: number(company.pending_bl_approvals), href: "/staff/bl-requests" },
  ] : [
    { label: "Handovers awaiting MD review", count: number(company.handovers.pending_md_review), href: "/staff/handovers" },
    { label: "CEO-approved handovers awaiting finalization", count: number(company.handovers.ceo_approved), href: "/staff/handovers" },
  ];
  return <section className="role-action-required"><div><p className="role-eyebrow">PRIORITY QUEUE</p><h3>Action Required</h3><span>Current workflow counts</span></div><div>{items.map((item) => <Link key={item.label} href={item.href}><span>{item.label}</span><strong>{item.count}</strong><b aria-hidden="true">→</b></Link>)}</div></section>;
}

function QuickLinks({ role }: { role: string }) {
  return <section className="role-quick-section"><div className="role-section-heading"><div><p className="role-eyebrow">WORKSPACE SHORTCUTS</p><h3>Operations</h3><span>Access the workflows available to your account.</span></div></div><div className="role-quick-grid">{(roleLinks[role] || []).map((item) => <Link className="role-quick-card" key={item.href} href={item.href}><span className="role-quick-icon"><Icon name={item.icon}/></span><strong>{item.title}</strong><span>{item.description}</span><b>Open {item.title.toLowerCase()} <i aria-hidden="true">→</i></b></Link>)}</div></section>;
}

function AdminContent({ data }: { data: DashboardData }) {
  const accounts = data.accounts || [];
  const counts = ["admin", "ceo", "manager", "staff", "rep"].map((role) => ({ role, count: accounts.filter((account) => account.role === role).length }));
  const active = accounts.filter((account) => account.is_active).length;
  const labels: Record<string, string> = { admin: "Admin", ceo: "CEO", manager: "MD / Manager", staff: "Staff", rep: "Representative" };
  return <><div className="role-kpi-grid role-kpi-grid-four"><Kpi label="Total accounts" value={accounts.length} detail="Accounts in the system" icon="people" accent/><Kpi label="Active accounts" value={active} detail="Currently enabled" icon="shield"/><Kpi label="Inactive accounts" value={accounts.length - active} detail="Access disabled" icon="people"/><Kpi label="Internal accounts" value={accounts.filter((account) => account.account_type === "internal").length} detail={`${accounts.filter((account) => account.account_type === "external").length} external accounts`} icon="tag"/></div><section className="role-admin-distribution"><div className="role-section-heading"><div><p className="role-eyebrow">ACCOUNT ACCESS</p><h3>Accounts by role</h3><span>Distribution from the account directory.</span></div></div><div>{counts.map((entry) => <div key={entry.role}><span>{labels[entry.role]}</span><i><b style={{ width: `${accounts.length ? Math.max(2, (entry.count / accounts.length) * 100) : 0}%` }}/></i><strong>{entry.count}</strong></div>)}</div></section><section className="role-panel role-activity-panel"><div className="role-panel-heading"><div><p className="role-eyebrow">AUDIT TRAIL</p><h3>Recent Account Activity</h3><span>Latest administrative audit events</span></div><Link href="/staff/activity">View activity <b aria-hidden="true">→</b></Link></div>{data.events?.length ? <div className="role-activity-list">{data.events.slice(0, 6).map((event, index) => <article key={`${event.created_at}-${event.action}-${index}`}><span className="role-activity-icon"><Icon name="chart"/></span><div><strong>{actionName(event.action)}</strong><p>{event.actor || "System"}{event.subject ? ` · ${event.subject}` : ""}</p></div><time dateTime={event.created_at}>{dateTime(event.created_at)}</time></article>)}</div> : <div className="role-empty-inline"><strong>{data.activityError ? "Activity is unavailable" : "No recent activity"}</strong><span>Administrative events will appear here.</span></div>}</section><QuickLinks role="admin"/></>;
}

function RepContent({ data }: { data: DashboardData }) {
  const rep = data.rep; const profile = data.profile;
  return <><div className="role-rep-profile"><div><p className="role-eyebrow">MY REPRESENTATIVE PROFILE</p><h3>{profile?.full_name || "Representative account"}</h3><span>{profile ? `${profile.reference} · ${profile.business_status} business status` : rep?.profile_linked ? "Profile linked" : "Profile not linked"}</span></div>{profile && <span className={`role-profile-state is-${profile.business_status}`}>{profile.business_status}</span>}</div>{profile && !profile.system_account_active && <p className="role-warning" role="status">Your account is inactive. Contact the MD/Manager.</p>}{rep && !rep.profile_linked && <p className="role-warning" role="status">Your Rep account has not been linked to a representative profile. Contact the MD/Manager.</p>}<div className="role-kpi-grid role-kpi-grid-four"><Kpi label="Confirmed Sales" value={rep?.confirmed_sales ?? "—"} detail="Assigned to your profile" icon="tag" accent/><Kpi label="Draft Sales" value={rep?.draft_sales ?? "—"} detail="Assigned to you" icon="document"/><Kpi label="Handed Over" value={rep?.handed_over_sales ?? "—"} detail="Finalized handovers" icon="handover"/><Kpi label="Unpaid Commissions" value={rep?.pending_commissions ?? "—"} detail={rep ? `${money(rep.pending_commission_lkr)} pending or approved` : "Private to your account"} icon="payment"/></div><div className="role-rep-summary"><span>Paid commissions</span><strong>{rep ? money(rep.paid_commission_lkr) : "—"}</strong><small>{rep?.paid_commissions ?? 0} paid ledger entries · reversed entries excluded</small>{rep?.unrated_commissions ? <p>{rep.unrated_commissions} pending entr{rep.unrated_commissions === 1 ? "y has" : "ies have"} no matching active policy rate. No rate was assumed.</p> : null}</div><RecentActivity notices={data.notices} error={data.activityError}/><QuickLinks role="rep"/></>;
}

function CompanyContent({ role, data }: { role: string; data: DashboardData }) {
  const company = data.company;
  if (!company) return null;
  const handoverTotal = Object.values(company.handovers).reduce((sum, count) => sum + count, 0);
  const inventoryTotal = Object.values(company.inventory).reduce((sum, count) => sum + count, 0);
  const pendingOps = number(company.enquiries.pending_count) + number(company.handovers.ceo_approved);
  const pendingApprovals = number(company.handovers.pending_ceo_approval) + number(company.pending_bl_approvals);
  const primary = role === "staff" ? [
    ["Vehicles in Stock", inventoryTotal, `${number(company.inventory.available)} available · ${number(company.inventory.reserved)} reserved · ${number(company.inventory.sold)} sold`, "car"],
    ["Confirmed Sales", company.sales.confirmed_count, "Authorized transaction count", "tag"],
    ["Active Reservations", company.reservations.active_count, "Vehicle holds in progress", "calendar"],
    ["Handovers", handoverTotal, `${number(company.handovers.preparing)} preparing · ${number(company.handovers.pending_md_review) + number(company.handovers.pending_ceo_approval)} awaiting review · ${number(company.handovers.finalized)} finalized`, "handover"],
  ] : role === "ceo" ? [
    ["Confirmed Sales", company.sales.confirmed_count, "Recorded transactions", "tag"],
    ["Pending Approvals", pendingApprovals, `${number(company.handovers.pending_ceo_approval)} handovers · ${number(company.pending_bl_approvals)} BL requests`, "shield"],
    ["Vehicles in Stock", inventoryTotal, "Authorized inventory count", "car"],
    ["Handovers", handoverTotal, `${number(company.handovers.finalized)} finalized · ${number(company.handovers.pending_ceo_approval)} awaiting CEO approval`, "handover"],
  ] : [
    ["Confirmed Sales", company.sales.confirmed_count, "Recorded transactions", "tag"],
    ["Pending MD Reviews", number(company.handovers.pending_md_review), "Awaiting your handover review", "shield"],
    ["Active Reservations", company.reservations.active_count, "Vehicle holds in progress", "calendar"],
    ["Pending Operational Tasks", pendingOps, `${number(company.enquiries.pending_count)} enquiries · ${number(company.handovers.ceo_approved)} handovers to finalize`, "document"],
  ];
  return <><div className="role-kpi-grid role-kpi-grid-four">{primary.map(([label, value, detail, icon], index) => <Kpi key={String(label)} label={String(label)} value={value} detail={String(detail)} icon={String(icon)} accent={index === 0}/>)}</div><div className="role-secondary-stats" aria-label="Additional dashboard metrics">{role === "staff" ? <><article><span>Draft Sales</span><strong>{company.sales.draft_count}</strong><small>Awaiting authorized review</small></article><article><span>Pending Enquiries</span><strong>{company.enquiries.pending_count}</strong><small>{company.enquiries.appointment_count} appointment requests</small></article><article><span>Quotations</span><strong>{number(company.quotations.draft) + number(company.quotations.issued)}</strong><small>{number(company.quotations.draft)} drafts · {number(company.quotations.issued)} issued</small></article></> : <><article><span>Draft Sales</span><strong>{company.sales.draft_count}</strong><small>Awaiting authorized review</small></article><article><span>Pending Enquiries</span><strong>{company.enquiries.pending_count}</strong><small>New or contacted</small></article><article><span>Quotations</span><strong>{number(company.quotations.draft) + number(company.quotations.issued)}</strong><small>{number(company.quotations.draft)} drafts · {number(company.quotations.issued)} issued</small></article></>}</div><ActionRequired role={role} data={data}/><div className="role-analytics-grid"><SalesChart rows={company.sales.confirmed_by_day}/><HandoverChart statuses={company.handovers}/><RecentActivity notices={data.notices} error={data.activityError}/></div><QuickLinks role={role}/></>;
}

export default function RoleDashboard() {
  const user = useStaffSession();
  const [data, setData] = useState<DashboardData>({ notices: [], error: "", activityError: false });
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const load = useCallback(async () => {
    if (!user) return;
    setLoading(true); setData({ notices: [], error: "", activityError: false });
    const role = user.role;
    let result: DashboardData = { notices: [], error: "", activityError: false };
    try {
      if (["staff", "manager", "ceo"].includes(role)) {
        const [summary, notifications] = await Promise.allSettled([api<CompanySummary>("/api/staff/dashboard/summary/"), api<{ results: Notice[] }>("/api/notifications/?limit=5&offset=0")]);
        if (summary.status === "fulfilled") result.company = summary.value; else throw summary.reason;
        if (notifications.status === "fulfilled") result.notices = notifications.value.results; else result.activityError = true;
      } else if (role === "rep") {
        const [summary, profile, notifications] = await Promise.allSettled([api<RepSummary>("/api/rep/dashboard/"), api<{ profile: RepProfile | null }>("/api/representative/profile/"), api<{ results: Notice[] }>("/api/notifications/?limit=5&offset=0")]);
        if (summary.status === "fulfilled") result.rep = summary.value; else throw summary.reason;
        if (profile.status === "fulfilled") result.profile = profile.value.profile; else throw profile.reason;
        if (notifications.status === "fulfilled") result.notices = notifications.value.results; else result.activityError = true;
      } else {
        const [accounts, activity] = await Promise.allSettled([api<Account[]>("/api/accounts/"), api<AuditEvent[]>("/api/activity/recent/")]);
        if (accounts.status === "fulfilled") result.accounts = accounts.value; else throw accounts.reason;
        if (activity.status === "fulfilled") result.events = activity.value; else result.activityError = true;
      }
    } catch (error) { result.error = error instanceof Error ? error.message : "Dashboard data could not be loaded."; }
    setData(result); setLoading(false);
  }, [user]);
  useEffect(() => { void load(); }, [load, reload]);

  if (!user) return <div className="role-dashboard-skeleton" role="status">Loading your dashboard…</div>;
  const copy = roleCopy[user.role] || roleCopy.staff;
  const name = [user.first_name, user.last_name].filter(Boolean).join(" ") || user.username;
  return <main className="role-dashboard" aria-labelledby="role-dashboard-title">
    <div className="role-dashboard-welcome"><div><p className="role-eyebrow">{copy.eyebrow}</p><h1 id="role-dashboard-title">{copy.title}</h1><p>Welcome back, {name.split(" ")[0]}. Here is your authorized workspace at a glance.</p></div><span className="role-account-chip">{user.role === "rep" ? "Private representative account" : `${user.role === "admin" ? "Admin" : user.role === "ceo" ? "CEO" : user.role === "manager" ? "MD / Manager" : "Staff"} account`}</span></div>
    <Hero role={user.role}/>
    {data.error ? <div className="role-dashboard-error" role="alert"><div><strong>Dashboard data could not be loaded</strong><span>{data.error}</span></div><button type="button" onClick={() => setReload((value) => value + 1)}>Retry</button></div> : loading ? <div className="role-dashboard-skeleton" role="status">Loading live dashboard data…</div> : user.role === "admin" ? <AdminContent data={data}/> : user.role === "rep" ? <RepContent data={data}/> : <CompanyContent role={user.role} data={data}/>}
  </main>;
}
