"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, photoUrl, Vehicle } from "@/lib/car-api";

const money = (value: string) => new Intl.NumberFormat("en-LK", { style: "currency", currency: "LKR", maximumFractionDigits: 0 }).format(Number(value));

export default function CarDetailPage() {
  const { reference } = useParams<{ reference: string }>();
  const [car, setCar] = useState<Vehicle | null>(null);
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

  if (loading) return <main className="inventory-page"><p className="state-card">Loading vehicle details…</p></main>;
  if (error || !car) return <main className="inventory-page"><Link className="text-link" href="/cars">← Back to vehicles</Link><p className="state-card state-error">{error || "This vehicle is not available."}</p></main>;
  return <main className="inventory-page car-detail-page">
    <header className="site-header"><Link className="brand" href="/">SSP<span>Vehicle collection</span></Link><Link className="text-link" href="/cars">← All vehicles</Link></header>
    <div className="detail-heading"><div><p className="eyebrow">{car.reference} · {car.condition}</p><h1>{car.make} {car.model}</h1><p>{car.variant}</p></div><strong className="detail-price">{money(car.asking_price_lkr)}</strong></div>
    {car.photos.length ? <div className="photo-gallery">{car.photos.map((photo, index) => <img key={photo.id} src={photoUrl(photo)} alt={`${car.make} ${car.model} photo ${index + 1}`} />)}</div> : <div className="car-cover car-cover-empty detail-empty">Photos will be added soon</div>}
    <section className="spec-grid" aria-label="Vehicle specifications">
      <div><span>Year</span><strong>{car.manufacture_year}</strong></div><div><span>Mileage</span><strong>{car.mileage_km.toLocaleString()} km</strong></div>
      <div><span>Fuel</span><strong>{car.fuel_type}</strong></div><div><span>Transmission</span><strong>{car.transmission}</strong></div><div><span>Color</span><strong>{car.color}</strong></div>
    </section>
    {car.description ? <section className="description-panel"><h2>About this vehicle</h2><p>{car.description}</p></section> : null}
    <footer className="page-footer"><Link href="/cars">Browse more vehicles</Link></footer>
  </main>;
}
