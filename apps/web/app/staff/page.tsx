"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import AdminDashboard from "@/components/admin-dashboard";
import { BrandLogo } from "@/components/public-site";
import RepresentativeDashboard from "@/components/representative-dashboard";
import { API } from "@/lib/car-api";
type User = { username: string; first_name: string; last_name: string; role: string; account_type: string };

const roleLabels: Record<string, string> = { admin: "Admin", ceo: "CEO", manager: "MD/Manager", staff: "Staff", rep: "Rep" };
const navigation: Record<string, { label: string; detail: string; href?: string }[]> = {
  admin: [{ label: "Accounts", detail: "Manage internal and external accounts", href: "/staff/accounts" }, { label: "Activity", detail: "Recent account activity and audit history", href: "/staff/activity" }],
  ceo: [{ label: "Leadership oversight", detail: "Review MD/Manager actions", href: "/staff/oversight/managers" }, { label: "Representatives", detail: "Review linked profiles (read-only)", href: "/staff/reps" }, { label: "Sales overview", detail: "Review sales and transaction status", href: "/staff/sales" }, { label: "Payments", detail: "Review payment verification status", href: "/staff/payments" }, { label: "Handovers", detail: "Review finalized and pending vehicle deliveries", href: "/staff/handovers" }, { label: "Quotations", detail: "Review issued customer quotations", href: "/staff/quotations" }, { label: "Imports", detail: "Review import progress", href: "/staff/imports" }, { label: "BL Requests", detail: "Review and decide BL approvals", href: "/staff/bl-requests" }, { label: "Inventory", detail: "Review vehicle stock (read-only)", href: "/staff/inventory" }, { label: "Reservations", detail: "Review vehicle reservations (read-only)", href: "/staff/reservations" }, { label: "Enquiries", detail: "Review requests and appointment schedules", href: "/staff/enquiries" }, { label: "Customers", detail: "Authorized customer directory", href: "/staff/customers" }],
  manager: [{ label: "Representatives", detail: "Link accounts and manage representative profiles", href: "/staff/reps" }, { label: "Sales", detail: "Create and confirm transactions", href: "/staff/sales" }, { label: "Payments", detail: "Record and review payments", href: "/staff/payments" }, { label: "Handovers", detail: "Prepare and finalize vehicle deliveries", href: "/staff/handovers" }, { label: "Quotations", detail: "Manage customer quotations", href: "/staff/quotations" }, { label: "Imports", detail: "Read import progress", href: "/staff/imports" }, { label: "Inventory", detail: "Review vehicle stock (read-only)", href: "/staff/inventory" }, { label: "Reservations", detail: "Review vehicle reservations (read-only)", href: "/staff/reservations" }, { label: "Enquiries", detail: "Review requests and appointment schedules", href: "/staff/enquiries" }, { label: "Customers", detail: "Authorized customer directory", href: "/staff/customers" }],
  staff: [{ label: "Inventory", detail: "Inventory workflow workspace", href: "/staff/inventory" }, { label: "Reservations", detail: "Manage vehicle holds and release history", href: "/staff/reservations" }, { label: "Handovers", detail: "Prepare confirmed sales for customer delivery", href: "/staff/handovers" }, { label: "Imports", detail: "Manage import records and progress", href: "/staff/imports" }, { label: "Quotations", detail: "Prepare and issue customer quotations", href: "/staff/quotations" }, { label: "Sales summary", detail: "View authorized transaction counts", href: "/staff/sales-summary" }, { label: "Enquiries", detail: "Review requests and appointment schedules", href: "/staff/enquiries" }, { label: "Customers", detail: "Authorized customer directory", href: "/staff/customers" }],
  rep: [{ label: "My sales", detail: "Your sales dashboard" }, { label: "My commission", detail: "Your commission dashboard" }],
};

function csrfToken() {
  return document.cookie.split("; ").find((item) => item.startsWith("csrftoken="))?.split("=")[1] ?? "";
}

