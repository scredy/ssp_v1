"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, photoUrl, User, Vehicle } from "@/lib/car-api";

const blank: Partial<Vehicle> = { make: "", model: "", variant: "", manufacture_year: new Date().getFullYear(), mileage_km: 0, fuel_type: "petrol", transmission: "automatic", color: "", condition: "used", internal_identifier: "", asking_price_lkr: "", description: "", visibility: "draft" };
const currency = (value: string) => new Intl.NumberFormat("en-LK", { style: "currency", currency: "LKR", maximumFractionDigits: 0 }).format(Number(value));
const allowedRoles = ["staff", "ceo", "manager"];

export default function StaffInventoryPage() {
  const [user, setUser] = useState<User | null>(null);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Vehicle | null>(null);
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const canManage = user?.role === "staff";

  async function refresh() { setVehicles(await api<Vehicle[]>("/api/staff/inventory/")); }
  useEffect(() => {
    api<User>("/api/auth/me/").then(async (current) => {
      if (!allowedRoles.includes(current.role)) throw new Error("Your role does not have inventory access.");
      setUser(current); setVehicles(await api<Vehicle[]>("/api/staff/inventory/"));
    }).catch((cause) => setError(cause instanceof Error ? cause.message : "Unable to load inventory."))
      .finally(() => setLoading(false));
  }, []);

  const visible = useMemo(() => vehicles.filter((v) => `${v.make} ${v.model} ${v.variant} ${v.reference}`.toLowerCase().includes(query.toLowerCase())), [vehicles, query]);

  async function saveVehicle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!canManage) return;
    setBusy(true); setError(""); setNotice("");
    const form = new FormData(event.currentTarget);
    const photoFiles = form.getAll("photos").filter((f): f is File => f instanceof File && f.size > 0);
    const payload = Object.fromEntries(["make", "model", "variant", "manufacture_year", "mileage_km", "fuel_type", "transmission", "color", "condition", "internal_identifier", "asking_price_lkr", "description", "visibility"].map((key) => [key, form.get(key)]));
    try {
      if (Number(payload.manufacture_year) < 1886 || Number(payload.manufacture_year) > new Date().getFullYear() + 1) throw new Error("Enter a valid manufacture year.");
      if (Number(payload.mileage_km) < 0 || Number(payload.asking_price_lkr) <= 0) throw new Error("Mileage must be zero or more and price must be greater than zero.");
      if (photoFiles.length > 10) throw new Error("Choose no more than 10 photos at a time.");
      let saved: Vehicle;
      if (editing) saved = await api<Vehicle>(`/api/staff/inventory/${editing.reference}/`, { method: "PATCH", body: JSON.stringify(payload) });
      else saved = await api<Vehicle>("/api/staff/inventory/", { method: "POST", body: JSON.stringify(payload) });
      if (photoFiles.length) {
        const photoData = new FormData(); photoFiles.forEach((file) => photoData.append("photos", file));
        saved = await api<Vehicle>(`/api/staff/inventory/${saved.reference}/photos/`, { method: "POST", body: photoData });
      }
      await refresh(); setEditing(null); setCreating(false); setNotice(`Saved ${saved.reference}.`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to save this vehicle."); }
    finally { setBusy(false); }
  }

  async function togglePublication(vehicle: Vehicle) {
    setBusy(true); setError(""); setNotice("");
    try { await api(`/api/staff/inventory/${vehicle.reference}/`, { method: "PATCH", body: JSON.stringify({ visibility: vehicle.visibility === "published" ? "draft" : "published" }) }); await refresh(); setNotice(`${vehicle.reference} is now ${vehicle.visibility === "published" ? "a draft" : "published"}.`); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to change publication."); }
    finally { setBusy(false); }
  }

  async function removePhoto(vehicle: Vehicle, photoId: number) {
    if (!canManage) return;
    setBusy(true); setError("");
    try { await api(`/api/staff/inventory/${vehicle.reference}/photos/${photoId}/`, { method: "DELETE" }); await refresh(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to remove photo."); }
    finally { setBusy(false); }
  }

  if (loading) return <main className="inventory-page"><p className="state-card">Loading your session and inventory…</p></main>;
  if (error && !user) return <main className="inventory-page"><Link href="/staff">← Staff portal</Link><p className="state-card state-error" role="alert">{error}</p><Link href="/staff/login">Sign in</Link></main>;
  return <main className="inventory-page staff-inventory">
    <header className="site-header"><div><Link className="brand" href="/staff">SSP<span>Staff portal</span></Link></div><nav><Link href="/cars">Public stock</Link><Link href="/staff">Workspace</Link></nav></header>
    <section className="cars-hero"><p className="eyebrow">{canManage ? "STAFF WORKSPACE" : "INVENTORY REVIEW"}</p><h1>Vehicle inventory</h1><p>{canManage ? "Create vehicle records, manage photos and control what visitors can see." : "Review vehicle records. Your role has read-only access."}</p></section>
    {error && <p className="inline-error" role="alert">{error}</p>}{notice && <p className="inline-notice" role="status">{notice}</p>}
    <section className="inventory-toolbar"><label className="filter-search">Search inventory<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Make, model or reference" /></label>{canManage && <button className="primary-button" onClick={() => { setEditing(null); setCreating(true); setError(""); }}>+ Add vehicle</button>}</section>
    {creating || editing ? <form className="vehicle-form" onSubmit={saveVehicle} key={editing?.reference ?? "new"}>
      <div className="form-heading"><div><p className="eyebrow">{editing ? `EDIT ${editing.reference}` : "NEW LISTING"}</p><h2>{editing ? "Update vehicle" : "Add a vehicle"}</h2></div><button type="button" className="quiet-button" onClick={() => { setEditing(null); setCreating(false); }}>Cancel</button></div>
      <div className="vehicle-form-grid">
        <label>Make<input name="make" required maxLength={80} defaultValue={editing?.make ?? blank.make} /></label>
        <label>Model<input name="model" required maxLength={100} defaultValue={editing?.model ?? blank.model} /></label>
        <label>Variant / grade<input name="variant" maxLength={120} defaultValue={editing?.variant ?? blank.variant} /></label>
        <label>Manufacture year<input name="manufacture_year" type="number" required min="1886" max={new Date().getFullYear() + 1} defaultValue={editing?.manufacture_year ?? blank.manufacture_year} /></label>
        <label>Mileage (km)<input name="mileage_km" type="number" required min="0" max="2000000" defaultValue={editing?.mileage_km ?? blank.mileage_km} /></label>
        <label>Fuel type<select name="fuel_type" defaultValue={editing?.fuel_type ?? blank.fuel_type}><option value="petrol">Petrol</option><option value="diesel">Diesel</option><option value="hybrid">Hybrid</option><option value="electric">Electric</option><option value="other">Other</option></select></label>
        <label>Transmission<select name="transmission" defaultValue={editing?.transmission ?? blank.transmission}><option value="automatic">Automatic</option><option value="manual">Manual</option><option value="other">Other</option></select></label>
        <label>Color<input name="color" required maxLength={50} defaultValue={editing?.color ?? blank.color} /></label>
        <label>Condition<select name="condition" defaultValue={editing?.condition ?? blank.condition}><option value="new">New</option><option value="used">Used</option><option value="reconditioned">Reconditioned</option></select></label>
        <label>Chassis / VIN / stock ID <span className="field-note">Internal only; never shown publicly.</span><input name="internal_identifier" required maxLength={100} defaultValue={editing?.internal_identifier ?? ""} /></label>
        <label>Asking price (LKR)<input name="asking_price_lkr" type="number" required min="0.01" step="0.01" defaultValue={editing?.asking_price_lkr ?? ""} /></label>
        <label>Publication<select name="visibility" defaultValue={editing?.visibility ?? "draft"}><option value="draft">Draft (private)</option><option value="published">Published</option></select></label>
        <label className="form-wide">Description<textarea name="description" rows={4} defaultValue={editing?.description ?? ""} /></label>
        <label className="form-wide">Add photos (JPEG, PNG or WebP, up to 8 MB each)<input name="photos" type="file" accept="image/jpeg,image/png,image/webp" multiple /></label>
      </div>
      {editing?.photos.length ? <div className="staff-photo-list"><p>Current photos</p>{editing.photos.map((photo) => <div key={photo.id}><img src={photoUrl(photo)} alt="Vehicle" />{canManage && <button type="button" className="text-button" disabled={busy} onClick={() => void removePhoto(editing, photo.id)}>Remove</button>}</div>)}</div> : null}
      <button className="primary-button" disabled={busy}>{busy ? "Saving…" : editing ? "Save changes" : "Create vehicle"}</button>
    </form> : null}
    <section className="inventory-list" aria-live="polite">
      {vehicles.length === 0 ? <p className="state-card">No vehicle records yet.{canManage ? " Add a vehicle to start building inventory." : ""}</p> : visible.length === 0 ? <p className="state-card">No vehicles match your search.</p> : visible.map((vehicle) => <article className="inventory-row" key={vehicle.reference}>
        <div className="inventory-row-main">{vehicle.photos[0] ? <img className="inventory-thumb" src={photoUrl(vehicle.photos[0])} alt="" /> : <div className="inventory-thumb thumb-empty">SSP</div>}<div><span className={`visibility-pill visibility-${vehicle.visibility}`}>{vehicle.visibility}</span><h2>{vehicle.manufacture_year} {vehicle.make} {vehicle.model}</h2><p>{vehicle.reference} · {vehicle.variant || "Standard"} · {vehicle.mileage_km.toLocaleString()} km</p><strong>{currency(vehicle.asking_price_lkr)}</strong></div></div>
        <div className="row-actions">{canManage && <><button className="quiet-button" disabled={busy} onClick={() => { setEditing(vehicle); setCreating(false); setError(""); }}>Edit</button><button className="primary-button" disabled={busy} onClick={() => void togglePublication(vehicle)}>{vehicle.visibility === "published" ? "Unpublish" : "Publish"}</button></>}</div>
      </article>)}
    </section>
  </main>;
}
