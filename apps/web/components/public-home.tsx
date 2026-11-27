"use client";

import Link from "next/link";
import "./homepage-polish.css";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, photoUrl, Vehicle } from "@/lib/car-api";
import { PublicPageFrame } from "@/components/public-site";

const money = (value: string) => new Intl.NumberFormat("en-LK", { style: "currency", currency: "LKR", maximumFractionDigits: 0 }).format(Number(value));
const heroVehicles = [
  { name: "Audi A5", src: "/images/home-audi-a5-ssp.webp" },
  { name: "Land Rover Defender 110", src: "/images/defender-110-silver.webp" },
  { name: "BMW M4", src: "/images/bmw-m4-white.webp" },
  { name: "Mercedes-AMG G63", src: "/images/mercedes-g63-black.webp" },
  { name: "Porsche 911", src: "/images/porsche-911-yellow.webp" },
];
const manufacturers = [
  "Toyota",
  "BMW",
  "Audi",
  "Mercedes-Benz",
  "Land Rover",
  "Honda",
  "Kia",
  "Suzuki",
  "Nissan",
  "Porsche",
  "Lexus",
  "Hyundai",
  "Mitsubishi",
  "Mazda",
  "Volkswagen",
  "Range Rover",
  "Jaguar",
  "Jeep",
  "Ford",
  "BYD",
];

