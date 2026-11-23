"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, photoUrl, Vehicle } from "@/lib/car-api";
import { PublicContactActions, PublicPageFrame } from "@/components/public-site";

const money = (value: string) => new Intl.NumberFormat("en-LK", { style: "currency", currency: "LKR", maximumFractionDigits: 0 }).format(Number(value));

export default function VehicleDetail({ reference }: { reference: string }) {
  const [car, setCar] = useState<Vehicle | null>(null);
  const [activePhoto, setActivePhoto] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<Vehicle>(`/api/cars/${encodeURIComponent(reference)}/`)
      .then((result) => { if (active) setCar(result); })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : "Unable to load this vehicle."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [reference]);

  if (loading) return <PublicPageFrame active="/cars"><main className="public-main"><p className="public-state">Loading vehicle details…</p></main></PublicPageFrame>;
  if (error || !car) return <PublicPageFrame active="/cars"><main className="public-main"><Link className="public-text-link" href="/cars">← All vehicles</Link><p className="public-state is-error">{error || "This vehicle is not available."}</p></main></PublicPageFrame>;
  const heroPhoto = car.photos[activePhoto];
  return <PublicPageFrame active="/cars"><main className="public-main vehicle-detail-main">
    <div className="public-breadcrumb"><Link href="/">Home</Link><span>/</span><Link href="/cars">Vehicles</Link><span>/</span><span>{car.make} {car.model}</span></div>
    <section className="vehicle-detail-heading"><div><p className="public-eyebrow">AVAILABLE VEHICLE</p><h1>{car.manufacture_year} {car.make} {car.model}</h1><p>{car.variant || ""}{car.variant ? " · " : ""}{car.transmission} · {car.fuel_type}</p></div><div className="vehicle-price"><span>Asking price</span><strong>{money(car.asking_price_lkr)}</strong><Link className="public-text-link" href={`/finance?price=${encodeURIComponent(car.asking_price_lkr)}`}>Estimate finance →</Link></div></section>
    <section className="vehicle-detail-grid"><div className="vehicle-gallery"><div className="vehicle-main-photo">{heroPhoto ? <img src={photoUrl(heroPhoto)} alt={`${car.make} ${car.model}`} fetchPriority="high" decoding="async" /> : <div className="public-vehicle-placeholder">SSP</div>}<span className="public-stock-badge">Available</span></div>
        {car.photos.length > 1 && <div className="vehicle-thumbnails" aria-label="Vehicle photographs">{car.photos.map((photo, index) => <button key={photo.id} className={activePhoto === index ? "is-active" : ""} onClick={() => setActivePhoto(index)} aria-label={`View vehicle photo ${index + 1}`} aria-pressed={activePhoto === index}><img src={photoUrl(photo)} alt="" loading="lazy" decoding="async" /></button>)}</div>}
      </div><aside className="vehicle-contact-panel"><p className="public-eyebrow">HAVE A QUESTION?</p><h2>Enquire about this vehicle</h2><p>Contact SSP Motor Trading with this vehicle reference: <strong>{car.reference}</strong>.</p><div className="contact-actions"><Link className="public-button public-button-red" href={`/book-appointment?vehicle=${encodeURIComponent(car.reference)}`}>Book appointment / test drive</Link><Link className="public-button public-button-outline" href={`/request-quote?vehicle=${encodeURIComponent(car.reference)}`}>Request a quote</Link></div><PublicContactActions message={`Hello, I would like to enquire about the ${car.manufacture_year} ${car.make} ${car.model} (${car.reference}).`} /><Link className="public-button public-button-outline finance-link" href={`/finance?price=${encodeURIComponent(car.asking_price_lkr)}`}>Calculate an estimate</Link></aside></section>
    <section className="vehicle-spec-section"><div className="public-section-heading"><div><p className="public-eyebrow">VEHICLE DETAILS</p><h2>Specifications</h2></div></div><dl className="vehicle-specs"><div><dt>Year</dt><dd>{car.manufacture_year}</dd></div><div><dt>Mileage</dt><dd>{car.mileage_km.toLocaleString()} km</dd></div><div><dt>Fuel</dt><dd>{car.fuel_type}</dd></div><div><dt>Transmission</dt><dd>{car.transmission}</dd></div><div><dt>Condition</dt><dd>{car.condition}</dd></div><div><dt>Color</dt><dd>{car.color}</dd></div></dl>
      {car.description && <div className="vehicle-description"><h3>Description</h3><p>{car.description}</p></div>}
    </section>
    <p className="vehicle-detail-disclaimer">Specifications and asking price are supplied by SSP Motor Trading and may be subject to confirmation.</p>
  </main></PublicPageFrame>;
}
