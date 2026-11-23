export function commissionActions(role, status) {
  if (role !== "ceo" && role !== "manager") return [];
  if (status === "pending") return ["approved", "reversed"];
  if (status === "approved") return ["paid", "reversed"];
  if (status === "paid") return ["reversed"];
  return [];
}

export function paidLeaderboardRows(rows) {
  return rows.filter((row) => row.status === "paid");
}
