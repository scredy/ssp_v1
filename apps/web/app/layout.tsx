import type { Metadata } from "next";
import "./globals.css";
import { SITE_URL, SITE_NAME, SITE_DESCRIPTION, socialMetadata } from "@/lib/seo";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  ...socialMetadata(SITE_NAME, SITE_DESCRIPTION, "/"),

  title: { default: "SSP Motor Trading", template: "%s | SSP Motor Trading" },
  description: "Explore vehicle listings and illustrative finance estimates from SSP Motor Trading.",
  applicationName: "SSP Motor Trading",
  icons: {
    icon: [
      { url: "/branding/ssp-favicon.png", sizes: "64x64", type: "image/png" },
      { url: "/branding/ssp-icon.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/branding/ssp-apple-icon.png", sizes: "180x180", type: "image/png" }],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
