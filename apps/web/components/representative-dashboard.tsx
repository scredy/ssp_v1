"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, User } from "@/lib/car-api";

type Dashboard = {
  profile_linked: boolean;
  draft_sales: number;
  confirmed_sales: number;
  handed_over_sales: number;
  pending_commissions: number;
  pending_commission_lkr: string;
  paid_commissions: number;
  paid_commission_lkr: string;
  unrated_commissions: number;
};
type Profile = { reference: string; full_name: string; email: string; phone: string | null; business_status: "active" | "inactive"; system_account_active: boolean };
const money = (value: string | number) => new Intl.NumberFormat("en-LK", { style: "currency", currency: "LKR", maximumFractionDigits: 2 }).format(Number(value || 0));

export default function RepresentativeDashboard({ user }: { user: User }) {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([api<Dashboard>("/api/rep/dashboard/"), api<{ profile: Profile | null }>("/api/representative/profile/")])
      .then(([summary, response]) => { if (active) { setDashboard(summary); setProfile(response.profile); } })
      .catch((e) => { if (active) setError(e instanceof Error ? e.message : "Representative data could not be loaded."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const name = [user.first_name, user.last_name].filter(Boolean).join(" ") || user.username;
  return <div className="rep-dashboard-content">
    <section className="portal-intro"><div><p className="eyebrow">YOUR WORKSPACE</p><h2>Welcome, {name.split(" ")[0]}</h2><p>Review sales assigned to you and commission entries created after finalized handover.</p></div>{profile && <span className={`rep-status is-${profile.business_status}`}>{profile.business_status} profile</span>}</section>
    {error && <p className="reservation-feedback is-error" role="alert">{error}</p>}
    {profile && <section className="rep-self-profile"><div><p className="eyebrow">MY PROFILE</p><h2>{profile.full_name}</h2><p>{profile.reference} · {profile.email || "No email on file"}{profile.phone ? ` · ${profile.phone}` : ""} · {profile.business_status} business status</p>{!profile.system_account_active && <p className="rep-feedback is-error">Your account is inactive. Contact the MD/Manager.</p>}</div></section>}
    {!loading && dashboard && !dashboard.profile_linked && <p className="reservation-hint">Your Rep account has not been linked to a representative profile. Contact the MD/Manager to link it.</p>}
    <section className="staff-dashboard-overview" aria-label="Your sales summary"><div className="staff-dashboard-overview-heading"><div><p className="eyebrow">MY ACTIVITY</p><h2>Sales summary</h2></div><span>Private to your account</span></div>
      <div className="staff-dashboard-metrics">
        <article><span>Draft sales</span><strong>{loading ? "—" : dashboard?.draft_sales ?? 0}</strong><small>Assigned to you</small></article>
        <article><span>Confirmed sales</span><strong>{loading ? "—" : dashboard?.confirmed_sales ?? 0}</strong><small>Awaiting handover</small></article>
        <article><span>Handed over</span><strong>{loading ? "—" : dashboard?.handed_over_sales ?? 0}</strong><small>Handover finalized</small></article>
        <article><span>Unpaid commission entries</span><strong>{loading ? "—" : dashboard?.pending_commissions ?? 0}</strong><small>{dashboard ? money(dashboard.pending_commission_lkr) : "Loading"} · pending or approved, not yet paid</small></article>
        <article><span>Paid commissions</span><strong>{loading ? "—" : dashboard?.paid_commissions ?? 0}</strong><small>{dashboard ? money(dashboard.paid_commission_lkr) : "Loading"} · reversed entries excluded</small></article>
      </div>
    </section>
    {dashboard?.unrated_commissions ? <p className="reservation-hint">{dashboard.unrated_commissions} pending ledger entr{dashboard.unrated_commissions === 1 ? "y has" : "ies have"} no matching active policy rate. Contact the CEO; no rate was assumed.</p> : null}
    <section className="workspace-grid rep-workspace-links" aria-label="Representative tools">
      <article className="workspace-card"><span className="card-index">01</span><h3>My sales</h3><p>Search your assigned sale records and review vehicle delivery progress.</p><Link className="coming-soon" href="/staff/my-sales">Open my sales</Link></article>
      <article className="workspace-card"><span className="card-index">02</span><h3>My commission ledger</h3><p>Review pending entries created from finalized handovers.</p><Link className="coming-soon" href="/staff/my-commissions">Open my commissions</Link></article>
    </section>
  </div>;
}
