from decimal import Decimal
from django.conf import settings
from django.db import DatabaseError
from django.test import override_settings
from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from .models import User, Vehicle
from config.settings import _get_allowed_hosts


class AccountApiTests(APITestCase):
    def test_render_external_hostname_is_added_without_replacing_custom_hosts(self):
        hosts = _get_allowed_hosts({
            "DJANGO_ALLOWED_HOSTS": "ssp.example.com, admin.ssp.example.com",
            "RENDER_EXTERNAL_HOSTNAME": "ssp-api.onrender.com",
        })
        self.assertEqual(hosts, ["ssp.example.com", "admin.ssp.example.com", "ssp-api.onrender.com"])

    def test_render_external_hostname_is_not_duplicated_or_wildcarded(self):
        hosts = _get_allowed_hosts({
            "DJANGO_ALLOWED_HOSTS": "ssp-api.onrender.com",
            "RENDER_EXTERNAL_HOSTNAME": "ssp-api.onrender.com",
        })
        self.assertEqual(hosts, ["ssp-api.onrender.com"])
        self.assertNotIn("*", hosts)

    def make_user(self, username, role, password="Valid-password-914!"):
        return User.objects.create_user(username=username, password=password, email=f"{username}@example.test",
                                        role=role)

    def login_as(self, user, password="Valid-password-914!"):
        self.client.force_authenticate(user=None)
        self.assertTrue(self.client.login(username=user.username, password=password))

    def test_healthz_checks_database_and_returns_no_sensitive_details(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_healthz_returns_200_for_allowed_render_hostname_with_database(self):
        render_hosts = _get_allowed_hosts({
            "DJANGO_ALLOWED_HOSTS": "ssp.example.com",
            "RENDER_EXTERNAL_HOSTNAME": "ssp-api.onrender.com",
        })
        with override_settings(ALLOWED_HOSTS=render_hosts):
            response = self.client.get("/healthz", HTTP_HOST="ssp-api.onrender.com")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"status": "ok"})

    @override_settings(
        ALLOWED_HOSTS=["ssp-api.onrender.com"],
        SECURE_SSL_REDIRECT=True,
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    )
    def test_healthz_recognizes_render_forwarded_https(self):
        response = self.client.get(
            "/healthz",
            HTTP_HOST="ssp-api.onrender.com",
            HTTP_X_FORWARDED_PROTO="https",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @override_settings(ALLOWED_HOSTS=["ssp-api.onrender.com"])
    def test_disallowed_host_is_logged_without_logging_request_query(self):
        with self.assertLogs("django.security.DisallowedHost", level="WARNING") as logs:
            response = self.client.get(
                "/healthz?access_token=private-value",
                HTTP_HOST="unexpected.example.net",
            )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        rendered_log = "\n".join(logs.output)
        self.assertIn("unexpected.example.net", rendered_log)
        self.assertNotIn("private-value", rendered_log)

    @patch("config.urls.connection.cursor", side_effect=DatabaseError("private database detail"))
    def test_healthz_returns_generic_unavailable_when_database_is_down(self, _cursor):
        response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.json(), {"status": "unavailable"})
        self.assertNotIn("private database detail", response.content.decode())

    def test_login_me_and_logout_use_session_authentication(self):
        user = self.make_user("admin", User.Role.ADMIN)
        response = self.client.post("/api/auth/login/", {"username": "admin", "password": "Valid-password-914!"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["role"], User.Role.ADMIN)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, status.HTTP_200_OK)

        response = self.client.post("/api/auth/logout/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIn(settings.SESSION_COOKIE_NAME, response.cookies)
        self.assertEqual(response.cookies[settings.SESSION_COOKIE_NAME]["max-age"], 0)
        self.assertNotEqual(self.client.get("/api/auth/me/").status_code, status.HTTP_200_OK)

    def test_local_web_login_preserves_csrf_and_session_cookies(self):
        self.make_user("local-staff", User.Role.STAFF)
        client = APIClient(enforce_csrf_checks=True)
        origin = "http://localhost:3000"
        csrf_response = client.get("/api/auth/csrf/", HTTP_ORIGIN=origin)
        csrf_token = csrf_response.cookies[settings.CSRF_COOKIE_NAME].value
        login_response = client.post("/api/auth/login/", {"username": "local-staff", "password": "Valid-password-914!"},
            format="json", HTTP_ORIGIN=origin, HTTP_X_CSRFTOKEN=csrf_token)
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertIn(settings.SESSION_COOKIE_NAME, login_response.cookies)
        self.assertEqual(client.get("/api/auth/me/", HTTP_ORIGIN=origin).status_code, status.HTTP_200_OK)

    def test_account_endpoints_require_admin_capability(self):
        for role in (User.Role.CEO, User.Role.MANAGER, User.Role.STAFF, User.Role.REP):
            with self.subTest(role=role):
                self.login_as(self.make_user(f"{role}-user", role))
                response = self.client.get("/api/accounts/")
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_and_update_non_admin_accounts(self):
        admin = self.make_user("root", User.Role.ADMIN)
        self.login_as(admin)
        payload = {"username": "staff-one", "email": "staff@example.test", "role": "staff",
                   "account_type": "internal"}
        response = self.client.post("/api/accounts/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data["is_active"])
        self.assertFalse(response.data["is_onboarded"])
        account_id = response.data["id"]
        response = self.client.patch(f"/api/accounts/{account_id}/", {"first_name": "Ravi", "username": "staff-renamed"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["first_name"], "Ravi")
        self.assertEqual(response.data["username"], "staff-renamed")

    def test_admin_role_cannot_be_assigned_at_creation_or_update(self):
        admin = self.make_user("root", User.Role.ADMIN)
        staff = self.make_user("staff", User.Role.STAFF)
        self.login_as(admin)
        payload = {"username": "another-admin", "email": "a@example.test", "role": "admin",
                   "account_type": "internal"}
        response = self.client.post("/api/accounts/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.patch(f"/api/accounts/{staff.pk}/", {"role": "admin"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_account_is_protected_from_other_admins(self):
        admin = self.make_user("root", User.Role.ADMIN)
        other_admin = self.make_user("second-root", User.Role.ADMIN)
        self.login_as(admin)
        response = self.client.patch(f"/api/accounts/{other_admin.pk}/", {"email": "changed@example.test"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        other_admin.refresh_from_db()
        self.assertEqual(other_admin.email, "second-root@example.test")

    def test_admin_cannot_deactivate_self_but_can_deactivate_another_account(self):
        admin = self.make_user("root", User.Role.ADMIN)
        staff = self.make_user("staff", User.Role.STAFF)
        self.login_as(admin)
        response = self.client.patch(f"/api/accounts/{admin.pk}/", {"is_active": False}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        admin.refresh_from_db()
        self.assertTrue(admin.is_active)

        response = self.client.patch(f"/api/accounts/{staff.pk}/", {"is_active": False}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        staff.refresh_from_db()
        self.assertFalse(staff.is_active)

    def test_admin_cannot_set_another_users_password_directly(self):
        admin = self.make_user("root", User.Role.ADMIN)
        staff = self.make_user("staff", User.Role.STAFF)
        self.login_as(admin)
        new_password = "Reset-password-772!"
        response = self.client.patch(f"/api/accounts/{staff.pk}/", {"password": new_password}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotEqual(response.data.get("password"), new_password)
        staff.refresh_from_db()
        self.assertTrue(staff.check_password("Valid-password-914!"))


class VehicleApiTests(APITestCase):
    def make_user(self, username, role):
        return User.objects.create_user(username=username, password="Valid-password-914!", role=role)

    def make_vehicle(self, visibility):
        return Vehicle.objects.create(
            make="Toyota", model="Corolla", manufacture_year=2022, mileage_km=12000,
            fuel_type=Vehicle.FuelType.PETROL, transmission=Vehicle.Transmission.AUTOMATIC,
            color="White", condition=Vehicle.Condition.USED, internal_identifier=f"VIN-{visibility}",
            asking_price_lkr=Decimal("7500000.00"), visibility=visibility,
        )

    def test_inventory_read_write_permissions_follow_roles(self):
        vehicle = self.make_vehicle(Vehicle.Visibility.DRAFT)
        for role in (User.Role.STAFF, User.Role.CEO, User.Role.MANAGER):
            with self.subTest(role=role):
                user = self.make_user(f"{role}-user", role)
                self.client.force_authenticate(user=user)
                inventory_response = self.client.get("/api/staff/inventory/")
                self.assertEqual(inventory_response.status_code, status.HTTP_200_OK)
                if role in (User.Role.CEO, User.Role.MANAGER):
                    self.assertNotIn("internal_identifier", inventory_response.data[0])
                response = self.client.patch(f"/api/staff/inventory/{vehicle.reference}/",
                                             {"description": "Updated"}, format="json")
                expected = status.HTTP_200_OK if role == User.Role.STAFF else status.HTTP_403_FORBIDDEN
                self.assertEqual(response.status_code, expected)

        for role in (User.Role.ADMIN, User.Role.REP):
            with self.subTest(denied_role=role):
                self.client.force_authenticate(user=self.make_user(f"{role}-user", role))
                self.assertEqual(self.client.get("/api/staff/inventory/").status_code,
                                 status.HTTP_403_FORBIDDEN)

    def test_public_api_exposes_only_published_vehicles(self):
        published = self.make_vehicle(Vehicle.Visibility.PUBLISHED)
        draft = self.make_vehicle(Vehicle.Visibility.DRAFT)

        response = self.client.get("/api/cars/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["reference"] for item in response.data], [published.reference])
        self.assertNotIn("internal_identifier", response.data[0])
        self.assertEqual(self.client.get(f"/api/cars/{published.reference}/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(f"/api/cars/{draft.reference}/").status_code, status.HTTP_404_NOT_FOUND)

    def test_archive_restore_allowed_but_reserved_sold_handover_are_blocked(self):
        staff = self.make_user("inventory-staff", User.Role.STAFF)
        vehicle = self.make_vehicle(Vehicle.Visibility.PUBLISHED)
        self.client.force_authenticate(user=staff)

        response = self.client.patch(f"/api/staff/inventory/{vehicle.reference}/",
                                     {"status": Vehicle.Status.ARCHIVED}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["visibility"], Vehicle.Visibility.PUBLISHED)
        self.assertEqual(response.data["status"], Vehicle.Status.ARCHIVED)
        self.assertEqual(self.client.get("/api/cars/").data, [])
        self.assertEqual(self.client.get(f"/api/cars/{vehicle.reference}/").status_code, status.HTTP_404_NOT_FOUND)

        response = self.client.patch(f"/api/staff/inventory/{vehicle.reference}/",
                                     {"status": Vehicle.Status.SOLD}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.patch(f"/api/staff/inventory/{vehicle.reference}/",
                                     {"status": Vehicle.Status.AVAILABLE}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.status, Vehicle.Status.AVAILABLE)
        for blocked_status in (Vehicle.Status.RESERVED, Vehicle.Status.SOLD, Vehicle.Status.HANDED_OVER):
            with self.subTest(blocked_status=blocked_status):
                response = self.client.patch(f"/api/staff/inventory/{vehicle.reference}/",
                                             {"status": blocked_status}, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
