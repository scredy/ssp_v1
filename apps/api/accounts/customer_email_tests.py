from datetime import timedelta

from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .appointment_email import send_confirmation_email
from .models import Customer, Enquiry

@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CustomerEmailTests(APITestCase):
    def payload(self, **overrides):
        return {
            "full_name": "A <b>Fictional Customer</b>",
            "email": "customer@example.test",
            "phone": "0771234567",
            "preferred_contact": "email",
            "kind": "general",
            "message": "A question about a car",
            "idempotency_key": "customer-email-preview-001",
            **overrides,
        }

    def test_general_enquiry_sends_shared_branded_html_and_text_to_customer(self):
        response = self.client.post("/api/public/enquiries/", self.payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["customer@example.test"])
        self.assertIn(response.data["reference"], sent.body)
        self.assertIn("Enquiry Received", sent.body)
        self.assertEqual(len(sent.alternatives), 1)
        html, content_type = sent.alternatives[0]
        self.assertEqual(content_type, "text/html")
        self.assertIn("SSP Motor Trading", html)
        self.assertIn("Reference Number", html)
        self.assertIn("&lt;b&gt;Fictional Customer&lt;/b&gt;", html)
        self.assertNotIn("A question about a car", html)
        self.assertNotIn("internal", html.lower())

    def test_appointment_request_email_says_it_is_not_confirmed(self):
        response = self.client.post("/api/public/enquiries/", self.payload(
            kind="appointment", idempotency_key="customer-email-appointment-001",
            requested_at=(timezone.now() + timedelta(days=3)).isoformat(),
        ), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        sent = mail.outbox[-1]
        html = sent.alternatives[0][0]
        self.assertIn("Appointment Request Received", sent.body)
        self.assertIn("not confirmed yet", sent.body)
        self.assertIn("not a confirmed booking", html)

    def test_quote_request_uses_purpose_specific_shared_template(self):
        response = self.client.post("/api/public/enquiries/", self.payload(
            kind="quote", vehicle_description="A Very Long & Fictional Touring Sedan",
            idempotency_key="customer-email-quote-001",
        ), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        sent = mail.outbox[-1]
        self.assertIn("Quotation Request Received", sent.body)
        self.assertIn("A Very Long &amp; Fictional Touring Sedan", sent.alternatives[0][0])

    def test_appointment_confirmation_uses_shared_template_and_excludes_internal_notes(self):
        customer = Customer.objects.create(full_name="Fictional Appointment Customer", email="appointment@example.test")
        scheduled_at = timezone.now() + timedelta(days=4)
        enquiry = Enquiry.objects.create(
            customer=customer,
            kind=Enquiry.Kind.APPOINTMENT,
            status=Enquiry.Status.SCHEDULED,
            scheduled_at=scheduled_at,
            confirmation_email_schedule=scheduled_at,
            confirmation_email_status=Enquiry.ConfirmationEmailStatus.QUEUED,
            confirmation_email_recipient=customer.email,
            internal_notes="Private internal-only note",
        )
        send_confirmation_email(enquiry.pk, scheduled_at, actor_id=None)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, [customer.email])
        self.assertIn(enquiry.reference, sent.body)
        self.assertIn("Showroom Appointment Confirmed", sent.body)
        self.assertEqual(sent.alternatives[0][1], "text/html")
        html = sent.alternatives[0][0]
        self.assertIn("Confirmed date and time", html)
        self.assertNotIn("Private internal-only note", sent.body + html)
