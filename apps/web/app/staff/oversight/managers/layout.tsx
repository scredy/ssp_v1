import type { Metadata } from "next";

export const metadata: Metadata = {
  title: { absolute: "Management Oversight | SSP Motor Trading" },
};

export default function Layout({ children }: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
