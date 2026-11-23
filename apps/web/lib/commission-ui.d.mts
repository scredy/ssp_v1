export type CommissionStatus = "pending" | "approved" | "paid" | "reversed";
export function commissionActions(role: string, status: CommissionStatus): CommissionStatus[];
export function paidLeaderboardRows<T extends { status: CommissionStatus }>(rows: T[]): T[];
