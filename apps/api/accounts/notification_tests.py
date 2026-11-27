from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Notification, User


class NotificationApiTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="notification-staff", password="Test-pass-912!", role=User.Role.STAFF)
        self.other = User.objects.create_user(username="notification-other", password="Test-pass-912!", role=User.Role.CEO)
        self.handover_review = self.make_notification("handover:1:review", "Handover needs MD review",
            "Handover HND-1 is ready for MD review.", "/staff/handovers")
        self.handover_finalized = self.make_notification("handover:2:finalized", "Handover finalized",
            "Handover HND-2 was finalized.", "/staff/handovers")
        self.payment = self.make_notification("payment:1:review", "Payment needs review",
            "Payment PAY-1 is waiting for verification.", "/staff/payments")
        self.bl = self.make_notification("bl-request:1:requested", "BL approval requested",
            "BL approval BLR-1 is waiting for review.", "/staff/bl-requests")
        self.appointment = self.make_notification("enquiry:1:appointment", "Appointment request received",
            "A showroom appointment needs review.", "/staff/enquiries")
        self.system = self.make_notification("system:1:maintenance", "System maintenance complete",
            "The system maintenance window has ended.", "/staff")
        self.appointment.created_at = timezone.now() - timedelta(days=45)
        self.appointment.save(update_fields=["created_at"])
        self.other_notification = Notification.objects.create(recipient=self.other, deduplication_key="private:1",
            title="Private notification", message="Not available to this staff member.", target_url="/staff")
        self.client.force_authenticate(self.staff)

    def make_notification(self, key, title, message, target):
        return Notification.objects.create(recipient=self.staff, deduplication_key=key, title=title,
            message=message, target_url=target)

    def test_categories_search_date_and_unread_filters_return_scoped_global_counts(self):
        all_response = self.client.get("/api/notifications/?limit=50&offset=0")
        self.assertEqual(all_response.status_code, status.HTTP_200_OK)
        self.assertEqual(all_response.data["count"], 6)
        self.assertEqual(all_response.data["unread_count"], 6)
        self.assertEqual(all_response.data["category_counts"], {
            "all": 6, "unread": 6, "approvals": 3, "handovers": 2, "system": 1,
        })

        for category, expected_count in (("approvals", 3), ("handovers", 2), ("system", 1), ("unread", 6)):
            response = self.client.get(f"/api/notifications/?category={category}")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["count"], expected_count, category)
        search = self.client.get("/api/notifications/?search=PAY-1")
        self.assertEqual(search.data["count"], 1)
        self.assertEqual(search.data["results"][0]["id"], self.payment.pk)
        recent = self.client.get("/api/notifications/?period=30d")
        self.assertEqual(recent.data["count"], 5)
        today = self.client.get("/api/notifications/?period=today")
        self.assertEqual(today.data["count"], 5)

    def test_read_state_updates_remain_owner_scoped_and_counts_are_refreshed(self):
        response = self.client.patch(f"/api/notifications/{self.payment.pk}/", {"is_read": True}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_read"])
        listing = self.client.get("/api/notifications/?category=unread")
        self.assertEqual(listing.data["count"], 5)
        self.assertEqual(listing.data["unread_count"], 5)
        other = self.client.patch(f"/api/notifications/{self.other_notification.pk}/", {"is_read": True}, format="json")
        self.assertEqual(other.status_code, status.HTTP_404_NOT_FOUND)

    def test_every_existing_staff_role_can_read_its_own_inbox(self):
        for role in (User.Role.ADMIN, User.Role.CEO, User.Role.MANAGER, User.Role.STAFF, User.Role.REP):
            user = User.objects.create_user(username=f"notification-role-{role}", password="Test-pass-912!", role=role)
            Notification.objects.create(recipient=user, deduplication_key=f"{role}:one", title="Own notification",
                message="Private to this role account.", target_url="/staff")
            self.client.force_authenticate(user)
            response = self.client.get("/api/notifications/")
            self.assertEqual(response.status_code, status.HTTP_200_OK, role)
            self.assertEqual(response.data["count"], 1, role)
            self.assertEqual(response.data["results"][0]["title"], "Own notification")

    def test_public_enquiry_notifies_only_authorized_roles(self):
        from django.core.cache import cache

        cache.clear()
        manager = User.objects.create_user(
            username="event-manager", role=User.Role.MANAGER
        )
        admin = User.objects.create_user(
            username="event-admin", role=User.Role.ADMIN
        )
        rep = User.objects.create_user(
            username="event-rep", role=User.Role.REP
        )
        inactive = User.objects.create_user(
            username="inactive-manager",
            role=User.Role.MANAGER,
            is_active=False,
        )

        self.client.force_authenticate(None)

        payload = {
            "full_name": "Notification Test Customer",
            "phone": "0771234567",
            "preferred_contact": "phone",
            "kind": "general",
            "message": "Notification workflow regression test",
            "idempotency_key": "notification-event-test-12345",
        }

        response = self.client.post(
            "/api/public/enquiries/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        repeated = self.client.post(
            "/api/public/enquiries/", payload, format="json"
        )
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)

        notices = Notification.objects.filter(
            deduplication_key__endswith=":general-requested"
        )

        self.assertSetEqual(
            set(notices.values_list("recipient_id", flat=True)),
            {self.staff.pk, self.other.pk, manager.pk},
        )
        self.assertEqual(notices.count(), 3)

        for user in (admin, rep, inactive):
            self.assertFalse(notices.filter(recipient=user).exists())

        for user in (self.staff, self.other, manager):
            self.client.force_authenticate(user)
            listing = self.client.get("/api/notifications/")
            self.assertEqual(listing.status_code, status.HTTP_200_OK)
            self.assertTrue(any(
                response.data["reference"] in row["message"]
                for row in listing.data["results"]
            ))

    def test_account_deactivation_generates_admin_notification(self):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from .views import AccountDetailView

        admin = User.objects.create_user(
            username="account-event-admin",
            role=User.Role.ADMIN,
        )
        factory = APIRequestFactory()
        request = factory.patch(
            "/account-test/",
            {"is_active": False},
            format="json",
        )
        force_authenticate(request, user=admin)

        response = AccountDetailView.as_view()(
            request, account_id=self.staff.pk
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        notices = Notification.objects.filter(
            title="Account deactivated"
        )
        self.assertEqual(notices.count(), 1)
        self.assertEqual(notices.first().recipient_id, admin.pk)
        self.assertEqual(notices.first().target_url, "/staff/accounts")

        self.client.force_authenticate(admin)
        listing = self.client.get("/api/notifications/")
        self.assertEqual(listing.data["count"], 1)
        self.assertEqual(listing.data["unread_count"], 1)
