import { socialMetadata } from "@/lib/seo";
import type { Metadata } from "next";
import FinanceCalculator from "@/components/finance-calculator";

export const metadata: Metadata = {
  ...socialMetadata("Vehicle Finance Calculator | SSP Motor Trading", "Estimate illustrative monthly vehicle finance payments using configured SSP rates.", "/finance"),
 title: "Vehicle Finance Calculator", description: "Estimate illustrative monthly vehicle finance payments using configured SSP rates." };

export default function FinancePage() { return <FinanceCalculator />; }
