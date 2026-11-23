import AuditHistory from "@/components/audit-history";

export default function ManagerOversightPage() {
  return <AuditHistory requiredRole="ceo" endpoint="/api/oversight/managers/" title="MD/Manager activity" description="Review the latest activity performed by MD/Manager accounts." />;
}
