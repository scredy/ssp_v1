"use client";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, Vehicle } from "@/lib/car-api";

type Kind = "general" | "quote" | "appointment" | "test_drive";
function sriLankaMinimumTime() {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Colombo", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(Date.now() + 60_000));
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return `${values.year}-${values.month}-${values.day}T${values.hour}:${values.minute}`;
}
export default function PublicEnquiryForm({ kind, title, description }: { kind: Kind; title: string; description: string }) {
  const search = useSearchParams();
  const [cars, setCars] = useState<Vehicle[]>([]);
  const [selectedKind, setSelectedKind] = useState<Kind>(kind);
  const [form, setForm] = useState({ full_name: "", email: "", phone: "", preferred_contact: "phone", vehicle_reference: kind === "quote" ? "" : search.get("vehicle") ?? "", vehicle_description: kind === "quote" ? search.get("vehicle") ?? "" : "", requested_at: "", message: "" });
  const [key, setKey] = useState(""); const [busy, setBusy] = useState(false); const [loadingCars, setLoadingCars] = useState(true); const [carsError, setCarsError] = useState(""); const [error, setError] = useState(""); const [reference, setReference] = useState("");
  useEffect(() => {
    setKey(crypto.randomUUID());
    if (kind === "quote") { setLoadingCars(false); return; }
    api<Vehicle[]>("/api/cars/").then(setCars).catch((e) => {
      setCars([]);
      setCarsError(e instanceof Error ? `Available vehicles could not be loaded. ${e.message}` : "Available vehicles could not be loaded. Please refresh and try again.");
    }).finally(() => setLoadingCars(false));
  }, [kind]);
  function update(name: string, value: string) { setForm((current) => ({ ...current, [name]: value })); }
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setError(""); setBusy(true);
    try {
      // datetime-local is a Colombo wall time; Django applies the configured Asia/Colombo zone.
      const requested_at = form.requested_at || undefined;
      const result = await api<{reference:string}>("/api/public/enquiries/", { method:"POST", headers:{"Idempotency-Key":key}, body: JSON.stringify({...form, kind:selectedKind, requested_at}) });
      setReference(result.reference); setKey(crypto.randomUUID());
    } catch (e) { setError(e instanceof Error ? e.message : "Your request could not be sent. Please try again."); }
    finally { setBusy(false); }
  }
  if (reference) return <section className="enquiry-success" role="status"><p className="public-eyebrow">REQUEST RECEIVED</p><h2>Thank you. We have your request.</h2><p>Your enquiry reference is <strong>{reference}</strong>.</p>{(kind === "appointment" || kind === "test_drive") && <p>This is a request, not a confirmed booking. SSP will contact you to confirm availability. Your requested time is interpreted as Sri Lanka time.{form.email && <span> A confirmation email will be sent if email delivery is configured.</span>}</p>}<button className="public-button public-button-outline" onClick={() => { setReference(""); setForm({...form, message:"", requested_at:"", vehicle_description:""}); }}>Send another request</button></section>;
  return <section className="enquiry-form-panel"><p className="public-eyebrow">SSP MOTOR TRADING</p><h2>{title}</h2><p>{description}</p><form className="public-enquiry-form" onSubmit={submit}>
    <label>Full name *<input required maxLength={160} value={form.full_name} onChange={e=>update("full_name",e.target.value)} autoComplete="name" /></label>
    <label>Phone{kind === "appointment" || kind === "test_drive" || !form.email || form.preferred_contact === "phone" || form.preferred_contact === "whatsapp" ? " *" : ""}<input type="tel" required={kind === "appointment" || kind === "test_drive" || !form.email || form.preferred_contact === "phone" || form.preferred_contact === "whatsapp"} maxLength={32} value={form.phone} onChange={e=>update("phone",e.target.value)} autoComplete="tel" /></label>
    <label>Email{kind === "appointment" || kind === "test_drive" || !form.phone || form.preferred_contact === "email" ? " *" : ""}<input type="email" required={kind === "appointment" || kind === "test_drive" || !form.phone || form.preferred_contact === "email"} maxLength={254} value={form.email} onChange={e=>update("email",e.target.value)} autoComplete="email" /></label>
    <label>Preferred contact *<select value={form.preferred_contact} onChange={e=>update("preferred_contact",e.target.value)}><option value="phone">Phone</option><option value="whatsapp">WhatsApp</option><option value="email">Email</option></select></label>
    {kind === "quote" ? <label className="enquiry-wide">Vehicle *<input required maxLength={160} value={form.vehicle_description} onChange={e=>update("vehicle_description",e.target.value)} placeholder="Enter make, model, year, or vehicle reference" /></label> : <label className="enquiry-wide">Vehicle (optional){loadingCars ? <span className="enquiry-hint">Loading available vehicles…</span> : <select value={form.vehicle_reference} onChange={e=>update("vehicle_reference",e.target.value)}><option value="">No specific vehicle</option>{cars.map(car=><option key={car.reference} value={car.reference}>{car.manufacture_year} {car.make} {car.model} · {car.reference}</option>)}</select>}{carsError && <span className="enquiry-error" role="alert">{carsError}</span>}</label>}
    {(kind === "appointment" || kind === "test_drive") && <><label>Purpose *<select value={selectedKind} onChange={e=>setSelectedKind(e.target.value as Kind)}><option value="appointment">Showroom appointment</option><option value="test_drive">Test drive</option></select></label><label>Preferred date and time *<input type="datetime-local" required min={sriLankaMinimumTime()} value={form.requested_at} onChange={e=>update("requested_at",e.target.value)} /></label><p className="enquiry-hint enquiry-wide">Choose Sri Lanka time. This is a request only; SSP will contact you to confirm availability.</p></>}
    <label className="enquiry-wide">
      Additional notes
      <textarea rows={4} maxLength={3000} value={form.message} onChange={e=>update("message",e.target.value)} aria-describedby={kind === "quote" ? "exchange-note" : undefined} />
      {kind === "quote" && <small id="exchange-note" className="enquiry-hint">(If you wish to exchange your current vehicle, please mention its make, model, year and condition.)</small>}
    </label>
    {error && <p className="enquiry-error enquiry-wide" role="alert">{error}</p>}
    <button className="public-button public-button-red enquiry-wide" disabled={busy || (kind === "appointment" || kind === "test_drive") && !form.requested_at}>{busy ? "Sending…" : "Submit request"}</button>
  </form></section>;
}
