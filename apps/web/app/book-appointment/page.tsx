import type { Metadata } from "next";
import { Suspense } from "react";
import { PublicPageFrame } from "@/components/public-site";
import PublicEnquiryForm from "@/components/public-enquiry-form";
export const metadata: Metadata = { title: "Book an Appointment", description: "Request a showroom appointment or vehicle test drive with SSP Motor Trading." };
export default function Page() { return <PublicPageFrame><main className="public-main contact-main"><div className="public-page-heading"><p className="public-eyebrow">VISIT SSP</p><h1>Book an appointment</h1><p>Choose a preferred time. Our team will contact you to confirm availability.</p></div><Suspense fallback={<p className="public-state">Loading form…</p>}><PublicEnquiryForm kind="appointment" title="Request a showroom visit" description="Tell us when you would like to visit. Your request is not confirmed until we contact you." /></Suspense></main></PublicPageFrame>; }
