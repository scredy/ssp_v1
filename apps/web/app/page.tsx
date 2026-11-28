import { socialMetadata } from "@/lib/seo";
import type { Metadata } from "next";
import HomeClient from "@/components/public-home";

export const metadata: Metadata = {
  ...socialMetadata("SSP Motor Trading | Premium Vehicles in Sri Lanka", "Explore new and pre-owned vehicles, personal vehicle imports, exchanges and finance assistance with SSP Motor Trading in Sri Lanka.", "/"),

  title: { absolute: "SSP Motor Trading | Premium Vehicles in Sri Lanka" },
  description: "Explore new and pre-owned vehicles, personal vehicle imports, exchanges and finance assistance with SSP Motor Trading in Sri Lanka.",
};

export default function HomePage() { return <HomeClient />; }
