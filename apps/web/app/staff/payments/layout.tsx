import type { Metadata } from "next";

export const metadata: Metadata = {
  title: { absolute: "Payments | SSP Motor Trading" },
};

export default function Layout({ children }: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
