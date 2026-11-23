"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/car-api";

type NotificationItem = {
  id: number; title: string; message: string; target_url: string;
  created_at: string; read_at: string | null; is_read: boolean;
};
type NotificationPage = { count: number; unread_count: number; next: string | null; previous: string | null; results: NotificationItem[] };
const PAGE_SIZE = 50;
function publishUnreadCount(count: number) {
  window.dispatchEvent(new CustomEvent("ssp:notification-count", { detail: count }));
}

function formatTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat("en-LK", {
    dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Colombo",
  }).format(date);
}

export default function NotificationsInbox() {
  const router = useRouter();
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [count, setCount] = useState(0);
  const [unreadCount, setUnreadCount] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadPage = useCallback(async (nextOffset = 0) => {
    setLoading(true); setError("");
    try {
      const page = await api<NotificationPage>(`/api/notifications/?limit=${PAGE_SIZE}&offset=${nextOffset}`);
      setItems(page.results); setCount(page.count); setUnreadCount(page.unread_count); setOffset(nextOffset); publishUnreadCount(page.unread_count);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load notifications.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { void loadPage(0); }, [loadPage]);

  async function setRead(item: NotificationItem, isRead: boolean) {
    setError("");
    try {
      const updated = await api<NotificationItem>(`/api/notifications/${item.id}/`, {
        method: "PATCH", body: JSON.stringify({ is_read: isRead }),
      });
      setItems((current) => current.map((row) => row.id === updated.id ? updated : row));
      if (item.is_read !== updated.is_read) {
        const nextUnreadCount = Math.max(0, unreadCount + (updated.is_read ? -1 : 1));
        setUnreadCount(nextUnreadCount); publishUnreadCount(nextUnreadCount);
      }
      return true;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to update notification state.");
      return false;
    }
  }

  async function openItem(event: React.MouseEvent<HTMLAnchorElement>, item: NotificationItem) {
    if (item.is_read) return;
    event.preventDefault();
    if (await setRead(item, true)) router.push(item.target_url);
  }

  const first = count === 0 ? 0 : offset + 1;
  const last = Math.min(offset + items.length, count);

  return <main className="workspace-page notification-workspace">
    <section className="workspace-hero"><p className="eyebrow">YOUR WORKSPACE</p><h1>Notifications</h1><p>Updates for work assigned to you and actions that need your attention.</p></section>
    <div className="notification-summary"><strong>{unreadCount}</strong><span>unread {unreadCount === 1 ? "notification" : "notifications"}</span></div>
    {error && <div className="state-card state-error" role="alert"><p>{error}</p><button className="quiet-button" onClick={() => void loadPage(offset)}>Retry</button></div>}
    {loading ? <p className="state-card" role="status">Loading notifications…</p> : error && items.length === 0 ? null : items.length === 0 ? <p className="state-card">{count === 0 ? "You have no notifications yet." : "No notifications are on this page."}</p> : <>
      <section className="notification-list" aria-label="Notifications" aria-live="polite">{items.map((item) => <article className={`notification-card ${item.is_read ? "is-read" : "is-unread"}`} key={item.id}>
        <div className="notification-card-body"><div className="notification-card-heading"><h2>{item.title}</h2><time dateTime={item.created_at}>{formatTime(item.created_at)}</time></div><p>{item.message}</p>
          <Link className="text-link" href={item.target_url} onClick={(event) => void openItem(event, item)}>Open related screen →</Link>
        </div>
        <button className="quiet-button" disabled={loading} onClick={() => void setRead(item, !item.is_read)}>{item.is_read ? "Mark unread" : "Mark read"}</button>
      </article>)}</section>
      <nav className="notification-pagination" aria-label="Notification pages"><span>Showing {first}–{last} of {count}</span><div><button className="quiet-button" disabled={loading || offset === 0} onClick={() => void loadPage(Math.max(0, offset - PAGE_SIZE))}>Previous</button><button className="quiet-button" disabled={loading || offset + items.length >= count} onClick={() => void loadPage(offset + PAGE_SIZE)}>Next</button></div></nav>
    </>}
  </main>;
}
