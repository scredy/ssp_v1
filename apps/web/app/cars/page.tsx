"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { api, photoUrl, Vehicle } from "@/lib/car-api";

const money = (value: string) => new Intl.NumberFormat("en-LK", { style: "currency", currency: "LKR", maximumFractionDigits: 0 }).format(Number(value));

export default function CarsPage() {
  const [cars, setCars] = useState<Vehicle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load(query = "") {
    setLoading(true); setError("");
    try { setCars(await api<Vehicle[]>(`/api/cars/${query}`)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to load vehicles."); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const params = new URLSearchParams();
    for (const key of ["search", "year", "fuel", "transmission", "min_price", "max_price"]) {
      const value = String(data.get(key) ?? "").trim(); if (value) params.set(key, value);
    }
    void load(params.size ? `?${params}` : "");
  }

  return <main className="inventory-page public-cars">
    <header className="site-header"><Link className="brand" href="/">SSP<span>Vehicle collection</span></Link><Link className="text-link" href="/staff/login">Staff sign in</Link></header>
    <section className="cars-hero"><p className="eyebrow">FIND YOUR NEXT DRIVE</p><h1>Vehicles for sale</h1><p>Browse our currently available published stock.</p></section>
    <form className="filter-panel" onSubmit={search}>
      <label className="filter-search">Search make or model<input name="search" placeholder="e.g. Toyota Corolla" /></label>
      <label>Year<input name="year" type="number" min="1886" placeholder="Any year" /></label>
      <label>Fuel<select name="fuel"><option value="">Any fuel</option><option value="petrol">Petrol</option><option value="diesel">Diesel</option><option value="hybrid">Hybrid</option><option value="electric">Electric</option><option value="other">Other</option></select></label>
      <label>Transmission<select name="transmission"><option value="">Any</option><option value="automatic">Automatic</option><option value="manual">Manual</option><option value="other">Other</option></select></label>
      <label>Price from (LKR)<input name="min_price" type="number" min="0" step="1000" placeholder="Any" /></label>
      <label>Price to (LKR)<input name="max_price" type="number" min="0" step="1000" placeholder="Any" /></label>
      <button className="primary-button" type="submit">Search stock</button>
    </form>
    <section className="car-results" aria-live="polite">
      {loading ? <p className="state-card">Loading available vehicles…</p> : error ? <div className="state-card state-error"><p>{error}</p><button className="quiet-button" onClick={() => void load()}>Try again</button></div> : cars.length === 0 ? <p className="state-card">No published vehicles match those filters.</p> : <div className="car-grid">{cars.map((car) => <Link className="car-card" href={`/cars/${car.reference}`} key={car.reference}>
        {car.photos[0] ? <img className="car-cover" src={photoUrl(car.photos[0])} alt={`${car.make} ${car.model}`} /> : <div className="car-cover car-cover-empty">SSP</div>}
        <div className="car-card-body"><span className="card-kicker">{car.manufacture_year} · {car.condition}</span><h2>{car.make} {car.model}</h2><p>{car.variant || ""}{car.variant ? " · " : ""}{car.transmission} · {car.fuel_type}</p><strong>{money(car.asking_price_lkr)}</strong></div>
      </Link>)}</div>}
    </section>
    <footer className="page-footer"><Link href="/">SSP</Link><span>Published vehicle details are provided by our team.</span></footer>
  </main>;
}
