import type { Metadata } from "next";
import CarsCatalogue from "@/components/cars-catalogue";

export const metadata: Metadata = {
  title: "Available Vehicles",
  description: "Search and compare the currently published, available vehicles at SSP Motor Trading.",
};

export default function CarsPage() { return <CarsCatalogue />; }
