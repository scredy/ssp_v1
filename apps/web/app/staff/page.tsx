"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
type User = { username: string; first_name: string; last_name: string; role: string; account_type: string };

const roleLabels: Record<string, string> = { admin: "Admin", ceo: "CEO", manager: "MD/Manager", staff: "Staff", rep: "Rep" };
const navigation: Record<string, { label: string; detail: string }[]> = {
  admin: [{ label: "Accounts", detail: "Manage internal and external accounts" }, { label: "Activity", detail: "Recent account activity and audit history" }],
  ceo: [{ label: "Leadership oversight", detail: "Review MD/Manager actions" }, { label: "Inventory", detail: "Review vehicle stock (read-only)" }, { label: "Commission rules", detail: "Manage commission rule settings" }],
  manager: [{ label: "Rep management", detail: "Manage representative accounts" }, { label: "Sales oversight", detail: "Sales oversight workspace" }, { label: "Inventory", detail: "Review vehicle stock (read-only)" }, { label: "Commission rules", detail: "Manage commission rule settings" }],
  staff: [{ label: "Inventory", detail: "Inventory workflow workspace" }, { label: "Imports", detail: "Import workflow workspace" }, { label: "Reservations", detail: "Reservation workflow workspace" }],
  rep: [{ label: "My sales", detail: "Your sales dashboard" }, { label: "My commission", detail: "Your commission dashboard" }],
};

function csrfToken() {
  return document.cookie.split("; ").find((item) => item.startsWith("csrftoken="))?.split("=")[1] ?? "";
}

export default function StaffPortal() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    fetch(`${API}/api/auth/me/`, { credentials: "include" })
      .then((response) => { if (!response.ok) throw new Error(); return response.json() as Promise<User>; })
      .then(setUser).catch(() => router.replace("/staff/login")).finally(() => setLoading(false));
  }, [router]);

  async function signOut() {
    await fetch(`${API}/api/auth/logout/`, {
      method: "POST", credentials: "include", headers: { "X-CSRFToken": decodeURIComponent(csrfToken()) },
    });
    router.replace("/staff/login");
  }

  if (loading || !user) return <main className="portal-loading"><p className="eyebrow">SSP · Staff portal</p><p>Checking your secure session…</p></main>;
  const items = navigation[user.role] ?? [];
  const displayName = [user.first_name, user.last_name].filter(Boolean).join(" ") || user.username;

  return (
    <div className="portal-layout">
      <aside className="portal-sidebar">
        <a className="brand" href="/">SSP<span>Staff portal</span></a>
        <p className="sidebar-caption">WORKSPACE</p>
        <nav aria-label="Staff workspace">{items.map((item) => <a key={item.label} href="#workspace">{item.label}<span>›</span></a>)}</nav>
        <div className="sidebar-foot"><span className="avatar">{displayName.slice(0, 1).toUpperCase()}</span><div><strong>{displayName}</strong><small>{roleLabels[user.role] ?? user.role}</small></div></div>
      </aside>
      <main className="portal-main">
        <header className="portal-header"><div><p className="eyebrow">{roleLabels[user.role] ?? "Staff"} workspace</p><h1>Welcome, {displayName.split(" ")[0]}</h1></div><button className="quiet-button" onClick={signOut}>Sign out</button></header>
        <section className="portal-intro"><div><p className="eyebrow">YOUR WORKSPACE</p><h2>{roleLabels[user.role]} dashboard</h2><p>Tools and information available to your account are shown below.</p></div><span className="role-chip">{user.account_type} account</span></section>
        <section id="workspace" className="workspace-grid" aria-label="Role workspace">
          {items.map((item, index) => <article className="workspace-card" key={item.label}><span className="card-index">0{index + 1}</span><h3>{item.label}</h3><p>{item.detail}</p>{item.label === "Inventory" ? <a className="coming-soon" href="/staff/inventory">Open inventory →</a> : <span className="coming-soon">Workspace placeholder</span>}</article>)}
        </section>
        {user.role === "ceo" || user.role === "manager" ? <p className="boundary-note">Future handovers are routed through CEO or MD/Manager approval.</p> : null}
      </main>
    </div>
  );
}
