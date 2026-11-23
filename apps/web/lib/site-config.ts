function configuredRate(rawValue: string | undefined, fallback: number) {
  const value = Number(rawValue);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

export const FINANCE_OPTIONS = [
  { id: "three-years", label: "3 years", months: 36, monthlyPer100k: configuredRate(process.env.NEXT_PUBLIC_FINANCE_36M_PER_100K, 3575.84) },
  { id: "five-years", label: "5 years", months: 60, monthlyPer100k: configuredRate(process.env.NEXT_PUBLIC_FINANCE_60M_PER_100K, 2483) },
  { id: "six-years", label: "6 years", months: 72, monthlyPer100k: configuredRate(process.env.NEXT_PUBLIC_FINANCE_72M_PER_100K, 2275) },
  { id: "speed-draft", label: "Speed draft / OD", months: null, monthlyPer100k: configuredRate(process.env.NEXT_PUBLIC_FINANCE_OD_PER_100K, 1330) },
] as const;

export const COMPANY_CONTACT = {
  phone: process.env.NEXT_PUBLIC_COMPANY_PHONE?.trim() ?? "",
  whatsapp: process.env.NEXT_PUBLIC_COMPANY_WHATSAPP?.trim() ?? "",
  email: process.env.NEXT_PUBLIC_COMPANY_EMAIL?.trim() ?? "",
};

export function phoneHref(value: string) {
  const normalized = value.replace(/[^\d+]/g, "");
  return /^\+?\d{7,15}$/.test(normalized) ? `tel:${normalized}` : "";
}

export function whatsappHref(value: string, message: string) {
  const digits = value.replace(/\D/g, "");
  return /^\d{7,15}$/.test(digits)
    ? `https://wa.me/${digits}?text=${encodeURIComponent(message)}`
    : "";
}

export function emailHref(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value) ? `mailto:${value}` : "";
}
