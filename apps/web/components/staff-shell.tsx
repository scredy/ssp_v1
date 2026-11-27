"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { api, User } from "@/lib/car-api";
import { staffRouteRedirect } from "@/lib/staff-route-guard.mjs";
import { BrandLogo } from "@/components/public-site";

type MenuItem = { label: string; href: string };
const navIcon = (label: string) => {
  const value = label.toLowerCase();
  if (value.includes("dashboard") || value === "overview") return "M3 10.5 12 3l9 7.5M5.5 9.5V21h13V9.5M9 21v-7h6v7";
  if (value.includes("sales") || value.includes("leaderboard")) return "M4 19V5m0 14h16M7 15l4-4 3 2 5-6M16 7h3v3";
  if (value.includes("payment") || value.includes("commission")) return "M4 6h16v13H4zM4 10h16M7 15h4";
  if (value.includes("handover")) return "M7 3h10v18H7zM9 7h6M9 11h6M9 15h4";
  if (value.includes("inventory")) return "M3 13l2-6h14l2 6v6h-3v-3H6v3H3zM5 13h14M7 16h.01M17 16h.01";
  if (value.includes("reservation") || value.includes("quotation") || value.includes("request")) return "M5 4h14v17H5zM8 2v4M16 2v4M5 9h14M8 13h3M8 17h7";
  if (value.includes("import") || value.includes("bl ")) return "M3 7h11v11H3zM14 11h4l3 3v4h-7zM7 21a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM18 21a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z";
  if (value.includes("representative") || value.includes("oversight")) return "M16 20v-1.5a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4V20M9.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM16 3.5a4 4 0 0 1 0 7.5M17 14.5a4 4 0 0 1 4 4V20";
  if (value.includes("enquir")) return "M4 4h16v13H9l-5 4zM8 9h8M8 13h5";
  if (value.includes("customer")) return "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4 21v-1a8 8 0 0 1 16 0v1z";
  if (value.includes("notification")) return "M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4";
  if (value.includes("activity")) return "M3 12h4l3-8 4 16 3-8h4";
  return "M4 4h16v16H4zM8 8h8M8 12h8M8 16h5";
};
const roleNames: Record<string, string> = { admin: "Admin", ceo: "CEO", manager: "MD/Manager", staff: "Staff", rep: "Representative" };
const displayRoleName = (user: User) => user.is_superuser ? "Superuser" : roleNames[user.role] ?? user.role;
const menus: Record<string, MenuItem[]> = {
  admin: [{ label: "Dashboard", href: "/staff" }, { label: "Users", href: "/staff/accounts" }, { label: "Account activity", href: "/staff/activity" }],
  ceo: [{ label: "Overview", href: "/staff" }, { label: "Sales", href: "/staff/sales" }, { label: "Payments", href: "/staff/payments" }, { label: "Handovers", href: "/staff/handovers" }, { label: "Commission policy", href: "/staff/commission-rules" }, { label: "Quotations", href: "/staff/quotations" }, { label: "Imports", href: "/staff/imports" }, { label: "BL Requests", href: "/staff/bl-requests" }, { label: "Inventory", href: "/staff/inventory" }, { label: "Reservations", href: "/staff/reservations" }, { label: "Representatives", href: "/staff/reps" }, { label: "Enquiries", href: "/staff/enquiries" }, { label: "Customers", href: "/staff/customers" }, { label: "Leadership oversight", href: "/staff/oversight/managers" }],
  manager: [{ label: "Dashboard", href: "/staff" }, { label: "Sales", href: "/staff/sales" }, { label: "Payments", href: "/staff/payments" }, { label: "Handovers", href: "/staff/handovers" }, { label: "Commission policy", href: "/staff/commission-rules" }, { label: "Quotations", href: "/staff/quotations" }, { label: "Imports", href: "/staff/imports" }, { label: "Inventory", href: "/staff/inventory" }, { label: "Reservations", href: "/staff/reservations" }, { label: "Representatives", href: "/staff/reps" }, { label: "Enquiries", href: "/staff/enquiries" }, { label: "Customers", href: "/staff/customers" }],
  staff: [{ label: "Dashboard", href: "/staff" }, { label: "Inventory", href: "/staff/inventory" }, { label: "Reservations", href: "/staff/reservations" }, { label: "Handovers", href: "/staff/handovers" }, { label: "Imports", href: "/staff/imports" }, { label: "Quotations", href: "/staff/quotations" }, { label: "Enquiries", href: "/staff/enquiries" }, { label: "Customers", href: "/staff/customers" }, { label: "Sales summary", href: "/staff/sales-summary" }],
  rep: [{ label: "Dashboard", href: "/staff" }, { label: "My sales", href: "/staff/my-sales" }, { label: "My commissions", href: "/staff/my-commissions" }],
};
const routeRoles: [string, string[]][] = [
  ["/staff/accounts", ["admin"]], ["/staff/activity", ["admin"]], ["/staff/notifications", ["admin", "ceo", "manager", "staff", "rep"]],
  ["/staff/oversight/managers", ["ceo"]],
  ["/staff/commission-rules", ["ceo", "manager"]],
  ["/staff/commissions", ["ceo", "manager"]],
  ["/staff/payments", ["manager", "ceo"]],
  ["/staff/quotations", ["staff", "manager", "ceo"]],
  ["/staff/imports", ["staff", "manager", "ceo"]], ["/staff/bl-requests", ["ceo"]],
  ["/staff/handovers", ["staff", "manager", "ceo"]],
  ["/staff/reps", ["manager", "ceo"]], ["/staff/sales-summary", ["staff", "manager", "ceo"]],
  ["/staff/sales", ["manager", "ceo"]], ["/staff/inventory", ["staff", "manager", "ceo"]],
  ["/staff/reservations", ["staff", "manager", "ceo"]], ["/staff/enquiries", ["staff", "manager", "ceo"]],
  ["/staff/customers", ["staff", "manager", "ceo"]],
  ["/staff/my-sales", ["rep"]], ["/staff/my-commissions", ["rep"]],
];
const StaffSessionContext = createContext<User | null>(null);
export function useStaffSession() { return useContext(StaffSessionContext); }
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
    if (!user || isPublicAuth) return;
    let active = true;
    let inFlight = false;
    let version = 0;

    async function refreshCount() {
      if (!active || inFlight || document.visibilityState === "hidden") return;
      inFlight = true;
      const currentVersion = ++version;

      try {
        const page = await api<{ unread_count: number }>(
          "/api/notifications/?limit=1&offset=0",
          { cache: "no-store" }
        );

        if (active && currentVersion === version &&
            Number.isInteger(page.unread_count) && page.unread_count >= 0) {
          setUnreadNotifications(page.unread_count);
        }
      } catch {
        // Retain the last known count during temporary network failures.
      } finally {
        inFlight = false;
      }
    }

    const updateCount = (event: Event) => {
      const count = (event as CustomEvent<unknown>).detail;
      if (active && typeof count === "number" &&
          Number.isInteger(count) && count >= 0) {
        version++;
        setUnreadNotifications(count);
      }
    };

    const refreshVisible = () => {
      if (document.visibilityState === "visible") void refreshCount();
    };

    window.addEventListener("ssp:notification-count", updateCount);
    window.addEventListener("focus", refreshVisible);
    document.addEventListener("visibilitychange", refreshVisible);

    void refreshCount();
    const interval = window.setInterval(refreshVisible, 30000);

    return () => {
      active = false;
      window.clearInterval(interval);
      window.removeEventListener("ssp:notification-count", updateCount);
      window.removeEventListener("focus", refreshVisible);
      document.removeEventListener("visibilitychange", refreshVisible);
    };
  }, [user?.username, isPublicAuth, pathname]);

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
      setUnreadNotifications(null);
      router.replace("/staff/login");
    } catch {
      setSignOutError("Sign out failed. Please try again.");
    }
  }

  return <StaffSessionContext.Provider value={user}><div className="portal-layout staff-app-shell">
    <aside className="portal-sidebar staff-app-sidebar">
      <BrandLogo href="/staff" className="portal-sidebar-logo" priority />
      <span className="portal-sidebar-subtitle">{displayRoleName(user)} WORKSPACE</span>
      <button className="staff-mobile-menu-toggle" aria-expanded={mobileMenuOpen} aria-controls="staff-primary-nav" onClick={() => setMobileMenuOpen((open) => !open)}>{mobileMenuOpen ? "Close menu" : "Menu"}</button>
      <nav id="staff-primary-nav" className={mobileMenuOpen ? "is-open" : ""} aria-label={`${displayRoleName(user)} navigation`}>
        {menu.map((item) => {
          const active = item.href === "/staff" ? pathname === item.href : pathname === item.href || pathname.startsWith(`${item.href}/`);
          return <Link key={item.href} href={item.href} className={active ? "is-current" : ""} aria-current={active ? "page" : undefined} onClick={() => setMobileMenuOpen(false)}><span className="staff-nav-icon" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><path d={navIcon(item.label)} /></svg></span><span className="staff-nav-label">{item.label}</span><span className="staff-nav-chevron" aria-hidden="true">›</span></Link>;
        })}
        {Object.prototype.hasOwnProperty.call(menus, user.role) && <Link href="/staff/notifications" className={pathname.startsWith("/staff/notifications") ? "is-current" : ""} aria-current={pathname.startsWith("/staff/notifications") ? "page" : undefined}><span className="staff-nav-icon" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><path d={navIcon("Notifications")} /></svg></span><span className="staff-nav-label">Notifications</span><span className="staff-nav-chevron" aria-hidden="true">›</span></Link>}
        {(user.role === "ceo" || user.role === "manager") && <Link href="/staff/commissions" className={pathname === "/staff/commissions" ? "is-current" : ""} aria-current={pathname === "/staff/commissions" ? "page" : undefined}><span className="staff-nav-icon" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><path d={navIcon("Commission payouts")} /></svg></span><span className="staff-nav-label">Commission payouts</span><span className="staff-nav-chevron" aria-hidden="true">›</span></Link>}
      </nav>
      <div className="sidebar-foot"><span className="avatar">{displayName.slice(0, 1).toUpperCase()}</span><div><strong>{displayName}</strong><small>{displayRoleName(user)}</small></div></div>
    </aside>
    <div className="portal-main staff-app-main">
      <header className={`portal-header staff-app-header ${pathname === "/staff/notifications" ? "has-notifications-hero" : ""}`}><div><nav className="staff-breadcrumb" aria-label="Breadcrumb"><Link href="/staff">SSP Motor Trading</Link><span aria-hidden="true">›</span><span>{displayRoleName(user)}</span><span aria-hidden="true">›</span><span aria-current="page">{pageTitle}</span></nav>{pathname !== "/staff/notifications" && <h1>{pageTitle}</h1>}</div><div className="staff-app-user"><Link className="staff-notification-bell" href="/staff/notifications" aria-label={unreadNotifications === null || unreadNotifications === 0 ? "Notifications" : `Notifications, ${unreadNotifications} unread`} aria-current={pathname.startsWith("/staff/notifications") ? "page" : undefined}><svg viewBox="0 0 24 24" focusable="false" aria-hidden="true"><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></svg>{unreadNotifications !== null && unreadNotifications > 0 && <span className="staff-notification-count" aria-hidden="true">{unreadNotifications > 99 ? "99+" : unreadNotifications}</span>}<span className="staff-notification-live" aria-live="polite" aria-atomic="true">{unreadNotifications === null ? "" : unreadNotifications === 0 ? "No unread notifications." : `${unreadNotifications} unread notifications.`}</span></Link><span>{displayName}</span><span className="role-chip">{displayRoleName(user)}</span><button className="quiet-button" onClick={() => void signOut()}>Sign out</button></div></header>
      {signOutError && <p className="form-error" role="alert">{signOutError}</p>}
      <div className="staff-page-body" key="staff-routes">{children}</div>
    </div>
  </div></StaffSessionContext.Provider>;
}
