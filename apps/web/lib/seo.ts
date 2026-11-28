import type { Metadata } from "next";

export const SITE_URL = new URL(
  process.env.NEXT_PUBLIC_SITE_URL?.trim() ||
  "https://ssp-frontend-xrli.onrender.com"
).origin;

export const SITE_NAME = "SSP Motor Trading";

export const SITE_DESCRIPTION =
  "Explore new and pre-owned vehicles, personal imports, vehicle exchanges and finance assistance in Sri Lanka.";

export const SOCIAL_IMAGE = "/branding/ssp-social-preview.png";

export function socialMetadata(
  title: string,
  description: string,
  route: string
): Pick<Metadata, "openGraph" | "twitter"> {
  return {
    openGraph: {
      type: "website",
      locale: "en_LK",
      siteName: SITE_NAME,
      title,
      description,
      url: new URL(route, SITE_URL).href,
      images: [{
        url: new URL(SOCIAL_IMAGE, SITE_URL).href,
        width: 1200,
        height: 630,
        alt: "SSP Motor Trading",
      }],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [new URL(SOCIAL_IMAGE, SITE_URL).href],
    },
  };
}
