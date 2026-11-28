import { socialMetadata } from "@/lib/seo";
import type { Metadata } from "next";
import Link from "next/link";
import { PublicPageFrame } from "@/components/public-site";

export const metadata: Metadata = {
  ...socialMetadata("About Us | SSP Motor Trading", "Learn about SSP Motor Trading and explore currently available vehicle listings.", "/about"),
 title: "About Us", description: "Learn about SSP Motor Trading and explore currently available vehicle listings." };

export default function AboutPage() {
  return <PublicPageFrame active="/about"><main className="public-main about-main">
    <section className="public-page-heading"><p className="public-eyebrow">ABOUT SSP</p><h1>SSP Motor Trading</h1><p>A clear place to explore current vehicle listings and learn more before making an enquiry.</p></section>
    <section className="about-story"><div><p className="public-eyebrow">OUR APPROACH</p><h2>Useful details for your next decision.</h2><p>SSP Motor Trading’s public catalogue presents current available vehicles with their key specifications, photographs and asking prices. Each listing is connected to live inventory so published stock can be reviewed as it changes.</p><p>When you find a vehicle of interest, use the configured contact options to ask the SSP team about its details and availability.</p><Link className="public-button public-button-red" href="/cars">Explore available vehicles</Link></div><div className="about-mark"><span>SSP</span><small>MOTOR TRADING</small><div className="about-rule" /></div></section>
    <section className="about-services"><p className="public-eyebrow">WHAT YOU CAN DO HERE</p><div className="about-service-grid"><article><h2>Browse live stock</h2><p>Search published vehicles that are currently available.</p></article><article><h2>Review the details</h2><p>Compare vehicle specifications, photographs and asking prices.</p></article><article><h2>Plan an estimate</h2><p>Use illustrative finance estimates as a starting point for a lender discussion.</p></article></div></section>
  </main></PublicPageFrame>;
}
