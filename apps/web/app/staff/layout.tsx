import type { Metadata } from "next";

export const metadata: Metadata = {
  openGraph: null,
  twitter: null,
  title: { absolute: "Dashboard | SSP Motor Trading" },
  description: "SSP Motor Trading internal staff portal.",
  robots: {
    index: false,
    follow: false,
    googleBot: {
      index: false,
      follow: false,
    },
  },
};

import StaffShell from "@/components/staff-shell";

export default function StaffLayout({ children }: { children: React.ReactNode }) {
  return <StaffShell>{children}</StaffShell>;
}
