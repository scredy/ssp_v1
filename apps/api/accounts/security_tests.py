import logging

from django.conf import settings
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from .models import User
from .security import SafeCsrfLogFilter


class CsrfProxySecurityTests(APITestCase):
    @override_settings(
        DEBUG=False,
        CSRF_TRUSTED_ORIGINS=["https://localhost:3100"],
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
    )
    def test_proxy_origin_is_csrf_trusted_and_session_cookies_remain_host_scoped(self):
        User.objects.create_user(
            username="proxy-staff",
            password="Valid-password-914!",
            email="proxy-staff@example.test",
            role=User.Role.STAFF,
        )
        client = APIClient(enforce_csrf_checks=True, secure=True)
        frontend_origin = "https://localhost:3100"
        csrf = client.get("/api/auth/csrf/", HTTP_ORIGIN=frontend_origin)
        token = csrf.cookies[settings.CSRF_COOKIE_NAME].value
        login = client.post(
            "/api/auth/login/",
            {"username": "proxy-staff", "password": "Valid-password-914!"},
            format="json",
            HTTP_ORIGIN=frontend_origin,
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(login.status_code, 200)
        session_cookie = login.cookies[settings.SESSION_COOKIE_NAME]
        self.assertTrue(session_cookie["httponly"])
        self.assertTrue(session_cookie["secure"])
        self.assertIsNone(settings.CSRF_COOKIE_DOMAIN)

    def test_invalid_origin_is_rejected_with_generic_csrf_response(self):
        User.objects.create_user(
            username="proxy-staff",
            password="Valid-password-914!",
            email="proxy-staff@example.test",
            role=User.Role.STAFF,
        )
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get("/api/auth/csrf/")
        token = csrf.cookies[settings.CSRF_COOKIE_NAME].value
        rejected = client.post(
            "/api/auth/login/?probe=private-value",
            {"username": "proxy-staff", "password": "Valid-password-914!"},
            format="json",
            HTTP_ORIGIN="https://attacker.example.test",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(rejected.json(), {"detail": "CSRF verification failed."})
        self.assertNotIn("private-value", rejected.content.decode())

    def test_csrf_diagnostics_retain_reason_category_without_untrusted_values(self):
        record = logging.LogRecord(
            "django.security.csrf",
            logging.WARNING,
            __file__,
            1,
            "Origin checking failed - https://attacker.example.test/private?token=secret",
            (),
            None,
        )
        self.assertTrue(SafeCsrfLogFilter().filter(record))
        rendered = record.getMessage()
        self.assertIn("origin_rejected", rendered)
        self.assertNotIn("attacker.example.test", rendered)
        self.assertNotIn("secret", rendered)
