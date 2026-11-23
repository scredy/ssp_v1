"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, User } from "@/lib/car-api";
import { staffRouteRedirect } from "@/lib/staff-route-guard.mjs";
import { BrandLogo } from "@/components/public-site";

type MenuItem = { label: string; href: string };
const roleNames: Record<string, string> = { admin: "Admin", ceo: "CEO", manager: "MD/Manager", staff: "Staff", rep: "Representative" };
const menus: Record<string, MenuItem[]> = {
  admin: [{ label: "Dashboard", href: "/staff" }, { label: "Users", href: "/staff/accounts" }, { label: "Account activity", href: "/staff/activity" }],
  ceo: [{ label: "Overview", href: "/staff" }, { label: "Sales", href: "/staff/sales" }, { label: "Payments", href: "/staff/payments" }, { label: "Handovers", href: "/staff/handovers" }, { label: "Commission policy", href: "/staff/commission-rules" }, { label: "Quotations", href: "/staff/quotations" }, { label: "Imports", href: "/staff/imports" }, { label: "BL Requests", href: "/staff/bl-requests" }, { label: "Inventory", href: "/staff/inventory" }, { label: "Reservations", href: "/staff/reservations" }, { label: "Representatives", href: "/staff/reps" }, { label: "Enquiries", href: "/staff/enquiries" }, { label: "Customers", href: "/staff/customers" }, { label: "Leadership oversight", href: "/staff/oversight/managers" }],
  manager: [{ label: "Dashboard", href: "/staff" }, { label: "Sales", href: "/staff/sales" }, { label: "Payments", href: "/staff/payments" }, { label: "Handovers", href: "/staff/handovers" }, { label: "Commission policy", href: "/staff/commission-rules" }, { label: "Quotations", href: "/staff/quotations" }, { label: "Imports", href: "/staff/imports" }, { label: "Inventory", href: "/staff/inventory" }, { label: "Reservations", href: "/staff/reservations" }, { label: "Representatives", href: "/staff/reps" }, { label: "Enquiries", href: "/staff/enquiries" }, { label: "Customers", href: "/staff/customers" }],
  staff: [{ label: "Dashboard", href: "/staff" }, { label: "Inventory", href: "/staff/inventory" }, { label: "Reservations", href: "/staff/reservations" }, { label: "Handovers", href: "/staff/handovers" }, { label: "Imports", href: "/staff/imports" }, { label: "Payments", href: "/staff/payments" }, { label: "Quotations", href: "/staff/quotations" }, { label: "Enquiries", href: "/staff/enquiries" }, { label: "Customers", href: "/staff/customers" }, { label: "Sales summary", href: "/staff/sales-summary" }],
  rep: [{ label: "Dashboard", href: "/staff" }, { label: "My sales", href: "/staff/my-sales" }, { label: "My commissions", href: "/staff/my-commissions" }],
};
const routeRoles: [string, string[]][] = [
  ["/staff/accounts", ["admin"]], ["/staff/activity", ["admin"]], ["/staff/notifications", ["admin", "ceo", "manager", "staff", "rep"]],
  ["/staff/oversight/managers", ["ceo"]],
  ["/staff/commission-rules", ["ceo", "manager"]],
  ["/staff/commissions", ["ceo", "manager"]],
  ["/staff/payments", ["staff", "manager", "ceo"]],
  ["/staff/quotations", ["staff", "manager", "ceo"]],
  ["/staff/imports", ["staff", "manager", "ceo"]], ["/staff/bl-requests", ["ceo"]],
  ["/staff/handovers", ["staff", "manager", "ceo"]],
  ["/staff/reps", ["manager", "ceo"]], ["/staff/sales-summary", ["staff", "manager", "ceo"]],
  ["/staff/sales", ["manager", "ceo"]], ["/staff/inventory", ["staff", "manager", "ceo"]],
  ["/staff/reservations", ["staff", "manager", "ceo"]], ["/staff/enquiries", ["staff", "manager", "ceo"]],
  ["/staff/customers", ["staff", "manager", "ceo"]],
  ["/staff/my-sales", ["rep"]], ["/staff/my-commissions", ["rep"]],
];
const titleFor = (path: string) => {
  if (path === "/staff") return "Dashboard";
  if (path === "/staff/commissions") return "Commission payouts";
  const match = routeRoles.map(([route]) => route).sort((a, b) => b.length - a.length).find((route) => path === route || path.startsWith(`${route}/`));
  return match ? ({ "/staff/accounts": "Users", "/staff/activity": "Recent account activity", "/staff/notifications": "Notifications", "/staff/oversight/managers": "Leadership oversight", "/staff/commission-rules": "Commission policy", "/staff/reps": "Representatives", "/staff/sales-summary": "Sales summary", "/staff/sales": "Sales directory", "/staff/payments": "Payments", "/staff/quotations": "Quotations", "/staff/imports": "Imports", "/staff/bl-requests": "BL Requests", "/staff/handovers": "Handovers", "/staff/inventory": "Vehicle inventory", "/staff/reservations": "Reservations", "/staff/enquiries": "Enquiries inbox", "/staff/customers": "Customers", "/staff/my-sales": "My sales", "/staff/my-commissions": "My commissions" } as Record<string, string>)[match] : "Workspace";
};

