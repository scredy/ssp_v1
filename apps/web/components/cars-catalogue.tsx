"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, photoUrl, Vehicle } from "@/lib/car-api";
import { PublicPageFrame } from "@/components/public-site";

const money = (value: string) => new Intl.NumberFormat("en-LK", { style: "currency", currency: "LKR", maximumFractionDigits: 0 }).format(Number(value));

export default function CarsCatalogue() {
  const [cars, setCars] = useState<Vehicle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [make, setMake] = useState("");
  const [model, setModel] = useState("");
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [fuel, setFuel] = useState("");
  const [transmission, setTransmission] = useState("");
  const [sort, setSort] = useState("latest");

  async function load() {
    setLoading(true); setError("");
    try { setCars(await api<Vehicle[]>("/api/cars/")); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to load vehicles."); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);
  const makes = useMemo(() => [...new Set(cars.map((car) => car.make))].sort(), [cars]);
  const models = useMemo(() => [...new Set(cars.filter((car) => !make || car.make === make).map((car) => car.model))].sort(), [cars, make]);
  const results = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const matching = cars.filter((car) =>
      (!needle || `${car.make} ${car.model} ${car.variant}`.toLowerCase().includes(needle)) &&
      (!make || car.make === make) && (!model || car.model === model) &&
      (!yearFrom || car.manufacture_year >= Number(yearFrom)) && (!yearTo || car.manufacture_year <= Number(yearTo)) &&
      (!minPrice || Number(car.asking_price_lkr) >= Number(minPrice)) && (!maxPrice || Number(car.asking_price_lkr) <= Number(maxPrice)) &&
      (!fuel || car.fuel_type === fuel) && (!transmission || car.transmission === transmission)
    );
    return matching.sort((a, b) => sort === "price-low" ? Number(a.asking_price_lkr) - Number(b.asking_price_lkr)
      : sort === "price-high" ? Number(b.asking_price_lkr) - Number(a.asking_price_lkr)
      : sort === "year-new" ? b.manufacture_year - a.manufacture_year
      : (b.created_at ?? "").localeCompare(a.created_at ?? ""));
  }, [cars, search, make, model, yearFrom, yearTo, minPrice, maxPrice, fuel, transmission, sort]);

  function clearFilters() { setSearch(""); setMake(""); setModel(""); setYearFrom(""); setYearTo(""); setMinPrice(""); setMaxPrice(""); setFuel(""); setTransmission(""); setSort("latest"); }

  return <PublicPageFrame active="/cars"><main className="public-main catalogue-main">
    <nav className="public-breadcrumb" aria-label="Breadcrumb"><Link href="/">Home</Link><span aria-hidden="true">›</span><span aria-current="page">Vehicles</span></nav>
    <div className="catalogue-layout"><aside className="catalogue-filters"><div className="filter-title"><div><p className="public-eyebrow">SEARCH STOCK</p><h2>Filters</h2></div><button type="button" className="filter-clear" onClick={clearFilters}>Clear</button></div>
      <label>Search<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Make or model" /></label>
      <label>Make<select value={make} onChange={(event) => { setMake(event.target.value); setModel(""); }}><option value="">All makes</option>{makes.map((value) => <option key={value}>{value}</option>)}</select></label>
      <label>Model<select value={model} onChange={(event) => setModel(event.target.value)}><option value="">All models</option>{models.map((value) => <option key={value}>{value}</option>)}</select></label>
      <div className="filter-pair"><label>Year from<input type="number" min="1886" value={yearFrom} onChange={(event) => setYearFrom(event.target.value)} placeholder="Any" /></label><label>To<input type="number" min="1886" value={yearTo} onChange={(event) => setYearTo(event.target.value)} placeholder="Any" /></label></div>
      <div className="filter-pair"><label>Price min (LKR)<input type="number" min="0" value={minPrice} onChange={(event) => setMinPrice(event.target.value)} placeholder="Any" /></label><label>Max<input type="number" min="0" value={maxPrice} onChange={(event) => setMaxPrice(event.target.value)} placeholder="Any" /></label></div>
      <label>Fuel<select value={fuel} onChange={(event) => setFuel(event.target.value)}><option value="">All fuel types</option><option value="petrol">Petrol</option><option value="diesel">Diesel</option><option value="hybrid">Hybrid</option><option value="electric">Electric</option><option value="other">Other</option></select></label>
      <label>Transmission<select value={transmission} onChange={(event) => setTransmission(event.target.value)}><option value="">All transmissions</option><option value="automatic">Automatic</option><option value="manual">Manual</option><option value="other">Other</option></select></label>
    </aside>
    <section className="catalogue-results"><div className="catalogue-results-heading"><div className="catalogue-count-heading"><h1>Vehicles ({results.length})</h1><p>Published and available stock</p></div><label>Sort by<select value={sort} onChange={(event) => setSort(event.target.value)}><option value="latest">Latest</option><option value="price-low">Price: low to high</option><option value="price-high">Price: high to low</option><option value="year-new">Year: newest</option></select></label></div>
      {loading ? <p className="public-state">Loading available vehicles…</p> : error ? <div className="public-state is-error" role="alert"><p>{error}</p><button className="public-button public-button-outline" onClick={() => void load()}>Try again</button></div> : results.length === 0 ? <p className="public-state">{cars.length === 0 ? "No vehicles are currently listed. Please check back soon." : "No available vehicles match your search. Adjust the filters to see more stock."}</p> : <div className="public-vehicle-grid catalogue-grid">{results.map((car) => <Link className="public-vehicle-card" href={`/cars/${car.reference}`} key={car.reference}>
        {car.photos[0] ? <img src={photoUrl(car.photos[0])} alt={`${car.make} ${car.model}`} loading="lazy" decoding="async" /> : <div className="public-vehicle-placeholder">SSP</div>}
        <div className="public-vehicle-copy"><span className="public-stock-badge">Available</span><p className="public-card-meta">{car.manufacture_year} · {car.condition}</p><h2>{car.make} {car.model}</h2><p>{car.variant ? `${car.variant} · ` : ""}{car.transmission} · {car.fuel_type}</p><strong>{money(car.asking_price_lkr)}</strong></div>
      </Link>)}</div>}
    </section></div>
  </main></PublicPageFrame>;
}
