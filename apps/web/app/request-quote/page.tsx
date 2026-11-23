import type { Metadata } from "next";
import { Suspense } from "react";
import { PublicPageFrame } from "@/components/public-site";
import PublicEnquiryForm from "@/components/public-enquiry-form";
export const metadata: Metadata = { title: "Request a Quote", description: "Request vehicle pricing information from SSP Motor Trading." };
export default function Page() { return <PublicPageFrame><main className="public-main contact-main"><div className="public-page-heading"><h1>Request a quote</h1><p>Send a request to our team for follow-up. This does not generate a formal quotation.</p></div><Suspense fallback={<p className="public-state">Loading form…</p>}><PublicEnquiryForm kind="quote" title="Tell us what you are looking for" description="A team member will follow up about your request." /></Suspense></main></PublicPageFrame>; }
