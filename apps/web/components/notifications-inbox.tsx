"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type MouseEvent } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/car-api";

type NotificationItem = {
  id: number; title: string; message: string; target_url: string;
  created_at: string; read_at: string | null; is_read: boolean;
};
type NotificationCategory = "all" | "unread" | "approvals" | "handovers" | "system";
type DateRange = "all" | "today" | "7d" | "30d";
type Counts = Record<NotificationCategory, number>;
type NotificationPage = {
  count: number; unread_count: number; next: string | null; previous: string | null;
  category_counts: Counts; results: NotificationItem[];
};
type NotificationKind = "handover" | "payment" | "appointment" | "approval" | "system" | "other";
const PAGE_SIZE = 50;
const KNOWN_TARGETS = [
  "/staff/handovers", "/staff/payments", "/staff/bl-requests", "/staff/imports",
  "/staff/enquiries", "/staff/my-sales", "/staff/commissions", "/staff/my-commissions", "/staff/sales",
  "/staff/accounts", "/staff/activity", "/staff/commission-rules",
];
const EMPTY_COUNTS: Counts = { all: 0, unread: 0, approvals: 0, handovers: 0, system: 0 };

function publishUnreadCount(count: number) {
  window.dispatchEvent(new CustomEvent("ssp:notification-count", { detail: count }));
}

function formatTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat("en-LK", {
    dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Colombo",
  }).format(date);
}

function relatedHref(target: string) {
  if (!target.startsWith("/") || target.startsWith("//") || target.includes("\\")) return null;
  try {
    const parsed = new URL(target, "https://ssp.invalid");
    if (parsed.origin !== "https://ssp.invalid" || (parsed.pathname !== "/staff" && !KNOWN_TARGETS.some((route) =>
      parsed.pathname === route || parsed.pathname.startsWith(`${route}/`)))) return null;
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return null;
  }
}

function notificationKind(item: NotificationItem): NotificationKind {
  const text = `${item.title} ${item.message}`.toLowerCase();
  if (item.target_url.startsWith("/staff/handovers") || text.includes("handover")) return "handover";
  if (item.target_url.startsWith("/staff/payments") || text.includes("payment")) return "payment";
  if (text.includes("appointment") || text.includes("showroom")) return "appointment";
  if (item.target_url.startsWith("/staff/bl-requests") || text.includes("approval")) return "approval";
  if (text.includes("system")) return "system";
  return "other";
}

function NotificationIcon({ kind }: { kind: NotificationKind }) {
  let paths: React.ReactNode;
  if (kind === "handover") paths = <><path d="m3 13 2-6h14l2 6v6h-3v-3H6v3H3z"/><path d="M5 13h14M7 16h.01M17 16h.01"/></>;
  else if (kind === "payment") paths = <><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 9h18M7 15h4"/></>;
  else if (kind === "appointment") paths = <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18M8 14h3M8 17h6"/></>;
  else if (kind === "approval") paths = <><path d="M7 3h8l5 5v13H7z"/><path d="M15 3v5h5M10 14l2 2 4-5"/></>;
  else if (kind === "system") paths = <><path d="M12 3 4 6v5c0 5 3.5 8.5 8 10 4.5-1.5 8-5 8-10V6z"/><path d="M9 12h6M12 9v6"/></>;
  else paths = <><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></>;
  return <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">{paths}</svg>;
}

