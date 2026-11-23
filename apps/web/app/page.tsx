import type { Metadata } from "next";
import HomeClient from "@/components/public-home";

export const metadata: Metadata = {
  title: "Quality Vehicles",
  description: "Browse available vehicles from SSP Motor Trading and request a vehicle enquiry.",
};

export default function HomePage() { return <HomeClient />; }
