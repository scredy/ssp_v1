from rest_framework import status
from rest_framework.test import APITestCase

from .models import User


class StaffDashboardSummaryTests(APITestCase):
    def test_staff_manager_and_ceo_receive_authorized_dashboard_aggregates(self):
        for role in (User.Role.STAFF, User.Role.MANAGER, User.Role.CEO):
            user = User.objects.create_user(username=f"dashboard-summary-{role}", password="Test-pass-912!", role=role)
            self.client.force_authenticate(user)
            response = self.client.get("/api/staff/dashboard/summary/")
            self.assertEqual(response.status_code, status.HTTP_200_OK, role)
            self.assertEqual(response.data["sales"]["draft_count"], 0)
            self.assertEqual(response.data["sales"]["confirmed_count"], 0)
            self.assertEqual(response.data["sales"]["confirmed_by_day"], [])
            self.assertEqual(response.data["handovers"], {})
            if role == User.Role.STAFF:
                self.assertNotIn("payments", response.data)
                self.assertNotIn("pending_bl_approvals", response.data)
            elif role == User.Role.MANAGER:
                self.assertIn("payments", response.data)
                self.assertNotIn("pending_bl_approvals", response.data)
            else:
                self.assertIn("payments", response.data)
                self.assertIn("pending_bl_approvals", response.data)

    def test_admin_and_representative_cannot_read_company_dashboard_summary(self):
        for role in (User.Role.ADMIN, User.Role.REP):
            user = User.objects.create_user(username=f"dashboard-denied-{role}", password="Test-pass-912!", role=role)
            self.client.force_authenticate(user)
            response = self.client.get("/api/staff/dashboard/summary/")
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, role)