export default function NotificationsInbox() {
  const router = useRouter();
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [count, setCount] = useState(0);
  const [categoryCounts, setCategoryCounts] = useState<Counts | null>(null);
  const [offset, setOffset] = useState(0);
  const [category, setCategory] = useState<NotificationCategory>("all");
  const [dateRange, setDateRange] = useState<DateRange>("all");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [updatingIds, setUpdatingIds] = useState<Set<number>>(() => new Set());
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const requestVersion = useRef(0);
  const unreadCount = categoryCounts?.unread ?? 0;

  useEffect(() => {
    const timeout = window.setTimeout(() => setSearch(searchInput.trim()), 250);
    return () => window.clearTimeout(timeout);
  }, [searchInput]);

  const loadPage = useCallback(async (nextOffset = 0, silent = false) => {
    const version = ++requestVersion.current;
    if (!silent) setLoading(true);
    setError("");
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(nextOffset) });
    if (category !== "all") params.set("category", category);
    if (dateRange !== "all") params.set("period", dateRange);
    if (search) params.set("search", search);
    try {
      const page = await api<NotificationPage>(`/api/notifications/?${params.toString()}`, { cache: "no-store" });
      if (version !== requestVersion.current) return;
      setItems(page.results);
      setCount(page.count);
      setCategoryCounts(page.category_counts);
      setOffset(nextOffset);
      publishUnreadCount(page.unread_count);
    } catch {
      if (version === requestVersion.current) setError("Notifications could not be loaded. Check your connection and retry.");
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  }, [category, dateRange, search]);

  useEffect(() => { void loadPage(0); }, [loadPage]);

  useEffect(() => {
    // Avoid interrupting read/unread changes or browsing older pages.
    if (loading || bulkLoading || updatingIds.size > 0 || offset !== 0) return;

    const refresh = () => {
      if (document.visibilityState === "visible") {
        void loadPage(0, true);
      }
    };

    const interval = window.setInterval(refresh, 30000);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);

    return () => {
      window.clearInterval(interval);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [loadPage, loading, bulkLoading, updatingIds.size, offset]);

  const updateRead = useCallback(async (item: NotificationItem, isRead: boolean) => {
    if (updatingIds.has(item.id) || bulkLoading) return false;
    setError("");
    setNotice("");
    setUpdatingIds((current) => new Set(current).add(item.id));
    try {
      const updated = await api<NotificationItem>(`/api/notifications/${item.id}/`, {
        method: "PATCH", body: JSON.stringify({ is_read: isRead }),
      });
      setItems((current) => current.map((row) => row.id === updated.id ? updated : row));
      if (item.is_read !== updated.is_read) {
        const nextOffset = category === "unread" && updated.is_read &&
          items.length === 1 ? Math.max(0, offset - PAGE_SIZE) : offset;
        await loadPage(nextOffset, true);
      }
      return true;
    } catch {
      setError("That notification could not be updated. Please retry.");
      return false;
    } finally {
      setUpdatingIds((current) => { const next = new Set(current); next.delete(item.id); return next; });
    }
  }, [bulkLoading, category, loadPage, offset, items.length, updatingIds]);

  async function openItem(event: MouseEvent<HTMLAnchorElement>, item: NotificationItem) {
    if (item.is_read) return;
    event.preventDefault();
    if (await updateRead(item, true)) {
      const href = relatedHref(item.target_url);
      if (href) router.push(href);
    }
  }

  async function markAllRead() {
    if (bulkLoading || unreadCount === 0) return;
    setBulkLoading(true);
    setError("");
    setNotice("");
    let pageOffset = 0;
    const unreadIds: number[] = [];
    try {
      let nextPage: NotificationPage;
      do {
        const params = new URLSearchParams({ limit: "100", offset: String(pageOffset), category: "unread" });
        nextPage = await api<NotificationPage>(`/api/notifications/?${params.toString()}`);
        unreadIds.push(...nextPage.results.filter((item) => !item.is_read).map((item) => item.id));
        pageOffset += nextPage.results.length;
      } while (nextPage.next && nextPage.results.length > 0);
    } catch {
      setError("Unread notifications could not be prepared for update. Please retry.");
      setBulkLoading(false);
      return;
    }

    let failed = 0;
    for (const id of unreadIds) {
      try {
        await api<NotificationItem>(`/api/notifications/${id}/`, {
          method: "PATCH", body: JSON.stringify({ is_read: true }),
        });
      } catch {
        failed += 1;
      }
    }
    await loadPage(0);
    if (failed) setError(`${failed} notification${failed === 1 ? "" : "s"} could not be marked as read. Retry to update the remaining items.`);
    else setNotice(unreadIds.length ? "All unread notifications were marked as read." : "You’re all caught up.");
    setBulkLoading(false);
  }

  const first = count === 0 ? 0 : offset + 1;
  const last = Math.min(offset + items.length, count);
  const tabs: { key: NotificationCategory; label: string; icon: NotificationKind }[] = [
    { key: "all", label: "All", icon: "other" },
    { key: "unread", label: "Unread", icon: "system" },
    { key: "approvals", label: "Approvals", icon: "approval" },
    { key: "handovers", label: "Handovers", icon: "handover" },
    { key: "system", label: "System", icon: "system" },
  ];
  const emptyMessage = search || dateRange !== "all"
    ? "No notifications match your filters."
    : category === "unread" ? "You’re all caught up."
      : categoryCounts?.all === 0 ? "No notifications yet."
        : "No notifications in this category.";

  return <main className="workspace-page notification-workspace">
    <section className="notification-hero" aria-labelledby="notification-title">
      <span className="notification-hero-icon"><NotificationIcon kind="system" /></span>
      <div className="notification-hero-copy">
        <p className="notification-eyebrow">SSP OPERATIONS</p>
        <h1 id="notification-title">Notifications</h1>
        <p>Updates for work assigned to you and actions that need your attention.</p>
      </div>
      <span className="notification-hero-count" aria-live="polite">
        {categoryCounts ? <><strong>{unreadCount}</strong> unread {unreadCount === 1 ? "notification" : "notifications"}</> : "Loading unread count…"}
      </span>
    </section>

    <nav className="notification-tabs" aria-label="Notification categories">
      {tabs.map((tab) => <button key={tab.key} type="button" className={`notification-tab ${category === tab.key ? "is-active" : ""}`}
        aria-pressed={category === tab.key} onClick={() => setCategory(tab.key)}>
        <NotificationIcon kind={tab.icon} /><span>{tab.label}</span>
        {categoryCounts && <span className="notification-tab-count">{categoryCounts[tab.key]}</span>}
      </button>)}
    </nav>

    <section className="notification-tools" aria-label="Filter notifications">
      <label className="notification-search"><span className="notification-search-icon" aria-hidden="true">⌕</span>
        <span className="staff-visually-hidden">Search notifications</span>
        <input type="search" value={searchInput} onChange={(event) => setSearchInput(event.target.value)}
          placeholder="Search notifications (handover, payment, approval…)" />
      </label>
      <label className="notification-date-filter"><span>Date</span>
        <select value={dateRange} onChange={(event) => setDateRange(event.target.value as DateRange)}>
          <option value="all">All time</option><option value="today">Today</option>
          <option value="7d">Last 7 days</option><option value="30d">Last 30 days</option>
        </select>
      </label>
      <button className="notification-mark-all" type="button"
        disabled={loading || bulkLoading || updatingIds.size > 0}
        onClick={() => void loadPage(offset)}>Refresh</button>
      <button className="notification-mark-all" type="button" disabled={loading || bulkLoading || unreadCount === 0}
        onClick={() => void markAllRead()}>{bulkLoading ? "Marking as read…" : "Mark all as read"}</button>
    </section>

    {error && <div className="notification-feedback is-error" role="alert"><span>{error}</span>
      <button type="button" className="notification-retry" onClick={() => void loadPage(offset)} disabled={loading}>Retry</button></div>}
    {notice && <p className="notification-feedback is-success" role="status">{notice}</p>}

    <section className="notification-results" aria-labelledby="notification-results-title">
      <div className="notification-results-heading"><h2 id="notification-results-title">Your notifications</h2>
        <span>{loading ? "Updating…" : `${first}–${last} of ${count}`}</span></div>
      {loading && items.length === 0 ? <div className="notification-skeletons" role="status" aria-label="Loading notifications">
        {[0, 1, 2].map((item) => <div className="notification-skeleton" key={item}><span/><div><i/><i/></div></div>)}
      </div> : !loading && items.length === 0 ? <div className="notification-empty"><span className="notification-empty-icon"><NotificationIcon kind="system" /></span><h3>{emptyMessage}</h3>
        <p>{category === "unread" ? "New items that need your attention will appear here." : "Try another category or adjust your search and date filters."}</p></div> : <div className="notification-list" aria-label="Notifications" aria-live="polite">
        {items.map((item) => {
          const href = relatedHref(item.target_url);
          const kind = notificationKind(item);
          const updating = updatingIds.has(item.id) || bulkLoading;
          return <article className={`notification-row ${item.is_read ? "is-read" : "is-unread"} kind-${kind}`} key={item.id}>
            <span className="notification-row-icon"><NotificationIcon kind={kind} /></span>
            <div className="notification-row-content">
              <div className="notification-row-title"><h3>{item.title}</h3><span className={`notification-read-label ${item.is_read ? "is-read" : "is-unread"}`}>{item.is_read ? "Read" : "Unread"}</span></div>
              <p>{item.message}</p>
              {href ? <Link className="notification-related-link" href={href} onClick={(event) => void openItem(event, item)}>Open related screen <span aria-hidden="true">→</span></Link>
                : <span className="notification-no-link">No related screen</span>}
            </div>
            <div className="notification-row-actions"><time dateTime={item.created_at}>{formatTime(item.created_at)}</time>
              <button type="button" className="notification-read-button" disabled={updating}
                aria-label={`${item.is_read ? "Mark unread" : "Mark as read"}: ${item.title}`}
                onClick={() => void updateRead(item, !item.is_read)}>{updating ? "Saving…" : item.is_read ? "Mark unread" : "Mark as read"}</button>
            </div>
          </article>;
        })}
      </div>}
      {count > PAGE_SIZE && <nav className="notification-pagination" aria-label="Notification pages"><span>Showing {first}–{last} of {count}</span><div>
        <button type="button" disabled={loading || offset === 0} onClick={() => void loadPage(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
        <button type="button" disabled={loading || offset + items.length >= count} onClick={() => void loadPage(offset + PAGE_SIZE)}>Next</button>
      </div></nav>}
    </section>
  </main>;
}
