export function syncSavedEnquiry(items, saved) {
  return {
    selected: saved,
    items: items.map((item) => item.id === saved.id ? saved : item),
    note: saved.internal_notes,
    scheduledAt: saved.scheduled_at,
  };
}
