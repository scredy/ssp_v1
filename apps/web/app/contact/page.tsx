import { socialMetadata } from "@/lib/seo";
import type { Metadata } from "next";
import { COMPANY_CONTACT, emailHref, phoneHref } from "@/lib/site-config";
import { PublicContactActions, PublicPageFrame } from "@/components/public-site";
import { Suspense } from "react";
import PublicEnquiryForm from "@/components/public-enquiry-form";

export const metadata: Metadata = {
  ...socialMetadata("Contact Us | SSP Motor Trading", "Contact SSP Motor Trading about available vehicles using verified configured company contact details.", "/contact"),
 title: "Contact Us", description: "Contact SSP Motor Trading about available vehicles using verified configured company contact details." };

export default function ContactPage() {
  const phone = phoneHref(COMPANY_CONTACT.phone);
  const email = emailHref(COMPANY_CONTACT.email);
  return <PublicPageFrame active="/contact"><main className="public-main contact-main">
    <section className="public-page-heading"><p className="public-eyebrow">CONTACT</p><h1>Let’s talk vehicles.</h1><p>Send an enquiry about a listing or ask our team for more information.</p></section>
    <div className="contact-layout"><section className="contact-panel"><p className="public-eyebrow">GET IN TOUCH</p><h2>Contact SSP Motor Trading</h2><p>Choose one of the verified contact options below. Include a vehicle reference when you enquire about a specific listing.</p><PublicContactActions />
      {(phone || email) && <dl className="contact-detail-list">{phone && <div><dt>Telephone</dt><dd><a href={phone}>{COMPANY_CONTACT.phone}</a></dd></div>}{email && <div><dt>Email</dt><dd><a href={`mailto:${COMPANY_CONTACT.email}`}>{COMPANY_CONTACT.email}</a></dd></div>}</dl>}
    </section><aside className="contact-note"><p className="public-eyebrow">VEHICLE ENQUIRY</p><h2>Found something you like?</h2><p>Open the vehicle page to review specifications and use its enquiry action to include the vehicle reference automatically.</p><a href="/cars" className="public-button public-button-red">Browse vehicles</a></aside></div><div className="contact-enquiry"><Suspense fallback={<p className="public-state">Loading form…</p>}><PublicEnquiryForm kind="general" title="Send a general enquiry" description="Our team will follow up using your preferred contact method." /></Suspense></div>
  </main></PublicPageFrame>;
}