export default function StaffShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [signOutError, setSignOutError] = useState("");
  const [unreadNotifications, setUnreadNotifications] = useState<number | null>(null);
  const isPublicAuth = ["/staff/login", "/staff/password-reset", "/staff/accept-invitation", "/staff/reset-password"].includes(pathname);

  useEffect(() => {
    if (isPublicAuth) { setLoading(false); return; }
    let active = true;
    api<User>("/api/auth/me/").then((current) => { if (active) setUser(current); })
      .catch(() => { if (active) router.replace("/staff/login"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [isPublicAuth, router]);

  useEffect(() => {
    if (!user) return;
    let active = true;
    const updateCount = (event: Event) => {
      const count = (event as CustomEvent<unknown>).detail;
      if (typeof count === "number" && Number.isInteger(count) && count >= 0) setUnreadNotifications(count);
    };
    window.addEventListener("ssp:notification-count", updateCount);
    api<{ unread_count: number }>("/api/notifications/?limit=1&offset=0")
      .then((page) => { if (active) setUnreadNotifications(page.unread_count); })
      .catch(() => { if (active) setUnreadNotifications(null); });
    return () => { active = false; window.removeEventListener("ssp:notification-count", updateCount); };
  }, [user?.username]);

  useEffect(() => {
    const redirect = staffRouteRedirect(pathname, user?.role, routeRoles);
    if (redirect) router.replace(redirect);
  }, [user, pathname, isPublicAuth, router]);

  if (isPublicAuth) return <>{children}</>;
  if (loading || !user) return <main className="staff-shell-loading"><p className="eyebrow">SSP MOTOR TRADING</p><p>Checking your secure session…</p></main>;

  const menu = menus[user.role] ?? [];
  const displayName = [user.first_name, user.last_name].filter(Boolean).join(" ") || user.username;
  const pageTitle = pathname === "/staff"
    ? ({ admin: "Account overview", ceo: "CEO overview", manager: "MD dashboard", staff: "Staff dashboard", rep: "Representative dashboard" } as Record<string, string>)[user.role]
    : titleFor(pathname);
  async function signOut() {
    setSignOutError("");
    try {
      await api<void>("/api/auth/logout/", { method: "POST", body: "{}" });
      setUser(null);
      router.replace("/staff/login");
    } catch {
      setSignOutError("Sign out failed. Please try again.");
    }
  }

  return <div className="portal-layout staff-app-shell">
    <aside className="portal-sidebar staff-app-sidebar">
      <BrandLogo href="/staff" className="portal-sidebar-logo" priority />
      <span className="portal-sidebar-subtitle">{roleNames[user.role]} WORKSPACE</span>
      <button className="staff-mobile-menu-toggle" aria-expanded={mobileMenuOpen} aria-controls="staff-primary-nav" onClick={() => setMobileMenuOpen((open) => !open)}>{mobileMenuOpen ? "Close menu" : "Menu"}</button>
      <nav id="staff-primary-nav" className={mobileMenuOpen ? "is-open" : ""} aria-label={`${roleNames[user.role]} navigation`}>
        {menu.map((item) => {
          const active = item.href === "/staff" ? pathname === item.href : pathname === item.href || pathname.startsWith(`${item.href}/`);
          return <Link key={item.href} href={item.href} className={active ? "is-current" : ""} aria-current={active ? "page" : undefined} onClick={() => setMobileMenuOpen(false)}>{item.label}<span aria-hidden="true">›</span></Link>;
        })}
        {Object.prototype.hasOwnProperty.call(menus, user.role) && <Link href="/staff/notifications" className={pathname.startsWith("/staff/notifications") ? "is-current" : ""} aria-current={pathname.startsWith("/staff/notifications") ? "page" : undefined}>Notifications<span aria-hidden="true">›</span></Link>}
        {(user.role === "ceo" || user.role === "manager") && <Link href="/staff/commissions" className={pathname === "/staff/commissions" ? "is-current" : ""} aria-current={pathname === "/staff/commissions" ? "page" : undefined}>Commission payouts<span aria-hidden="true">›</span></Link>}
      </nav>
      <div className="sidebar-foot"><span className="avatar">{displayName.slice(0, 1).toUpperCase()}</span><div><strong>{displayName}</strong><small>{roleNames[user.role] ?? user.role}</small></div></div>
    </aside>
    <div className="portal-main staff-app-main">
      <header className="portal-header staff-app-header"><div><p className="eyebrow">SSP MOTOR TRADING ? {roleNames[user.role]}</p><h1>{pageTitle}</h1></div><div className="staff-app-user"><Link className="staff-notification-bell" href="/staff/notifications" aria-label={unreadNotifications === null || unreadNotifications === 0 ? "Notifications" : `Notifications, ${unreadNotifications} unread`} aria-current={pathname.startsWith("/staff/notifications") ? "page" : undefined}><svg viewBox="0 0 24 24" focusable="false" aria-hidden="true"><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></svg>{unreadNotifications !== null && unreadNotifications > 0 && <span className="staff-notification-count" aria-hidden="true">{unreadNotifications > 99 ? "99+" : unreadNotifications}</span>}<span className="staff-notification-live" aria-live="polite" aria-atomic="true">{unreadNotifications === null ? "" : unreadNotifications === 0 ? "No unread notifications." : `${unreadNotifications} unread notifications.`}</span></Link><span>{displayName}</span><span className="role-chip">{roleNames[user.role]}</span><button className="quiet-button" onClick={() => void signOut()}>Sign out</button></div></header>
      {signOutError && <p className="form-error" role="alert">{signOutError}</p>}
      <div className="staff-page-body" key="staff-routes">{children}</div>
    </div>
  </div>;
}
