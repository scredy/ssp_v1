import json
import os
from urllib.parse import parse_qs, urlparse
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase

from .email_backend import BREVO_EMAIL_URL, BrevoEmailBackend
from .models import AccountActionToken, User


class _Response:
    def __init__(self, status=201, body=b'{"messageId":"<accepted@example.test>"}'):
        self.status = status
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return self.status

    def read(self):
        return self.body


@override_settings(DEFAULT_FROM_EMAIL="SSP Motor Trading <mail@example.test>")
class BrevoEmailBackendTests(SimpleTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"BREVO_API_KEY": "test-api-key", "BREVO_TIMEOUT_SECONDS": "7"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.message = EmailMessage(
            "Welcome", "Set up your account: https://portal.test/?token=private", "SSP <sender@example.test>",
            ["employee@example.test"],
        )

    @patch("accounts.email_backend.urlopen", return_value=_Response())
    def test_sends_text_email_to_brevo_and_counts_accepted_message(self, urlopen_mock):
        sent = BrevoEmailBackend().send_messages([self.message])
        self.assertEqual(sent, 1)
        (request,) = urlopen_mock.call_args.args
        self.assertEqual(request.full_url, BREVO_EMAIL_URL)
        self.assertEqual(request.get_header("Api-key"), "test-api-key")
        self.assertEqual(urlopen_mock.call_args.kwargs["timeout"], 7)
        payload = json.loads(request.data)
        self.assertEqual(payload["sender"], {"email": "sender@example.test", "name": "SSP"})
        self.assertEqual(payload["to"], [{"email": "employee@example.test"}])
        self.assertIn("textContent", payload)
        self.assertIn("token=private", payload["textContent"])

    @patch("accounts.email_backend.urlopen", return_value=_Response())
    def test_supports_html_alternatives_and_attachments(self, urlopen_mock):
        message = EmailMultiAlternatives("Appointment", "Plain confirmation", "sender@example.test", ["customer@example.test"])
        message.attach_alternative("<p>Confirmed</p>", "text/html")
        message.attach("details.txt", "Appointment details", "text/plain")
        self.assertEqual(BrevoEmailBackend().send_messages([message]), 1)
        payload = json.loads(urlopen_mock.call_args.args[0].data)
        self.assertEqual(payload["textContent"], "Plain confirmation")
        self.assertEqual(payload["htmlContent"], "<p>Confirmed</p>")
        self.assertEqual(payload["attachment"][0]["name"], "details.txt")
        self.assertEqual(payload["attachment"][0]["content"], "QXBwb2ludG1lbnQgZGV0YWlscw==")

    @patch.dict(os.environ, {"BREVO_API_KEY": ""})
    def test_missing_key_raises_safely(self):
        with self.assertLogs("accounts.email_backend", level="WARNING") as captured:
            with self.assertRaises(ImproperlyConfigured):
                BrevoEmailBackend().send_messages([self.message])
        rendered = " ".join(captured.output)
        self.assertNotIn("test-api-key", rendered)
        self.assertNotIn("private", rendered)

    def test_provider_errors_return_zero_and_log_only_category_and_status(self):
        for code, category in ((401, "invalid_api_key"), (403, "unauthorized_sender"), (429, "rate_limited"), (503, "provider_error")):
            with self.subTest(code=code):
                error = HTTPError(BREVO_EMAIL_URL, code, "private response", {}, BytesIO(b"token=private"))
                with patch("accounts.email_backend.urlopen", side_effect=error), self.assertLogs("accounts.email_backend", level="WARNING") as logs:
                    self.assertEqual(BrevoEmailBackend().send_messages([self.message]), 0)
                rendered = " ".join(logs.output)
                self.assertIn(category, rendered)
                self.assertIn(str(code), rendered)
                self.assertNotIn("private", rendered)
                self.assertNotIn("test-api-key", rendered)

    @patch("accounts.email_backend.urlopen", return_value=_Response(body=b"not-json"))
    def test_invalid_provider_response_is_not_reported_as_accepted(self, _urlopen):
        with self.assertLogs("accounts.email_backend", level="WARNING") as logs:
            self.assertEqual(BrevoEmailBackend().send_messages([self.message]), 0)
        self.assertIn("invalid_response", " ".join(logs.output))

    @patch("accounts.email_backend.urlopen", side_effect=TimeoutError())
    def test_timeout_is_not_retried_and_outcome_is_reported_as_unknown(self, urlopen_mock):
        with self.assertLogs("accounts.email_backend", level="WARNING") as logs:
            self.assertEqual(BrevoEmailBackend().send_messages([self.message]), 0)
        self.assertEqual(urlopen_mock.call_count, 1)
        self.assertIn("outcome unknown", " ".join(logs.output))

    @patch("accounts.email_backend.urlopen", return_value=_Response(body=b'{"message":"missing id"}'))
    def test_201_without_message_id_is_not_reported_as_accepted(self, _urlopen):
        self.assertEqual(BrevoEmailBackend().send_messages([self.message]), 0)


@override_settings(
    EMAIL_BACKEND="accounts.email_backend.BrevoEmailBackend",
    DEFAULT_FROM_EMAIL="SSP Motor Trading <mail@example.test>",
    ACCOUNT_PORTAL_URL="https://ssp-frontend-xrli.onrender.com",
)
class BrevoAccountWorkflowTests(APITestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"BREVO_API_KEY": "test-api-key", "BREVO_TIMEOUT_SECONDS": "7"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.admin = User.objects.create_user(
            username="email-admin", password="Valid-password-914!", email="admin@example.test", role=User.Role.ADMIN
        )
        self.client.force_authenticate(self.admin)

    @staticmethod
    def _token(request_mock):
        payload = json.loads(request_mock.call_args.args[0].data)
        link = next(part for part in payload["textContent"].split() if "?token=" in part)
        return parse_qs(urlparse(link).query)["token"][0]

    @patch("accounts.email_backend.urlopen", return_value=_Response())
    def test_invitation_is_accepted_then_secure_setup_activates_user_and_reset_sends(self, urlopen_mock):
        response = self.client.post("/api/accounts/", {
            "username": "invited-employee", "email": "employee@example.test",
            "role": User.Role.STAFF, "account_type": "internal",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        employee = User.objects.get(username="invited-employee")
        self.assertFalse(employee.is_active)
        self.assertFalse(employee.has_usable_password())
        self.assertEqual(urlopen_mock.call_count, 1)
        invitation_token = self._token(urlopen_mock)
        self.assertTrue(AccountActionToken.objects.filter(user=employee, kind=AccountActionToken.Kind.INVITATION).exists())

        self.client.force_authenticate(user=None)
        setup = self.client.post("/api/auth/password-setup/", {
            "token": invitation_token, "password": "Employee-setup-Password-914!",
        }, format="json")
        self.assertEqual(setup.status_code, 200)
        employee.refresh_from_db()
        self.assertTrue(employee.is_active)
        self.assertTrue(employee.check_password("Employee-setup-Password-914!"))

        with patch("accounts.email_backend.urlopen", return_value=_Response()) as reset_send:
            reset = self.client.post("/api/auth/password-reset/", {"email": employee.email}, format="json")
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(reset_send.call_count, 1)
        self.assertIn("staff/reset-password", json.loads(reset_send.call_args.args[0].data)["textContent"])

    @patch("accounts.email_backend.urlopen")
    def test_failed_brevo_delivery_rolls_back_account_and_invitation_token(self, urlopen_mock):
        urlopen_mock.side_effect = HTTPError(BREVO_EMAIL_URL, 401, "private", {}, BytesIO(b"private"))
        response = self.client.post("/api/accounts/", {
            "username": "undelivered-employee", "email": "employee@example.test",
            "role": User.Role.STAFF, "account_type": "internal",
        }, format="json")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(User.objects.filter(username="undelivered-employee").exists())
        self.assertFalse(AccountActionToken.objects.filter(user__username="undelivered-employee").exists())

