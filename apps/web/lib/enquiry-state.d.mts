export function syncSavedEnquiry<T extends { id: number; internal_notes: string; scheduled_at: string | null }>(
  items: T[],
  saved: T,
): { selected: T; items: T[]; note: string; scheduledAt: string | null };
