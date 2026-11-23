"use client";

import Link from "next/link";
import { Fragment } from "react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, photoUrl, User, Vehicle } from "@/lib/car-api";
import { BrandLogo } from "@/components/public-site";

const blank: Partial<Vehicle> = { make: "", model: "", variant: "", manufacture_year: new Date().getFullYear(), mileage_km: 0, fuel_type: "petrol", transmission: "automatic", color: "", condition: "used", internal_identifier: "", asking_price_lkr: "", description: "", visibility: "draft", status: "available" };
const currency = (value: string) => new Intl.NumberFormat("en-LK", { style: "currency", currency: "LKR", maximumFractionDigits: 0 }).format(Number(value));
const allowedRoles = ["staff", "ceo", "manager"];
const statuses = ["available", "reserved", "sold", "handed_over", "archived"] as const;
const statusLabels: Record<string, string> = { available: "Available", reserved: "Reserved", sold: "Sold", handed_over: "Handed Over", archived: "Archived" };
const roleLabels: Record<string, string> = { staff: "Staff", ceo: "CEO", manager: "MD/Manager" };

export default function StaffInventoryPage() {
  const [user, setUser] = useState<User | null>(null);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [query, setQuery] = useState("");
  const [availability, setAvailability] = useState("");
  const [publication, setPublication] = useState("");
  const [makeFilter, setMakeFilter] = useState("");
  const [conditionFilter, setConditionFilter] = useState("");
  const [editing, setEditing] = useState<Vehicle | null>(null);
  const [creating, setCreating] = useState(false);
  const [details, setDetails] = useState<string | null>(null);
  const [photoFiles, setPhotoFiles] = useState<File[]>([]);
  const [photoPreviews, setPhotoPreviews] = useState<string[]>([]);
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

  useEffect(() => {
    const urls = photoFiles.map((file) => URL.createObjectURL(file));
    setPhotoPreviews(urls);
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, [photoFiles]);

  const makes = useMemo(() => [...new Set(vehicles.map((vehicle) => vehicle.make))].sort(), [vehicles]);
  const filtered = useMemo(() => vehicles.filter((vehicle) => {
    const needle = query.trim().toLowerCase();
    return (!needle || `${vehicle.reference} ${vehicle.make} ${vehicle.model}`.toLowerCase().includes(needle)) &&
      (!availability || vehicle.status === availability) &&
      (!publication || vehicle.visibility === publication) &&
      (!makeFilter || vehicle.make === makeFilter) &&
      (!conditionFilter || vehicle.condition === conditionFilter);
  }), [vehicles, query, availability, publication, makeFilter, conditionFilter]);

  async function saveVehicle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!canManage) return;
    setBusy(true); setError(""); setNotice("");
    const form = new FormData(event.currentTarget);
    const payload = Object.fromEntries(["make", "model", "variant", "manufacture_year", "mileage_km", "fuel_type", "transmission", "color", "condition", "internal_identifier", "asking_price_lkr", "description", "visibility"].map((key) => [key, form.get(key)]));
    try {
      if (Number(payload.manufacture_year) < 1886 || Number(payload.manufacture_year) > new Date().getFullYear() + 1) throw new Error("Enter a valid manufacture year.");
      if (Number(payload.mileage_km) < 0 || Number(payload.mileage_km) > 2000000 || Number(payload.asking_price_lkr) <= 0) throw new Error("Check mileage and enter a price greater than zero.");
      if (photoFiles.length + (editing?.photos.length ?? 0) > 10) throw new Error("A vehicle can have at most 10 photos.");
      let saved: Vehicle;
      if (editing) saved = await api<Vehicle>(`/api/staff/inventory/${editing.reference}/`, { method: "PATCH", body: JSON.stringify(payload) });
      else saved = await api<Vehicle>("/api/staff/inventory/", { method: "POST", body: JSON.stringify(payload) });
      if (photoFiles.length) {
        const photoData = new FormData(); photoFiles.forEach((file) => photoData.append("photos", file));
        saved = await api<Vehicle>(`/api/staff/inventory/${saved.reference}/photos/`, { method: "POST", body: photoData });
      }
      await refresh(); setEditing(null); setCreating(false); setPhotoFiles([]); setNotice(`Saved ${saved.reference}.`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to save this vehicle."); }
    finally { setBusy(false); }
  }

  async function togglePublication(vehicle: Vehicle) {
    const publishing = vehicle.visibility !== "published";
    if (publishing && vehicle.status !== "available") { setError("Only available vehicles can be published as public stock."); return; }
    setBusy(true); setError(""); setNotice("");
    try { await api(`/api/staff/inventory/${vehicle.reference}/`, { method: "PATCH", body: JSON.stringify({ visibility: publishing ? "published" : "draft" }) }); await refresh(); setNotice(`${vehicle.reference} is now ${publishing ? "published" : "a draft"}.`); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to change publication."); }
    finally { setBusy(false); }
  }

  async function changeStatus(vehicle: Vehicle, next: "available" | "archived") {
    const action = next === "archived" ? "Archive" : "Restore";
    const message = next === "archived" ? `Archive ${vehicle.reference}? It will be removed from public available stock.` : `Restore ${vehicle.reference} to available stock?`;
    if (!window.confirm(message)) return;
    setBusy(true); setError(""); setNotice("");
    try { await api(`/api/staff/inventory/${vehicle.reference}/`, { method: "PATCH", body: JSON.stringify({ status: next }) }); await refresh(); setNotice(`${vehicle.reference} was ${next === "archived" ? "archived" : "restored"}.`); }
    catch (cause) { setError(cause instanceof Error ? cause.message : `Unable to ${action.toLowerCase()} this vehicle.`); }
    finally { setBusy(false); }
  }

  async function removePhoto(vehicle: Vehicle, photoId: number) {
    if (!canManage) return;
    setBusy(true); setError("");
    try { await api(`/api/staff/inventory/${vehicle.reference}/photos/${photoId}/`, { method: "DELETE" }); await refresh(); setEditing((current) => current?.reference === vehicle.reference ? { ...current, photos: current.photos.filter((photo) => photo.id !== photoId) } : current); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to remove photo."); }
    finally { setBusy(false); }
  }

  if (loading) return <main className="inventory-page"><p className="state-card">Loading your session and inventory…</p></main>;
  if (error && !user) return <main className="inventory-page"><Link href="/staff">← Staff portal</Link><p className="state-card state-error" role="alert">{error}</p><Link href="/staff/login">Sign in</Link></main>;
  const counts = Object.fromEntries(statuses.map((status) => [status, vehicles.filter((vehicle) => vehicle.status === status).length]));
  return <main className="inventory-page staff-inventory inventory-portal">
    <header className="site-header staff-brand-header"><BrandLogo href="/staff" className="staff-page-logo" priority /><span className="staff-brand-caption">{roleLabels[user?.role ?? "staff"]} PORTAL</span><nav><Link href="/cars">Public stock</Link><Link href="/staff">Workspace</Link></nav></header>
    <section className="cars-hero"><p className="eyebrow">{canManage ? "STOCK MANAGEMENT" : "INVENTORY REVIEW"}</p><h1>Vehicle inventory</h1><p>{canManage ? "Manage vehicle records, stock status and public listings." : "Review vehicle records. Your role has read-only access."}</p></section>
    <section className="inventory-stats" aria-label="Inventory statistics">
      {statuses.map((status) => <div key={status}><span>{statusLabels[status]}</span><strong>{counts[status]}</strong></div>)}
      <div><span>Published</span><strong>{vehicles.filter((vehicle) => vehicle.visibility === "published").length}</strong></div>
      <div><span>Draft</span><strong>{vehicles.filter((vehicle) => vehicle.visibility === "draft").length}</strong></div>
    </section>
    {error && <p className="inventory-message is-error" role="alert">{error}</p>}{notice && <p className="inventory-message is-success" role="status">{notice}</p>}
    <section className="inventory-filters" aria-label="Filter inventory">
      <label className="inventory-search">Search<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Reference, make or model" /></label>
      <label>Availability<select value={availability} onChange={(event) => setAvailability(event.target.value)}><option value="">All statuses</option>{statuses.map((status) => <option key={status} value={status}>{statusLabels[status]}</option>)}</select></label>
      <label>Publication<select value={publication} onChange={(event) => setPublication(event.target.value)}><option value="">All listings</option><option value="published">Published</option><option value="draft">Draft</option></select></label>
      <label>Make<select value={makeFilter} onChange={(event) => setMakeFilter(event.target.value)}><option value="">All makes</option>{makes.map((make) => <option key={make}>{make}</option>)}</select></label>
      <label>Condition<select value={conditionFilter} onChange={(event) => setConditionFilter(event.target.value)}><option value="">All conditions</option><option value="new">New</option><option value="used">Used</option><option value="reconditioned">Reconditioned</option></select></label>
      {canManage && <button className="inventory-primary" onClick={() => { setEditing(null); setCreating(true); setPhotoFiles([]); setError(""); setNotice(""); }}>+ Add vehicle</button>}
    </section>
    {(creating || editing) && <form className="vehicle-form inventory-form" onSubmit={saveVehicle} key={editing?.reference ?? "new"}>
      <div className="form-heading"><div><p className="eyebrow">{editing ? `EDIT ${editing.reference}` : "NEW VEHICLE"}</p><h2>{editing ? "Update vehicle details" : "Add vehicle"}</h2></div><button type="button" className="inventory-secondary" onClick={() => { setEditing(null); setCreating(false); setPhotoFiles([]); }}>Cancel</button></div>
      <div className="vehicle-form-grid">
        <label>Make<input name="make" required maxLength={80} defaultValue={editing?.make ?? blank.make} /></label><label>Model<input name="model" required maxLength={100} defaultValue={editing?.model ?? blank.model} /></label><label>Variant / grade<input name="variant" maxLength={120} defaultValue={editing?.variant ?? blank.variant} /></label>
        <label>Manufacture year<input name="manufacture_year" type="number" required min="1886" max={new Date().getFullYear() + 1} defaultValue={editing?.manufacture_year ?? blank.manufacture_year} /></label><label>Mileage (km)<input name="mileage_km" type="number" required min="0" max="2000000" defaultValue={editing?.mileage_km ?? blank.mileage_km} /></label>
        <label>Fuel type<select name="fuel_type" defaultValue={editing?.fuel_type ?? blank.fuel_type}><option value="petrol">Petrol</option><option value="diesel">Diesel</option><option value="hybrid">Hybrid</option><option value="electric">Electric</option><option value="other">Other</option></select></label>
        <label>Transmission<select name="transmission" defaultValue={editing?.transmission ?? blank.transmission}><option value="automatic">Automatic</option><option value="manual">Manual</option><option value="other">Other</option></select></label><label>Color<input name="color" required maxLength={50} defaultValue={editing?.color ?? blank.color} /></label>
        <label>Condition<select name="condition" defaultValue={editing?.condition ?? blank.condition}><option value="new">New</option><option value="used">Used</option><option value="reconditioned">Reconditioned</option></select></label><label>Chassis / VIN / stock ID<input name="internal_identifier" required maxLength={100} defaultValue={editing?.internal_identifier ?? ""} /><span className="inventory-help">Private; not shown in public listings.</span></label>
        <label>Asking price (LKR)<input name="asking_price_lkr" type="number" required min="0.01" step="0.01" defaultValue={editing?.asking_price_lkr ?? ""} /></label><label>Publication<select name="visibility" defaultValue={editing?.visibility ?? "draft"}><option value="draft">Draft</option><option value="published">Published</option></select></label>
        <label className="form-wide">Description<textarea name="description" rows={3} defaultValue={editing?.description ?? ""} /></label>
        {canManage && <label className="form-wide">Add photographs<input name="photos" type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(event) => setPhotoFiles(Array.from(event.currentTarget.files ?? []))} /><span className="inventory-help">JPEG, PNG or WebP, up to 8 MB each; 10 photos per vehicle.</span></label>}
      </div>
      {photoPreviews.length > 0 && <section className="photo-preview-grid" aria-label="Selected photograph previews">{photoPreviews.map((url, index) => <div key={`${url}-${index}`}><img src={url} alt={`Selected vehicle photo ${index + 1}`} /><span>New photo {index + 1}</span><button type="button" className="inventory-text-button" onClick={() => setPhotoFiles((files) => files.filter((_, fileIndex) => fileIndex !== index))}>Remove</button></div>)}</section>}
      {editing?.photos.length ? <section className="photo-preview-grid existing-photos" aria-label="Current vehicle photographs"><h3>Current photographs</h3>{editing.photos.map((photo) => <div key={photo.id}><img src={photoUrl(photo)} alt="Vehicle" />{canManage && <button type="button" className="inventory-text-button" disabled={busy} onClick={() => void removePhoto(editing, photo.id)}>Remove</button>}</div>)}</section> : null}
      <button className="inventory-primary" disabled={busy}>{busy ? "Saving…" : editing ? "Save changes" : "Create vehicle"}</button>
    </form>}
    <section className="inventory-table-wrap" aria-live="polite">
      {vehicles.length === 0 ? <p className="inventory-empty">No vehicle records yet.{canManage ? " Add a vehicle to start building inventory." : ""}</p> : filtered.length === 0 ? <p className="inventory-empty">No vehicles match these filters.</p> : <table className="inventory-table"><thead><tr><th>Vehicle</th><th>Reference</th><th>Condition</th><th>Availability</th><th>Publication</th><th>Price</th><th>Actions</th></tr></thead><tbody>{filtered.map((vehicle) =>
        <Fragment key={vehicle.reference}><tr><td><div className="inventory-vehicle-cell">{vehicle.photos[0] ? <img src={photoUrl(vehicle.photos[0])} alt="" /> : <span className="inventory-image-placeholder">SSP</span>}<span><strong>{vehicle.manufacture_year} {vehicle.make} {vehicle.model}</strong><small>{vehicle.variant || "Standard"} · {vehicle.mileage_km.toLocaleString()} km</small></span></div></td><td>{vehicle.reference}</td><td>{vehicle.condition}</td><td><span className={`stock-status stock-${vehicle.status}`}>{statusLabels[vehicle.status ?? "available"] ?? vehicle.status}</span></td><td><span className={`publication-status publication-${vehicle.visibility}`}>{vehicle.visibility}</span></td><td>{currency(vehicle.asking_price_lkr)}</td>
          <td><div className="inventory-actions"><button className="inventory-secondary" onClick={() => setDetails(details === vehicle.reference ? null : vehicle.reference)}>{details === vehicle.reference ? "Hide" : "Details"}</button>{canManage && <>{vehicle.status === "available" && <Link className="inventory-secondary" href={`/staff/reservations?vehicle=${encodeURIComponent(vehicle.reference)}`}>Reserve</Link>}<button className="inventory-secondary" disabled={busy} onClick={() => { setEditing(vehicle); setCreating(false); setPhotoFiles([]); setError(""); setNotice(""); }}>Edit</button><button className="inventory-secondary" disabled={busy || (vehicle.status !== "available" && vehicle.visibility !== "published")} onClick={() => void togglePublication(vehicle)}>{vehicle.visibility === "published" ? "Unpublish" : "Publish"}</button>{vehicle.status === "available" ? <button className="inventory-danger" disabled={busy} onClick={() => void changeStatus(vehicle, "archived")}>Archive</button> : vehicle.status === "archived" ? <button className="inventory-secondary" disabled={busy} onClick={() => void changeStatus(vehicle, "available")}>Restore</button> : <span className="inventory-help">Lifecycle locked</span>}</>}</div></td></tr>
        {details === vehicle.reference && <tr className="inventory-detail"><td colSpan={7}><div className="inventory-detail-content"><p><strong>Color:</strong> {vehicle.color} · <strong>Fuel:</strong> {vehicle.fuel_type} · <strong>Transmission:</strong> {vehicle.transmission}</p><p><strong>Internal identifier:</strong> {canManage ? vehicle.internal_identifier : "Hidden for read-only review"}</p>{vehicle.description && <p>{vehicle.description}</p>}<div className="detail-photo-strip">{vehicle.photos.map((photo) => <img key={photo.id} src={photoUrl(photo)} alt={`${vehicle.make} ${vehicle.model}`} />)}</div></div></td></tr>}</Fragment>
      )}</tbody></table>}
    </section>
  </main>;
}
