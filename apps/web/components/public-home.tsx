"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, photoUrl, Vehicle } from "@/lib/car-api";
import { PublicPageFrame } from "@/components/public-site";

const money = (value: string) => new Intl.NumberFormat("en-LK", { style: "currency", currency: "LKR", maximumFractionDigits: 0 }).format(Number(value));

export default function HomeClient() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    api<Vehicle[]>("/api/cars/").then(setVehicles).catch((cause) => setError(cause instanceof Error ? cause.message : "Available stock is temporarily unavailable."))
      .finally(() => setLoading(false));
  }, []);
  const featured = vehicles.slice(0, 4);
  const heroPhoto = featured.find((vehicle) => vehicle.photos[0])?.photos[0];
  const configuredHero = process.env.NEXT_PUBLIC_HOMEPAGE_HERO_IMAGE;
  const heroImage = configuredHero || (heroPhoto ? photoUrl(heroPhoto) : "/images/home-hero.png");
  const heroStyle = heroImage ? { backgroundImage: `linear-gradient(90deg, rgb(7 9 11 / 92%) 0%, rgb(7 9 11 / 72%) 42%, rgb(7 9 11 / 18%) 100%), url("${heroImage}")` } : undefined;

  return <PublicPageFrame active="/">
    <main className="public-main home-main">
      <section className={`home-hero${heroStyle ? " has-photo" : " no-photo"}`} style={heroStyle}>
        <div className="home-hero-copy"><p className="public-eyebrow">SSP MOTOR TRADING <span>· SRI LANKA</span></p><h1>Quality Vehicles.<br/>Trusted Service.</h1><p>Explore available vehicles, compare the details, and talk with our team about what comes next.</p><div className="home-hero-actions"><Link className="public-button public-button-red" href="/cars">Browse vehicles <span aria-hidden="true">→</span></Link><Link className="public-button public-button-light" href="/request-quote">Request a quote</Link></div></div>
        <div className="hero-side-mark" aria-hidden="true"><span>SSP</span><i></i><small>YOUR NEXT DRIVE<br/>STARTS HERE</small></div>
        <span className="hero-caption">{configuredHero ? "SSP Motor Trading" : heroPhoto ? "Available vehicle · Live inventory" : "SSP Motor Trading"}</span>
      </section>

      <section className="public-section featured-section"><div className="public-section-heading"><div><p className="public-eyebrow">OUR COLLECTION</p><h2>Featured vehicles</h2><p>Current published and available stock.</p></div><Link className="public-text-link" href="/cars">View all vehicles →</Link></div>
        {loading ? <p className="public-state">Loading available vehicles…</p> : error ? <p className="public-state is-error" role="status">{error}</p> : featured.length === 0 ? <div className="stock-empty"><div><p className="public-eyebrow">CURRENT AVAILABILITY</p><h3>No vehicles are listed right now.</h3><p>Tell us what you have in mind and our team can follow up about your enquiry.</p></div><Link href="/request-quote" className="public-button public-button-red">Request a quote</Link></div> : <div className="public-vehicle-grid">{featured.map((vehicle) => <article className="public-vehicle-card" key={vehicle.reference}>
          <Link className="vehicle-card-image" href={`/cars/${vehicle.reference}`} aria-label={`View ${vehicle.make} ${vehicle.model}`}>{vehicle.photos[0] ? <img src={photoUrl(vehicle.photos[0])} alt={`${vehicle.make} ${vehicle.model}`} loading="lazy" decoding="async" /> : <div className="public-vehicle-placeholder">SSP</div>}<span className="public-stock-badge">Available</span></Link>
          <div className="public-vehicle-copy"><p className="public-card-meta">{vehicle.manufacture_year} <span>·</span> {vehicle.fuel_type} <span>·</span> {vehicle.transmission}</p><h3>{vehicle.make} {vehicle.model}</h3>{vehicle.variant && <p className="vehicle-card-variant">{vehicle.variant}</p>}<strong>{money(vehicle.asking_price_lkr)}</strong><div className="vehicle-card-actions"><Link href={`/cars/${vehicle.reference}`}>View details <span>→</span></Link><Link href={`/request-quote?vehicle=${encodeURIComponent(vehicle.reference)}`}>Ask about this vehicle</Link></div></div>
        </article>)}</div>}
      </section>

      <section className="public-section service-section"><div className="public-section-heading"><div><p className="public-eyebrow">THE SSP DIFFERENCE</p><h2>Support for every step.</h2><p>Explore services and send a request to our team.</p></div></div><div className="service-grid">
        <article><span className="service-number">01 / SALES</span><h3>Vehicle sales</h3><p>Browse the live catalogue and ask about an available vehicle.</p><Link href="/cars">View available vehicles →</Link></article>
        <article><span className="service-number">02 / IMPORTS</span><h3>Personal imports</h3><p>Have a vehicle in mind? Send an enquiry to discuss your requirements.</p><Link href="/contact">Make an enquiry →</Link></article>
        <article><span className="service-number">03 / EXCHANGE</span><h3>Vehicle exchanges</h3><p>Contact the team to start a conversation about exchanging your vehicle.</p><Link href="/request-quote">Request a conversation →</Link></article>
        <article><span className="service-number">04 / FINANCE</span><h3>Finance assistance</h3><p>Plan with illustrative estimates and request follow-up from the team.</p><Link href="/finance">Explore finance estimates →</Link></article>
      </div></section>

      <section className="business-intro"><div><p className="public-eyebrow">ABOUT SSP</p><h2>A considered approach to finding your vehicle.</h2><p>Explore current listings, understand the details, then connect with our team when you are ready to take the next step.</p><Link className="public-text-link" href="/about">Discover SSP →</Link></div><div className="business-intro-rule"><span>SSP</span><small>MOTOR TRADING</small></div></section>
      <section className="home-contact"><div><p className="public-eyebrow">START A CONVERSATION</p><h2>Tell us what you’re looking for.</h2><p>Send a general enquiry, ask for a quote, or arrange a visit.</p></div><div className="home-contact-actions"><Link className="public-button public-button-red" href="/request-quote">Request a quote</Link><Link className="public-button public-button-outline" href="/book-appointment">Book an appointment</Link><Link className="home-contact-text" href="/contact">General enquiry →</Link></div></section>
    </main>
  </PublicPageFrame>;
}