export default function HomeClient() {
  const router = useRouter();
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [condition, setCondition] = useState("");
  const [make, setMake] = useState("");
  const [model, setModel] = useState("");
  const [marqueePaused, setMarqueePaused] = useState(false);
  const [heroPaused, setHeroPaused] = useState(false);
  const [heroVehicle, setHeroVehicle] = useState(0);
  const [heroPhase, setHeroPhase] = useState("initial");
  const [pageVisible, setPageVisible] = useState(true);
  const [searchFocused, setSearchFocused] = useState(false);
  const failedHeroImages = useRef(new Set<string>());
  const vehicleTrack = useRef<HTMLDivElement>(null);
  const vehiclesRequest = useRef<Promise<Vehicle[]> | null>(null);

  useEffect(() => {
    let live = true;
    vehiclesRequest.current ??= api<Vehicle[]>("/api/cars/");
    vehiclesRequest.current.then((data) => { if (live) setVehicles(data); })
      .catch((cause) => { if (live) setError(cause instanceof Error ? cause.message : "Available stock is temporarily unavailable."); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, []);
  useEffect(() => {
    const root = document.querySelector<HTMLElement>(".home-main");
    const targets = root?.querySelectorAll<HTMLElement>(".home-reveal");
    if (!root || !targets?.length || !("IntersectionObserver" in window) || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let observer: IntersectionObserver;
    try {
      observer = new IntersectionObserver((entries) => entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.remove("is-pending");
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      }), { threshold: 0, rootMargin: "0px 0px -24px 0px" });
      root.classList.add("has-reveal-motion");
      targets.forEach((target) => target.classList.add("is-pending"));
      targets.forEach((target) => observer.observe(target));
    } catch {
      root.classList.remove("has-reveal-motion");
      targets.forEach((target) => target.classList.remove("is-pending", "is-visible"));
      return;
    }
    return () => {
      observer.disconnect();
      root.classList.remove("has-reveal-motion");
      targets.forEach((target) => target.classList.remove("is-pending", "is-visible"));
    };
  }, []);
  useEffect(() => {
    if (heroPaused || searchFocused || !pageVisible || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const delay = heroPhase === "initial" ? 1200 : heroPhase === "center" ? 4000 : 800;
    const timer = window.setTimeout(() => {
      if (heroPhase === "initial") { setHeroPhase("center"); return; }
      if (heroPhase === "center") { setHeroPhase("exit"); return; }
      if (heroPhase === "enter") { setHeroPhase("center"); return; }
      let next = (heroVehicle + 1) % heroVehicles.length;
      while (next !== heroVehicle && failedHeroImages.current.has(heroVehicles[next].src)) next = (next + 1) % heroVehicles.length;
      setHeroVehicle(next); setHeroPhase("enter");
    }, delay);
    return () => window.clearTimeout(timer);
  }, [heroPaused, heroVehicle, heroPhase, pageVisible, searchFocused]);
  useEffect(() => {
    const onVisibility = () => setPageVisible(!document.hidden);
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);
  const makes = useMemo(() => [...new Set(vehicles.map((vehicle) => vehicle.make))].sort(), [vehicles]);
  const models = useMemo(() => [...new Set(vehicles.filter((vehicle) => !make || vehicle.make === make).map((vehicle) => vehicle.model))].sort(), [vehicles, make]);
  const featured = vehicles.slice(0, 4);
  const carousel = featured.length > 2;
  const scrollVehicles = (direction: number) => vehicleTrack.current?.scrollBy({ left: direction * vehicleTrack.current.clientWidth * 0.8, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  const goSearch = (event: FormEvent) => {
    event.preventDefault();
    const params = new URLSearchParams();
    if (condition) params.set("condition", condition);
    if (make) params.set("make", make);
    if (model) params.set("model", model);
    router.push(`/cars${params.size ? `?${params.toString()}` : ""}`);
  };
  return <PublicPageFrame active="/" home><main className="public-main home-main">
    <div className="approved-home-stage">
    <section className="approved-hero" aria-label="SSP Motor Trading homepage">
      <div className="approved-hero-watermark" aria-hidden="true">SSP</div>
      <div className={`approved-hero-visual hero-phase-${heroPhase}${heroPaused || searchFocused || !pageVisible ? " is-motion-paused" : ""}`} aria-label={`Featured vehicle: ${heroVehicles[heroVehicle].name}`}>
        <img key={heroVehicles[heroVehicle].src} className="approved-hero-image" src={heroVehicles[heroVehicle].src} alt="" fetchPriority="high" decoding="async" onError={() => {
          failedHeroImages.current.add(heroVehicles[heroVehicle].src);
          let next = (heroVehicle + 1) % heroVehicles.length;
          while (next !== heroVehicle && failedHeroImages.current.has(heroVehicles[next].src)) next = (next + 1) % heroVehicles.length;
          if (next !== heroVehicle) { setHeroVehicle(next); setHeroPhase("enter"); }
        }}/>
      </div>
      <button type="button" className="hero-motion-toggle" aria-pressed={heroPaused} onClick={() => setHeroPaused((paused) => !paused)}>{heroPaused ? "Resume vehicle motion" : "Pause vehicle motion"}</button>
      <span className="sr-only" aria-live="polite">Featured vehicle: {heroVehicles[heroVehicle].name}</span>
    </section>
    <form className="quick-search" onFocus={() => setSearchFocused(true)} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setSearchFocused(false); }} onSubmit={goSearch} aria-label="Search available vehicles">
      <label><small>Condition</small><select value={condition} onChange={(event) => setCondition(event.target.value)}><option value="">New &amp; Used</option>{[...new Set(vehicles.map((vehicle) => vehicle.condition))].sort().map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
      <label><small>Make</small><select value={make} onChange={(event) => {setMake(event.target.value); setModel("");}}><option value="">All Makes</option>{makes.map((value) => <option key={value}>{value}</option>)}</select></label>
      <label><small>Model</small><select value={model} onChange={(event) => setModel(event.target.value)}><option value="">All Models</option>{models.map((value) => <option key={value}>{value}</option>)}</select></label>
      <button type="submit" className="quick-search-submit" aria-label="Search vehicles"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.8" cy="10.8" r="6.3"/><path d="m15.5 15.5 5 5"/></svg></button>
    </form>
    </div>

    <section className="manufacturer-strip" aria-label="Vehicle manufacturers">
      <div className="manufacturer-strip-heading"><p className="public-eyebrow">VEHICLE MANUFACTURERS</p><button type="button" className="marquee-toggle" aria-pressed={marqueePaused} onClick={() => setMarqueePaused((paused) => !paused)}>{marqueePaused ? "Resume motion" : "Pause motion"}</button></div>
      <div tabIndex={0} aria-label="Scrolling vehicle manufacturers" className={`manufacturer-marquee is-moving${marqueePaused ? " is-paused" : ""}`}><div className="manufacturer-marquee-track">{[...manufacturers, ...manufacturers].map((brand, index) => <Link key={`${brand}-${index}`} href={`/cars?make=${encodeURIComponent(brand)}`} aria-label={`Browse ${brand} vehicles`}><span className="manufacturer-logo-circle" aria-hidden="true">
  <img
    src={`/manufacturers/${brand.toLowerCase().replace(/ /g, "-")}.png`}
    alt=""
    width={512}
    height={512}
    decoding="async"
    onError={(event) => {
      event.currentTarget.style.display = "none";
    }}
  />
</span>
<span className="manufacturer-brand-name" aria-hidden="true">
  {brand}
</span></Link>)}</div></div>
    </section>
    <section className="public-section featured-section home-reveal"><div className="public-section-heading"><div><p className="public-eyebrow"><span/> OUR COLLECTION</p><h2>Featured vehicles</h2><p>Current published and available stock.</p></div><div className="featured-heading-actions">{carousel && <div className="carousel-controls"><button type="button" onClick={() => scrollVehicles(-1)} aria-label="Show previous vehicles">‹</button><button type="button" onClick={() => scrollVehicles(1)} aria-label="Show next vehicles">›</button></div>}<Link className="public-text-link" href="/cars">View all vehicles <span aria-hidden="true">→</span></Link></div></div>
      {loading ? <p className="public-state">Loading available vehicles…</p> : error ? <p className="public-state is-error" role="status">{error}</p> : featured.length === 0 ? <div className="stock-empty"><div><p className="public-eyebrow">CURRENT AVAILABILITY</p><h3>No vehicles are listed right now.</h3><p>Tell us what you have in mind and our team can follow up about your enquiry.</p></div><Link href="/request-quote" className="public-button public-button-dark">Request a quote</Link></div> : <div ref={vehicleTrack} className={`public-vehicle-grid${carousel ? " is-carousel" : ""}`}>{featured.map((vehicle) => <article className="public-vehicle-card" key={vehicle.reference}>
        <Link className="vehicle-card-image" href={`/cars/${encodeURIComponent(vehicle.reference)}`} aria-label={`View ${vehicle.make} ${vehicle.model}`}>{vehicle.photos[0] ? <img src={photoUrl(vehicle.photos[0])} alt={`${vehicle.make} ${vehicle.model}`} loading="lazy" decoding="async"/> : <div className="public-vehicle-placeholder">Photo unavailable</div>}<span className="public-stock-badge">Available</span></Link>
        <div className="public-vehicle-copy"><p className="public-card-meta">{vehicle.manufacture_year} <span>·</span> {vehicle.condition}</p><h3>{vehicle.make} {vehicle.model}</h3>{vehicle.variant && <p className="vehicle-card-variant">{vehicle.variant}</p>}<strong>{money(vehicle.asking_price_lkr)}</strong><div className="vehicle-card-actions"><Link href={`/cars/${encodeURIComponent(vehicle.reference)}`}>View details <span>→</span></Link><Link href={`/request-quote?vehicle=${encodeURIComponent(vehicle.reference)}`}>Ask about this vehicle</Link></div></div>
      </article>)}</div>}
    </section>
    <section className="public-section service-section home-reveal"><div className="public-section-heading"><div><p className="public-eyebrow"><span/> OUR SERVICES</p><h2>Support for every step.</h2></div></div><div className="service-grid">
      <article><span className="service-number">01 / SALES</span><h3>Vehicle sales</h3><p>Browse the live catalogue and ask about an available vehicle.</p><Link href="/cars">View available vehicles →</Link></article><article><span className="service-number">02 / IMPORTS</span><h3>Personal imports</h3><p>Have a vehicle in mind? Send an enquiry to discuss your requirements.</p><Link href="/contact">Make an enquiry →</Link></article><article><span className="service-number">03 / EXCHANGE</span><h3>Vehicle exchanges</h3><p>Contact the team to start a conversation about exchanging your vehicle.</p><Link href="/request-quote">Request a conversation →</Link></article><article><span className="service-number">04 / FINANCE</span><h3>Finance assistance</h3><p>Plan with illustrative estimates and request follow-up from the team.</p><Link href="/finance">Explore finance estimates →</Link></article>
    </div></section>
    <section className="business-intro home-reveal"><div><p className="public-eyebrow">ABOUT SSP</p><h2>A considered approach to finding your vehicle.</h2><p>Explore current listings, understand the details, then connect with our team when you are ready to take the next step.</p><Link className="public-text-link" href="/about">Discover SSP →</Link></div><Link href="/about" className="business-logo" aria-label="About SSP Motor Trading"><img src="/branding/ssp-logo-display.png" alt="SSP Motor Trading"/></Link></section>
    <section className="home-contact home-reveal"><div><p className="public-eyebrow">START A CONVERSATION</p><h2>Tell us what you’re looking for.</h2><p>Send a general enquiry, ask for a quote, or arrange a visit.</p></div><div className="home-contact-actions"><Link className="public-button public-button-dark" href="/request-quote">Request a quote</Link><Link className="public-button public-button-outline" href="/book-appointment">Book an appointment</Link><Link className="home-contact-text" href="/contact">General enquiry →</Link></div></section>
  </main></PublicPageFrame>;
}
