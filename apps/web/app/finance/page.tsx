import type { Metadata } from "next";
import FinanceCalculator from "@/components/finance-calculator";

export const metadata: Metadata = { title: "Finance Calculator", description: "Estimate illustrative monthly vehicle finance payments using configured SSP rates." };

export default function FinancePage() { return <FinanceCalculator />; }
