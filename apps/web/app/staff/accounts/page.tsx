"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/car-api";
import { BrandLogo } from "@/components/public-site";

type Account = {
  id: number; username: string; first_name: string; last_name: string; email: string;
  phone: string | null; role: string; account_type: "internal" | "external"; is_active: boolean; is_onboarded: boolean; is_superuser: boolean;
};
type CurrentUser = { id: number; role: string; is_superuser: boolean };

const roles = [
  { value: "ceo", label: "CEO" },
  { value: "manager", label: "MD/Manager" },
  { value: "staff", label: "Staff" },
  { value: "rep", label: "Rep" },
];
const roleLabels: Record<string, string> = { admin: "Admin", ceo: "CEO", manager: "MD/Manager", staff: "Staff", rep: "Rep" };

export default function AccountsPage() {
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [listError, setListError] = useState("");
  const [success, setSuccess] = useState("");
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [editing, setEditing] = useState<Account | null>(null);
  const [creating, setCreating] = useState(false);
  const [forbidden, setForbidden] = useState(false);

  async function loadAccounts() {
    try {
      setAccounts(await api<Account[]>("/api/accounts/"));
      setListError("");
    } catch (cause) {
      setListError(cause instanceof Error ? cause.message : "Unable to load accounts.");
    }
  }

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const user = await api<CurrentUser>("/api/auth/me/");
        if (!active) return;
        if (user.role !== "admin") { setForbidden(true); return; }
        setCurrentUser(user);
        await loadAccounts();
      } catch (cause) {
        if (!active) return;
        const message = cause instanceof Error ? cause.message : "Unable to check your session.";
        if (message.includes("(401)") || message.includes("(403)")) router.replace("/staff/login");
        else setError(message);
      }
      finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, [router]);

  const filtered = useMemo(() => accounts.filter((account) => {
    const haystack = [account.username, account.first_name, account.last_name, account.email, account.phone ?? ""]
      .join(" ").toLowerCase();
    return haystack.includes(query.toLowerCase()) && (!roleFilter || account.role === roleFilter) &&
      (!typeFilter || account.account_type === typeFilter);
  }), [accounts, query, roleFilter, typeFilter]);

  async function submitAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError(""); setSuccess("");
    const form = new FormData(event.currentTarget);
    const phone = String(form.get("phone") ?? "").trim();
    const common: Record<string, string | null> = {
      first_name: String(form.get("first_name") ?? "").trim(),
      last_name: String(form.get("last_name") ?? "").trim(),
      email: String(form.get("email") ?? "").trim(),
      phone: phone || null,
      account_type: editing ? String(form.get("account_type") ?? editing.account_type) : "internal",
    };
    if (editing) common.username = String(form.get("username") ?? "").trim();
    if (!editing || (editing.role !== "admin" && !editing.is_superuser) || (currentUser?.is_superuser && !editing.is_superuser)) {
      common.role = String(form.get("role") ?? "");
      if (editing && common.role !== editing.role) {
        const previousRole = editing.is_superuser ? "Superuser" : roleLabels[editing.role] ?? editing.role;
        const nextRole = roleLabels[common.role] ?? common.role;
        if (!window.confirm(`Change ${editing.username}'s role from ${previousRole} to ${nextRole}? This change takes effect immediately.`)) { setBusy(false); return; }
      }
    }
    try {
      let saved: Account;
      if (editing) {
        saved = await api<Account>(`/api/accounts/${editing.id}/`, { method: "PATCH", body: JSON.stringify(common) });
        setSuccess(`Changes saved for ${editing.username}.`);
      } else {
        const payload = { ...common, username: String(form.get("username") ?? "").trim() };
        saved = await api<Account>("/api/accounts/", { method: "POST", body: JSON.stringify(payload) });
        setSuccess(`Internal account ${saved.username} was created. An invitation was sent to ${saved.email}.`);
      }
      await loadAccounts(); setEditing(null); setCreating(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to save this account.");
    } finally { setBusy(false); }
  }

  async function setAccountActive(account: Account, active: boolean) {
    const action = active ? "Activate" : "Deactivate";
    if (!window.confirm(`${action} ${account.username}?`)) return;
    setBusy(true); setError(""); setSuccess("");
    try {
      await api(`/api/accounts/${account.id}/`, { method: "PATCH", body: JSON.stringify({ is_active: active }) });
      await loadAccounts(); setSuccess(`${account.username} was ${active ? "activated" : "deactivated"}.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to update this account's status.");
    } finally { setBusy(false); }
  }

  async function sendAccessLink(account: Account, kind: "invitation" | "password_reset") {
    setBusy(true); setError(""); setSuccess("");
    try {
      await api(`/api/accounts/${account.id}/access-link/`, { method: "POST", body: JSON.stringify({ kind }) });
      setSuccess(kind === "invitation" ? `A new invitation was sent to ${account.email}.` : `A password reset link was sent to ${account.email}.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to send the account email.");
    } finally { setBusy(false); }
  }

  if (loading) return <main className="workspace-page"><p className="state-card">Loading account workspace…</p></main>;
  if (forbidden) return <main className="workspace-page"><Link className="text-link" href="/staff">← Staff workspace</Link><p className="state-card state-error" role="alert">Your role cannot manage accounts.</p></main>;
  if (!currentUser) return <main className="workspace-page"><Link className="text-link" href="/staff/login">← Sign in</Link><p className="state-card state-error" role="alert">{error || "Your account session could not be checked."}</p></main>;

  return <main className="workspace-page admin-workspace">
    <header className="site-header staff-brand-header"><BrandLogo href="/staff" className="staff-page-logo" priority /><span className="staff-brand-caption">ADMIN WORKSPACE</span><nav><Link href="/staff/activity">Account activity</Link><Link href="/staff">Workspace</Link></nav></header>
    <section className="workspace-hero"><p className="eyebrow">ADMINISTRATION</p><h1>Accounts</h1><p>Create, update and deactivate internal or external accounts. A Django Superuser can manage Admin accounts; regular Admins can manage employee roles only.</p></section>
    {error && <p className="inline-error" role="alert">{error}</p>}{success && <p className="inline-notice" role="status">{success}</p>}
    <section className="account-toolbar" aria-label="Search and filter accounts">
      <label className="search-field">Search accounts<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Username, name, email or phone" /></label>
      <label>Role<select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}><option value="">All roles</option>{Object.entries(roleLabels).map(([value, label]) => <option key={value} value={value}>{label}{value === "admin" ? " and Superusers" : ""}</option>)}</select></label>
      <label>Account type<select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}><option value="">Internal and external</option><option value="internal">Internal</option><option value="external">External</option></select></label>
      <button className="primary-button" onClick={() => { setEditing(null); setCreating(true); setError(""); setSuccess(""); }}>+ Create account</button>
    </section>
    {creating || editing ? <form className="account-form" onSubmit={submitAccount} key={editing?.id ?? "create"}>
      <div className="form-heading"><div><p className="eyebrow">{editing ? "EDIT ACCOUNT" : "NEW ACCOUNT"}</p><h2>{editing ? `Update ${editing.username}` : "Create account"}</h2></div><button type="button" className="quiet-button" onClick={() => { setCreating(false); setEditing(null); }}>Cancel</button></div>
      <div className="account-form-grid">
        {!editing && <label>Username<input name="username" required maxLength={150} autoComplete="off" /></label>}
        {editing && <label>Username<input name="username" required maxLength={150} autoComplete="off" defaultValue={editing.username} /></label>}
        <label>First name<input name="first_name" maxLength={150} defaultValue={editing?.first_name ?? ""} /></label>
        <label>Last name<input name="last_name" maxLength={150} defaultValue={editing?.last_name ?? ""} /></label>
        <label>Email<input name="email" type="email" required defaultValue={editing?.email ?? ""} /></label>
        <label>Phone<input name="phone" type="tel" maxLength={32} defaultValue={editing?.phone ?? ""} /></label>
        {editing ? <label>Account type<select name="account_type" required defaultValue={editing.account_type}><option value="internal">Internal</option><option value="external">External</option></select></label> : <label>Account type<input value="Internal" disabled /><span className="field-note">New accounts use internal SSP roles only.</span></label>}
        {editing?.is_superuser || (editing?.role === "admin" && !currentUser.is_superuser) ? <label>Role<input value={editing.is_superuser ? "Superuser" : "Admin"} disabled /><span className="field-note">Privileged role changes are protected.</span></label> : <label>Role<select name="role" required defaultValue={editing?.role ?? ""}><option value="" disabled>Select a role</option>{roles.map((role) => <option key={role.value} value={role.value}>{role.label}</option>)}{currentUser.is_superuser && <option value="admin">Admin</option>}</select></label>}
        {!editing && <p className="field-note account-wide">A secure invitation email will provide the password setup link.</p>}
      </div>
      <p className="account-security-note">New accounts receive a single-use setup link by email. Passwords are never entered or displayed here. Website-created Admin accounts are regular Admins; Django superusers are created only through the secured server procedure.</p>
      <button className="primary-button" disabled={busy}>{busy ? "Saving…" : editing ? "Save account" : "Create account and send invitation"}</button>
    </form> : null}
    {listError && <div className="inline-error" role="alert">Unable to refresh account list: {listError} <button className="text-button" onClick={() => void loadAccounts()}>Retry</button></div>}
    <section className="account-table-wrap" aria-label="Accounts" aria-live="polite">
      {loading ? <p className="state-card">Loading accounts…</p> : accounts.length === 0 ? listError ? <p className="state-card state-error">The account list could not be loaded. Use Retry above.</p> : <p className="state-card">No accounts found.</p> : filtered.length === 0 ? <p className="state-card">No accounts match these filters.</p> : <table className="account-table">
        <thead><tr><th>User</th><th>Name</th><th>Role</th><th>Classification</th><th>Status</th><th>Actions</th></tr></thead>
        <tbody>{filtered.map((account) => <tr key={account.id}>
          <td data-label="User"><strong>@{account.username}</strong><small>{account.email || "No email"}</small></td>
          <td data-label="Name">{account.first_name || account.last_name ? `${account.first_name} ${account.last_name}`.trim() : "—"}<small>{account.phone || "No phone"}</small></td>
          <td data-label="Role">{account.is_superuser ? "Superuser" : roleLabels[account.role] ?? account.role}</td>
          <td data-label="Classification">{account.account_type}</td>
          <td data-label="Status"><span className={`account-status ${account.is_active ? "is-active" : "is-inactive"}`}>{account.is_active ? "Active" : "Inactive"}</span></td>
          <td data-label="Actions"><div className="account-actions">{(!account.is_superuser || account.id === currentUser.id) && (account.role !== "admin" || currentUser.is_superuser || account.id === currentUser.id) && <>
            <button className="quiet-button" disabled={busy} onClick={() => { setEditing(account); setCreating(false); setError(""); setSuccess(""); }}>Edit</button>
            {!account.is_superuser && (account.role !== "admin" || currentUser.is_superuser) && account.id !== currentUser.id && account.is_active && <button className="quiet-button" disabled={busy} onClick={() => void sendAccessLink(account, "password_reset")}>Send password reset</button>}
            {!account.is_superuser && (account.role !== "admin" || currentUser.is_superuser) && account.id !== currentUser.id && !account.is_active && !account.is_onboarded && <button className="quiet-button" disabled={busy} onClick={() => void sendAccessLink(account, "invitation")}>Resend invitation</button>}
            {!account.is_superuser && account.id !== currentUser.id && (account.role !== "admin" || currentUser.is_superuser) && (account.is_active || account.is_onboarded) && <button className={account.is_active ? "danger-button" : "quiet-button"} disabled={busy} onClick={() => void setAccountActive(account, !account.is_active)}>{account.is_active ? "Deactivate" : "Activate"}</button>}
          </>}</div></td>
        </tr>)}</tbody>
      </table>}
    </section>
  </main>;
}
