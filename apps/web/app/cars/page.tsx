import { socialMetadata } from "@/lib/seo";
import type { Metadata } from "next";
import CarsCatalogue from "@/components/cars-catalogue";

export const metadata: Metadata = {
  ...socialMetadata("Browse Vehicles | SSP Motor Trading", "Search and compare the currently published, available vehicles at SSP Motor Trading.", "/cars"),

  title: "Browse Vehicles",
  description: "Search and compare the currently published, available vehicles at SSP Motor Trading.",
};

export default function CarsPage() { return <CarsCatalogue />; }
