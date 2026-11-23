import { resolveApiBaseUrl } from "./api-config.mjs";

export const API = resolveApiBaseUrl(
  process.env.NEXT_PUBLIC_API_BASE_URL,
  typeof window === "undefined" ? undefined : window.location.origin,
);

export type Photo = { id: number; url: string; content_type: string; created_at: string };
export type Vehicle = {
  id?: number; reference: string; make: string; model: string; variant: string; manufacture_year: number;
  mileage_km: number; fuel_type: string; transmission: string; color: string; condition: string;
  asking_price_lkr: string; description: string; photos: Photo[]; visibility?: "draft" | "published";
  status?: "available" | "reserved" | "sold" | "handed_over" | "archived";
  internal_identifier?: string; created_at?: string; updated_at?: string;
};
export type User = { username: string; first_name: string; last_name: string; role: string; account_type: string };

function csrfToken() {
  return document.cookie.split("; ").find((item) => item.startsWith("csrftoken="))?.split("=")[1] ?? "";
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!API) {
    throw new Error("The SSP service is not configured. Set NEXT_PUBLIC_API_BASE_URL and restart the web server.");
  }
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (method !== "GET" && method !== "HEAD") {
    let csrfResponse: Response;
    try {
      csrfResponse = await fetch(`${API}/api/auth/csrf/`, { credentials: "include" });
    } catch {
      throw new Error("The SSP service is unavailable right now. Please check your connection and try again.");
    }
    if (!csrfResponse.ok) {
      throw new Error(`Could not prepare a secure request (HTTP ${csrfResponse.status}). Please try again.`);
    }
    headers.set("X-CSRFToken", decodeURIComponent(csrfToken()));
  }
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(`${API}${path}`, { ...init, method, headers, credentials: "include" });
  } catch {
    throw new Error("The SSP service is unavailable right now. Please check your connection and try again.");
  }
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      message = typeof body.detail === "string" ? body.detail : Object.entries(body)
        .map(([field, value]) => `${field}: ${Array.isArray(value) ? value.join(" ") : String(value)}`).join(" ") || message;
    } catch { /* Response had no JSON error body. */ }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function photoUrl(photo: Photo) { return `${API}${photo.url}`; }
