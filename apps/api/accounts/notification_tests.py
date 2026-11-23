from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Notification, User


class NotificationApiTests(APITestCase):
    def setUp(self):
        cache.clear()

    def make_user(self, username, role):
        return User.objects.create_user(username=username, password="Valid-password-914!", role=role)

    def test_inbox_and_read_state_are_scoped_to_authenticated_recipient(self):
        recipient = self.make_user("recipient", User.Role.STAFF)
        other = self.make_user("other-recipient", User.Role.MANAGER)
        own_notice = Notification.objects.create(recipient=recipient, deduplication_key="own-event",
            title="Appointment request", message="A test appointment needs review.", target_url="/staff/enquiries")
        other_notice = Notification.objects.create(recipient=other, deduplication_key="other-event",
            title="Private update", message="Private recipient message.", target_url="/staff")

        self.client.force_authenticate(user=recipient)
        inbox = self.client.get("/api/notifications/?limit=1&offset=0")
        self.assertEqual(inbox.status_code, status.HTTP_200_OK)
        self.assertEqual(inbox.data["count"], 1)
        self.assertEqual(inbox.data["unread_count"], 1)
        self.assertEqual([item["id"] for item in inbox.data["results"]], [own_notice.pk])
        self.assertNotIn(other_notice.message, str(inbox.data))

        forbidden = self.client.patch(f"/api/notifications/{other_notice.pk}/", {"is_read": True}, format="json")
        self.assertEqual(forbidden.status_code, status.HTTP_404_NOT_FOUND)
        other_notice.refresh_from_db()
        self.assertIsNone(other_notice.read_at)

        marked = self.client.patch(f"/api/notifications/{own_notice.pk}/", {"is_read": True}, format="json")
        self.assertEqual(marked.status_code, status.HTTP_200_OK)
        self.assertTrue(marked.data["is_read"])
        self.assertEqual(self.client.get("/api/notifications/").data["unread_count"], 0)

    def test_quote_submission_notifies_only_active_enquiry_team_roles(self):
        staff = self.make_user("quote-staff", User.Role.STAFF)
        manager = self.make_user("quote-manager", User.Role.MANAGER)
        ceo = self.make_user("quote-ceo", User.Role.CEO)
        admin = self.make_user("quote-admin", User.Role.ADMIN)
        rep = self.make_user("quote-rep", User.Role.REP)
        missing_vehicle = self.client.post("/api/public/enquiries/", {
            "full_name": "Fictional Buyer", "email": "buyer@example.test", "phone": "0771234567",
            "preferred_contact": "phone", "kind": "quote", "idempotency_key": "quote-missing-vehicle-01",
        }, format="json")
        self.assertEqual(missing_vehicle.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("vehicle_description", missing_vehicle.data)

        response = self.client.post("/api/public/enquiries/", {
            "full_name": "Fictional Buyer", "email": "buyer@example.test", "phone": "0771234567",
            "preferred_contact": "phone", "kind": "quote", "vehicle_description": "2023 Example Comet",
            "idempotency_key": "quote-example-vehicle-0001",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        from .models import Enquiry
        enquiry = Enquiry.objects.get(reference=response.data["reference"])
        self.assertEqual(enquiry.vehicle_description, "2023 Example Comet")
        self.assertEqual(set(Notification.objects.values_list("recipient_id", flat=True)), {staff.pk, manager.pk, ceo.pk})
        self.assertNotIn(admin.pk, Notification.objects.values_list("recipient_id", flat=True))
        self.assertNotIn(rep.pk, Notification.objects.values_list("recipient_id", flat=True))
