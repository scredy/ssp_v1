export function isDownPaymentValid(vehiclePrice: string, downPayment: string): boolean;
export function amountFinanced(vehiclePrice: string, downPayment: string): string | null;
export function monthlyEstimate(financedAmount: string, ratePer100k: string): string | null;
