import type { Metadata } from "next";
import { PublicPageFrame } from "@/components/public-site";
import PublicImportTracking from "@/components/public-import-tracking";

export const metadata: Metadata = {
  title: "Track Your Vehicle",
  description: "Securely follow customer-visible updates for an SSP Motor Trading vehicle import.",
};

export default function TrackPage() {
  return <PublicPageFrame active="/track"><PublicImportTracking /></PublicPageFrame>;
}
