export function syncSavedEnquiry(items, saved) {
  return {
    selected: saved,
    items: items.map((item) => item.id === saved.id ? saved : item),
    note: saved.internal_notes,
    scheduledAt: saved.scheduled_at,
  };
}

export function supportsScheduling(kind) {
  return kind === "appointment" || kind === "test_drive";
}

export function enquiryStatuses(kind) {
  return supportsScheduling(kind)
    ? ["new", "contacted", "scheduled", "completed", "cancelled"]
    : ["new", "contacted", "completed", "cancelled"];
}
