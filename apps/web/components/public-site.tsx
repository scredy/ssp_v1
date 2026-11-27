"use client";

import Link from "next/link";
import Image from "next/image";
import { useState } from "react";
import { COMPANY_CONTACT, emailHref, phoneHref, whatsappHref } from "@/lib/site-config";

const leftLinks = [{ href: "/", label: "Home" }, { href: "/cars", label: "Vehicles" }, { href: "/finance", label: "Finance" }];
const rightLinks = [{ href: "/track", label: "Track Vehicle" }, { href: "/contact", label: "Contact" }, { href: "/request-quote", label: "Request a quote" }];

export function BrandLogo({ href = "/", className = "", priority = false, source = "/branding/ssp-logo-display.png", imageWidth = 1170, imageHeight = 508 }: { href?: string; className?: string; priority?: boolean; source?: string; imageWidth?: number; imageHeight?: number }) {
  const [loadFailed, setLoadFailed] = useState(false);
  return <Link className={`brand-logo-link ${className}`} href={href} aria-label="SSP Motor Trading home">
    {!loadFailed ? <Image src={source} alt="SSP Motor Trading" width={imageWidth} height={imageHeight} priority={priority} onError={() => setLoadFailed(true)} /> : <span className="brand-logo-fallback">SSP<small>MOTOR TRADING</small></span>}
  </Link>;
}

export function PublicHeader({ active }: { active?: string }) {
  const [open, setOpen] = useState(false);
  return <header className="public-header"><div className="public-header-inner">
    <nav className="public-nav public-nav-left" aria-label="Main navigation">{leftLinks.map((link) => <Link key={link.href} className={active === link.href ? "is-active" : ""} href={link.href}>{link.label}</Link>)}</nav>
    <BrandLogo className="public-brand-logo" source="/branding/ssp-chrome-logo.webp" imageWidth={1721} imageHeight={731} priority />
    <button className="public-menu-toggle" aria-expanded={open} aria-controls="public-mobile-nav" aria-label={open ? "Close navigation" : "Open navigation"} onClick={() => setOpen((value) => !value)}><span aria-hidden="true">{open ? "×" : "☰"}</span></button>
    <nav className="public-nav public-nav-right" aria-label="Customer links">{rightLinks.map((link) => <Link key={link.href} className={active === link.href ? "is-active" : ""} href={link.href}>{link.label}</Link>)}</nav>
    <nav id="public-mobile-nav" className={open ? "public-mobile-nav is-open" : "public-mobile-nav"} aria-label="Mobile navigation">{[...leftLinks, ...rightLinks, { href: "/about", label: "About SSP" }].map((link) => <Link key={link.href} className={active === link.href ? "is-active" : ""} href={link.href} onClick={() => setOpen(false)}>{link.label}</Link>)}</nav>
  </div></header>;
}

export function PublicFooter() {
  return <footer className="public-footer"><div className="public-footer-main"><BrandLogo className="public-footer-logo" /><p>Explore current vehicles and connect with the SSP Motor Trading team.</p><div className="public-footer-links"><Link href="/cars">Vehicle catalogue</Link><Link href="/finance">Finance estimates</Link><Link href="/book-appointment">Appointments</Link><Link href="/request-quote">Request a quote</Link><Link href="/about">About SSP</Link><Link href="/track">Track vehicle</Link><Link href="/contact">Contact</Link><Link className="footer-staff-link" href="/staff/login">Staff sign in</Link></div></div><div className="public-footer-bottom"><span>© {new Date().getFullYear()} SSP Motor Trading</span><span>Finance estimates are illustrative and subject to lender assessment.</span></div></footer>;
}

export function PublicContactActions({ message = "Hello, I would like to enquire about a vehicle." }: { message?: string }) {
  const tel = phoneHref(COMPANY_CONTACT.phone);
  const whatsapp = whatsappHref(COMPANY_CONTACT.whatsapp, message);
  const email = emailHref(COMPANY_CONTACT.email);
  if (!tel && !whatsapp && !email) return <p className="contact-not-configured">Contact options will be available once verified company details are configured.</p>;
  return <div className="contact-actions">
    {tel && <a className="public-button public-button-outline" href={tel}>Call SSP</a>}
    {whatsapp && <a className="public-button public-button-red" href={whatsapp} target="_blank" rel="noreferrer">WhatsApp enquiry</a>}
    {email && <a className="public-button public-button-outline" href={`mailto:${COMPANY_CONTACT.email}`}>Email SSP</a>}
  </div>;
}

export function PublicPageFrame({ children, active, home = false }: { children: React.ReactNode; active?: string; home?: boolean }) {
  return <div className={`public-site${home ? " home-public-site" : ""}`}><PublicHeader active={active} />{children}<PublicFooter /></div>;
}
