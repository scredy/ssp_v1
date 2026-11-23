"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { FINANCE_OPTIONS } from "@/lib/site-config";
import { PublicPageFrame } from "@/components/public-site";

const money = (value: number) => new Intl.NumberFormat("en-LK", { style: "currency", currency: "LKR", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);

export default function FinanceCalculator() {
  const [vehiclePrice, setVehiclePrice] = useState("");
  const [downPayment, setDownPayment] = useState("");
  const [term, setTerm] = useState<string>(FINANCE_OPTIONS[1].id);
  const [calculated, setCalculated] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const value = new URLSearchParams(window.location.search).get("price");
    if (value && Number.isFinite(Number(value)) && Number(value) > 0) setVehiclePrice(value);
  }, []);

  const selected = useMemo(() => FINANCE_OPTIONS.find((option) => option.id === term) ?? FINANCE_OPTIONS[1], [term]);
  const price = Number(vehiclePrice);
  const down = Number(downPayment || 0);
  const financed = price - down;
  const monthly = (financed / 100000) * selected.monthlyPer100k;

  function calculate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setCalculated(false);
    if (!vehiclePrice.trim() || !Number.isFinite(price) || price <= 0) { setError("Enter a vehicle price greater than zero."); return; }
    if (!Number.isFinite(down) || down < 0 || down > price) { setError("Down payment must be zero or more and cannot exceed the vehicle price."); return; }
    if (financed <= 0 || !Number.isFinite(monthly) || monthly <= 0) { setError("Enter a down payment that leaves an amount to finance."); return; }
    setCalculated(true);
  }

  return <PublicPageFrame active="/finance"><main className="public-main finance-main">
    <section className="public-page-heading"><p className="public-eyebrow">ILLUSTRATIVE ESTIMATES</p><h1>Finance calculator</h1><p>Explore an indicative monthly estimate based on the amount you plan to finance.</p></section>
    <div className="finance-layout"><form className="finance-form" onSubmit={calculate} noValidate><p className="public-eyebrow">ESTIMATE YOUR PAYMENT</p><h2>Enter your details</h2>
      <label>Vehicle price (LKR)<input type="number" min="0.01" step="0.01" inputMode="decimal" value={vehiclePrice} onChange={(event) => { setVehiclePrice(event.target.value); setCalculated(false); }} placeholder="e.g. 8,500,000" /></label>
      <label>Down payment (LKR)<input type="number" min="0" step="0.01" inputMode="decimal" value={downPayment} onChange={(event) => { setDownPayment(event.target.value); setCalculated(false); }} placeholder="0" /><span>Cannot be greater than the vehicle price.</span></label>
      <label>Estimate term<select value={term} onChange={(event) => { setTerm(event.target.value); setCalculated(false); }}>{FINANCE_OPTIONS.map((option) => <option key={option.id} value={option.id}>{option.label}{option.months ? ` (${option.months} months)` : ""}</option>)}</select></label>
      {error && <p className="finance-error" role="alert">{error}</p>}
      <button className="public-button public-button-red" type="submit">Calculate estimate</button>
    </form>
    <section className="finance-result" aria-live="polite"><p className="public-eyebrow">ILLUSTRATIVE RESULT</p><h2>Your estimate</h2>
      <dl><div><dt>Vehicle price</dt><dd>{Number.isFinite(price) && price > 0 ? money(price) : "—"}</dd></div><div><dt>Down payment</dt><dd>{Number.isFinite(down) && down >= 0 ? money(down) : "—"}</dd></div><div><dt>Amount financed</dt><dd>{Number.isFinite(financed) && financed > 0 ? money(financed) : "—"}</dd></div><div><dt>Estimate term</dt><dd>{selected.label}</dd></div></dl>
      <div className="monthly-estimate"><span>Estimated monthly amount</span><strong>{calculated ? money(monthly) : "Calculate to view"}</strong></div>
      {calculated && <p className="finance-rate-note">Based on LKR {selected.monthlyPer100k.toLocaleString("en-LK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} per LKR 100,000 financed.</p>}
    </section></div>
    <aside className="finance-disclaimer"><h2>Important information</h2><ul><li>These figures are illustrative planning estimates, not a credit offer or lender quote.</li><li>Actual rates, fees, eligibility and monthly payments depend on lender assessment and final terms.</li><li>Speed draft / OD estimates are not directly comparable to fixed-term instalment products.</li><li>Vehicle availability and final asking price should be confirmed with SSP Motor Trading.</li></ul><Link href="/cars">Browse available vehicles →</Link></aside>
  </main></PublicPageFrame>;
}
