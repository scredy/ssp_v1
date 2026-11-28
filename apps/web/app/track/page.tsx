import { socialMetadata } from "@/lib/seo";
import type { Metadata } from "next";
import { PublicPageFrame } from "@/components/public-site";
import PublicImportTracking from "@/components/public-import-tracking";

export const metadata: Metadata = {
  ...socialMetadata("Track Your Vehicle | SSP Motor Trading", "Securely follow customer-visible updates for an SSP Motor Trading vehicle import.", "/track"),

  title: "Track Your Vehicle",
  description: "Securely follow customer-visible updates for an SSP Motor Trading vehicle import.",
};

export default function TrackPage() {
  return <PublicPageFrame active="/track"><PublicImportTracking /></PublicPageFrame>;
}