export default function StaffPortal() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [signOutError, setSignOutError] = useState("");
  const [pending, setPending] = useState<number | null>(null);
  const [activeReservations, setActiveReservations] = useState<number | null>(null);
  const [salesCounts, setSalesCounts] = useState<{ draft_count: number; confirmed_count: number } | null>(null);
  const [stockCounts, setStockCounts] = useState<Record<string, number> | null>(null);
  const [paymentCounts, setPaymentCounts] = useState<{ pending_count: number; pending_amount_lkr: string } | null>(null);
  const [quotationCounts, setQuotationCounts] = useState<{ draft: number; issued: number } | null>(null);
  const [handoverCounts, setHandoverCounts] = useState<{ preparing: number; ready: number; finalized: number } | null>(null);
  useEffect(() => {
    fetch(`${API}/api/auth/me/`, { credentials: "include" })
      .then((response) => { if (!response.ok) throw new Error(); return response.json() as Promise<User>; })
      .then(setUser).catch(() => router.replace("/staff/login")).finally(() => setLoading(false));
  }, [router]);
  useEffect(() => { if (user && ["staff", "manager", "ceo"].includes(user.role)) fetch(`${API}/api/staff/enquiries/summary/`, { credentials: "include" }).then(r => r.ok ? r.json() : null).then((data: { pending: number } | null) => { if (data) setPending(data.pending); }).catch(() => undefined); }, [user]);
  useEffect(() => { if (user && ["staff", "manager", "ceo"].includes(user.role)) fetch(`${API}/api/staff/reservations/summary/`, { credentials: "include" }).then(r => r.ok ? r.json() : null).then((data: { active_count: number } | null) => { if (data) setActiveReservations(data.active_count); }).catch(() => undefined); }, [user]);
  useEffect(() => { if (user && ["staff", "manager", "ceo"].includes(user.role)) fetch(`${API}/api/manager/sales/summary/`, { credentials: "include" }).then(r => r.ok ? r.json() : null).then((data: { draft_count: number; confirmed_count: number } | null) => { if (data) setSalesCounts(data); }).catch(() => undefined); }, [user]);
  useEffect(() => { if (user && ["staff", "manager", "ceo"].includes(user.role)) fetch(`${API}/api/staff/inventory/`, { credentials: "include" }).then(r => r.ok ? r.json() : null).then((data: { status: string }[] | null) => { if (data) setStockCounts(data.reduce<Record<string, number>>((counts, vehicle) => { counts[vehicle.status] = (counts[vehicle.status] ?? 0) + 1; return counts; }, {})); }).catch(() => undefined); }, [user]);
  useEffect(() => { if (user && ["manager", "ceo"].includes(user.role)) fetch(`${API}/api/staff/payments/summary/`, { credentials: "include" }).then(r => r.ok ? r.json() : null).then((data: { pending_count: number; pending_amount_lkr: string } | null) => { if (data) setPaymentCounts(data); }).catch(() => undefined); }, [user]);
  useEffect(() => { if (user && ["staff", "manager", "ceo"].includes(user.role)) fetch(`${API}/api/staff/quotations/`, { credentials: "include" }).then(r => r.ok ? r.json() : null).then((data: { status: string }[] | null) => { if (data) setQuotationCounts({ draft: data.filter(q => q.status === "draft").length, issued: data.filter(q => q.status === "issued").length }); }).catch(() => undefined); }, [user]);
  useEffect(() => { if (user && ["staff", "manager", "ceo"].includes(user.role)) fetch(`${API}/api/staff/handovers/`, { credentials: "include" }).then(r => r.ok ? r.json() : null).then((data: { status: string }[] | null) => { if (data) setHandoverCounts({ preparing: data.filter(h => h.status === "preparing").length, ready: data.filter(h => h.status === "ready_for_review").length, finalized: data.filter(h => h.status === "finalized").length }); }).catch(() => undefined); }, [user]);

  async function signOut() {
    setSignOutError("");
    try {
      const response = await fetch(`${API}/api/auth/logout/`, {
        method: "POST", credentials: "include", headers: { "X-CSRFToken": decodeURIComponent(csrfToken()) },
      });
      if (!response.ok) throw new Error("Sign out failed.");
      router.replace("/staff/login");
    } catch {
      setSignOutError("Sign out failed. Please try again.");
    }
  }

  if (loading || !user) return <main className="portal-loading"><p className="eyebrow">SSP Â· Staff portal</p><p>Checking your secure session…</p></main>;
  if (user.role === "admin") return <AdminDashboard user={user} onSignOut={() => void signOut()} />;
  if (user.role === "rep") return <RepresentativeDashboard user={user} />;
  const items = navigation[user.role] ?? [];
  const displayName = [user.first_name, user.last_name].filter(Boolean).join(" ") || user.username;

  return (
    <div className="portal-layout">
      <aside className="portal-sidebar">
        <BrandLogo className="portal-sidebar-logo" />
        <span className="portal-sidebar-subtitle">STAFF PORTAL</span>
        <p className="sidebar-caption">WORKSPACE</p>
        <nav aria-label="Staff workspace">{items.map((item) => <a key={item.label} href={item.href ?? "#workspace"}>{item.label}<span>›</span></a>)}</nav>
        <div className="sidebar-foot"><span className="avatar">{displayName.slice(0, 1).toUpperCase()}</span><div><strong>{displayName}</strong><small>{roleLabels[user.role] ?? user.role}</small></div></div>
      </aside>
      <main className="portal-main">
        {signOutError && <p className="form-error" role="alert">{signOutError}</p>}
        <header className="portal-header"><div><p className="eyebrow">{roleLabels[user.role] ?? "Staff"} workspace</p><h1>Welcome, {displayName.split(" ")[0]}</h1></div><div className="portal-header-actions"><BrandLogo className="portal-header-logo" /><button className="quiet-button" onClick={signOut}>Sign out</button></div></header>
        <section className="portal-intro"><div><p className="eyebrow">YOUR WORKSPACE</p><h2>{roleLabels[user.role]} dashboard</h2><p>Tools and information available to your account are shown below.</p></div><span className="role-chip">{user.account_type} account</span></section>
        {user.role !== "rep" && <section className="staff-dashboard-overview" aria-label="Live operations overview">
          <div className="staff-dashboard-overview-heading"><div><p className="eyebrow">{user.role === "ceo" ? "EXECUTIVE OVERVIEW" : user.role === "manager" ? "MD OPERATIONS" : "OPERATIONS SNAPSHOT"}</p><h2>Current records</h2></div><span>Live data</span></div>
          <div className="staff-dashboard-metrics">
            <article><span>Vehicles in stock</span><strong>{stockCounts ? Object.values(stockCounts).reduce((total, value) => total + value, 0) : "—"}</strong><small>{stockCounts ? `${stockCounts.available ?? 0} available · ${stockCounts.reserved ?? 0} reserved · ${stockCounts.sold ?? 0} sold` : "Loading inventory"}</small></article>
            <article><span>Confirmed sales</span><strong>{salesCounts?.confirmed_count ?? "—"}</strong><small>Recorded transactions</small></article>
            <article><span>Draft sales</span><strong>{salesCounts?.draft_count ?? "—"}</strong><small>Awaiting authorized review</small></article>
            <article><span>Active reservations</span><strong>{activeReservations ?? "—"}</strong><small>Vehicle holds in progress</small></article>
            <article><span>Pending enquiries</span><strong>{pending ?? "—"}</strong><small>New or contacted</small></article>
            {(user.role === "manager" || user.role === "ceo") && <article><span>Payments awaiting verification</span><strong>{paymentCounts?.pending_count ?? "—"}</strong><small>{paymentCounts ? `${paymentCounts.pending_amount_lkr} LKR pending review` : "Loading payment data"}</small></article>}
            <article><span>Quotations</span><strong>{quotationCounts ? quotationCounts.draft + quotationCounts.issued : "—"}</strong><small>{quotationCounts ? `${quotationCounts.draft} drafts · ${quotationCounts.issued} issued` : "Loading quotation data"}</small></article>
            <article><span>Handovers</span><strong>{handoverCounts ? handoverCounts.preparing + handoverCounts.ready + handoverCounts.finalized : "—"}</strong><small>{handoverCounts ? `${handoverCounts.preparing} preparing · ${handoverCounts.ready} awaiting review · ${handoverCounts.finalized} finalized` : "Loading handover records"}</small></article>
          </div>
        </section>}
        {user.role === "staff" && activeReservations !== null ? <Link className="reservation-dashboard-count" href="/staff/reservations"><span>Active vehicle reservations</span><strong>{activeReservations}</strong><span>Review reservation directory</span></Link> : null}
        <section id="workspace" className="workspace-grid" aria-label="Role workspace">
          {items.map((item, index) => (
            <article className="workspace-card" key={item.label}>
              <span className="card-index">0{index + 1}</span>
              <h3>{item.label}{item.label === "Enquiries" && pending !== null ? <span className="pending-counter">{pending} pending</span> : null}</h3>
              <p>{item.detail}</p>
              {item.href ? <Link className="coming-soon" href={item.href}>Open {item.label.toLowerCase()}</Link> : <span className="coming-soon">Workspace placeholder</span>}
            </article>
          ))}
        </section>
      </main>
    </div>
  );
}
