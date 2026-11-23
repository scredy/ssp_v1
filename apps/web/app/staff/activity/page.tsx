import AuditHistory from "@/components/audit-history";

export default function AdminActivityPage() {
  return <AuditHistory requiredRole="admin" endpoint="/api/activity/recent/" title="Recent account activity" description="Review recent account events and audit actions." />;
}
