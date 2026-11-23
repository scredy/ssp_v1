function toCents(value) {
  if (typeof value !== "string" || !/^\d+(?:\.\d{0,2})?$/.test(value.trim())) return null;
  const [whole, fraction = ""] = value.trim().split(".");
  return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0") || "0");
}

function fromCents(value) {
  return `${value / 100n}.${String(value % 100n).padStart(2, "0")}`;
}

export function isDownPaymentValid(vehiclePrice, downPayment) {
  const priceCents = toCents(vehiclePrice);
  const downCents = toCents(downPayment);
  return priceCents !== null && downCents !== null && downCents <= priceCents;
}

export function amountFinanced(vehiclePrice, downPayment) {
  if (!isDownPaymentValid(vehiclePrice, downPayment)) return null;
  return fromCents(toCents(vehiclePrice) - toCents(downPayment));
}

export function monthlyEstimate(financedAmount, ratePer100k) {
  const financedCents = toCents(financedAmount);
  const rateCents = toCents(ratePer100k);
  if (financedCents === null || rateCents === null) return null;
  const monthlyCents = (financedCents * rateCents + 5_000_000n) / 10_000_000n;
  return fromCents(monthlyCents);
}
