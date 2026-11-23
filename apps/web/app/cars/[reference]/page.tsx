import type { Metadata } from "next";
import VehicleDetail from "@/components/vehicle-detail";

export async function generateMetadata({ params }: { params: Promise<{ reference: string }> }): Promise<Metadata> {
  const { reference } = await params;
  return { title: `Vehicle ${reference}`, description: `View specifications, price and enquiry information for vehicle ${reference} at SSP Motor Trading.` };
}

export default async function CarDetailPage({ params }: { params: Promise<{ reference: string }> }) {
  const { reference } = await params;
  return <VehicleDetail reference={reference} />;
}
