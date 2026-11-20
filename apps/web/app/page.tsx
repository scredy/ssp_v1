"use client";

import { useEffect, useState } from "react";

type ApiState = "checking" | "online" | "offline";

export default function Home() {
  const [apiState, setApiState] = useState<ApiState>("checking");
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

  useEffect(() => {
    const controller = new AbortController();

    fetch(`${apiBaseUrl}/api/health/`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Backend returned an error");
        return response.json() as Promise<{ status?: string }>;
      })
      .then((result) => setApiState(result.status === "ok" ? "online" : "offline"))
      .catch(() => {
        if (!controller.signal.aborted) setApiState("offline");
      });

    return () => controller.abort();
  }, [apiBaseUrl]);

  const message = {
    checking: "Checking backend…",
    online: "Backend is reachable",
    offline: "Backend is unavailable",
  }[apiState];

  return (
    <main>
      <p className="eyebrow">SSP · Development</p>
      <h1>Application foundation</h1>
      <p className="description">
        The public website is available without signing in. Staff members can use the secure portal for their role.
      </p>
      <a className="portal-link" href="/staff/login">Staff sign in <span aria-hidden="true">→</span></a>
      <a className="portal-link" href="/cars">Browse vehicles <span aria-hidden="true">→</span></a>
      <p className={`status status--${apiState}`} role="status" aria-live="polite">
        <span className="status__dot" aria-hidden="true" />
        {message}
      </p>
      <code className="endpoint">{apiBaseUrl}/api/health/</code>
    </main>
  );
}
