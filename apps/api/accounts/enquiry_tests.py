from datetime import timedelta
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from django.utils import timezone
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .models import AuditEvent, Customer, Enquiry, User, Vehicle


class EnquiryApiTests(APITestCase):
    def setUp(self):
        cache.clear()

    def make_user(self, username, role):
        return User.objects.create_user(username=username, password="Valid-password-914!", role=role)

    def make_vehicle(self, visibility=Vehicle.Visibility.PUBLISHED, stock=Vehicle.Status.AVAILABLE):
        return Vehicle.objects.create(make="Honda", model="Vezel", manufacture_year=2023, mileage_km=15000,
            fuel_type=Vehicle.FuelType.HYBRID, transmission=Vehicle.Transmission.AUTOMATIC, color="Silver",
            condition=Vehicle.Condition.USED, internal_identifier=f"PRIVATE-{visibility}-{Vehicle.objects.count()}", asking_price_lkr="12500000",
            visibility=visibility, status=stock)

    def payload(self, **extra):
        return {"full_name": "Test Customer", "email": "buyer@example.test", "phone": "0771234567",
            "preferred_contact": "phone", "kind": "general", "message": "Please contact me.",
            "idempotency_key": "retry-key-12345678", **extra}

    def test_public_submission_creates_customer_and_idempotent_reference(self):
        payload = self.payload()
        first = self.client.post("/api/public/enquiries/", payload, format="json")
        second = self.client.post("/api/public/enquiries/", payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["reference"], second.data["reference"])
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Enquiry.objects.count(), 1)
        self.assertNotIn("email", first.data)
        self.assertTrue(first.data["reference"].startswith("ENQ-"))

    def test_customer_record_is_reused_for_repeat_public_contacts(self):
        self.client.post("/api/public/enquiries/", self.payload(), format="json")
        next_payload = self.payload(idempotency_key="another-distinct-request", kind="quote", vehicle_description="Example hatchback")
        self.client.post("/api/public/enquiries/", next_payload, format="json")
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Customer.objects.first().enquiries.count(), 2)

    def test_quote_requires_and_persists_free_text_vehicle_description(self):
        missing = self.client.post("/api/public/enquiries/", self.payload(kind="quote"), format="json")
        self.assertEqual(missing.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("vehicle_description", missing.data)

        response = self.client.post("/api/public/enquiries/", self.payload(
            kind="quote", vehicle_description="2023 Example Comet", idempotency_key="quote-comet-request-001",
        ), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        enquiry = Enquiry.objects.get(reference=response.data["reference"])
        self.assertEqual(enquiry.vehicle_description, "2023 Example Comet")
        staff = self.make_user("quote-reviewer", User.Role.STAFF)
        self.client.force_authenticate(staff)
        listing = self.client.get("/api/staff/enquiries/?search=Example%20Comet")
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(listing.data[0]["vehicle_description"], "2023 Example Comet")

    def test_staff_enquiry_list_loads_with_filters_and_denies_other_roles(self):
        response = self.client.post("/api/public/enquiries/", self.payload(
            kind="quote", vehicle_description="2024 Fictional Sedan", idempotency_key="filter-test-quote-001",
        ), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        staff = self.make_user("enquiry-list-staff", User.Role.STAFF)
        self.client.force_authenticate(staff)

        listing = self.client.get("/api/staff/enquiries/?kind=quote&status=new&search=Fictional%20Sedan")
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listing.data), 1)
        self.assertEqual(listing.data[0]["vehicle_description"], "2024 Fictional Sedan")
        self.assertEqual(listing.data[0]["status"], Enquiry.Status.NEW)

        for role in (User.Role.ADMIN, User.Role.REP):
            self.client.force_authenticate(self.make_user(f"denied-enquiry-{role}", role))
            denied = self.client.get("/api/staff/enquiries/")
            self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

    def test_vehicle_must_be_public_and_available_and_private_identifiers_never_return(self):
        available = self.make_vehicle()
        hidden = self.make_vehicle(Vehicle.Visibility.DRAFT)
        bad = self.client.post("/api/public/enquiries/", self.payload(vehicle_reference=hidden.reference), format="json")
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)
        good = self.client.post("/api/public/enquiries/", self.payload(vehicle_reference=available.reference), format="json")
        self.assertEqual(good.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("PRIVATE-CHASSIS-1", str(good.data))

    def test_vehicle_linked_appointment_is_saved_with_the_selected_vehicle(self):
        vehicle = self.make_vehicle()
        requested = timezone.now() + timedelta(days=2)
        response = self.client.post("/api/public/enquiries/", self.payload(
            kind="appointment", vehicle_reference=vehicle.reference,
            requested_at=requested.isoformat(), idempotency_key="appointment-request-12345",
        ), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        enquiry = Enquiry.objects.get(reference=response.data["reference"])
        self.assertEqual(enquiry.vehicle_id, vehicle.pk)
        self.assertEqual(enquiry.kind, Enquiry.Kind.APPOINTMENT)

    def test_public_enquiry_preflight_allows_idempotency_header(self):
        response = self.client.options("/api/public/enquiries/", HTTP_ORIGIN="http://localhost:3000",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,x-csrftoken,idempotency-key")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://localhost:3000")
        allowed_headers = response["Access-Control-Allow-Headers"].lower().split(", ")
        self.assertIn("idempotency-key", allowed_headers)

    def test_customer_and_enquiry_data_are_role_protected(self):
        self.client.post("/api/public/enquiries/", self.payload(), format="json")
        for role in (User.Role.ADMIN, User.Role.REP):
            self.client.force_authenticate(self.make_user(f"{role}-user", role))
            self.assertEqual(self.client.get("/api/staff/customers/").status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(self.client.get("/api/staff/enquiries/").status_code, status.HTTP_403_FORBIDDEN)
        for role in (User.Role.STAFF, User.Role.MANAGER, User.Role.CEO):
            self.client.force_authenticate(self.make_user(f"{role}-user", role))
            self.assertEqual(self.client.get("/api/staff/customers/").status_code, status.HTTP_200_OK)
            self.assertEqual(self.client.get("/api/staff/enquiries/").status_code, status.HTTP_200_OK)

    def test_appointment_requests_and_confirmed_schedule_remain_distinct_and_audited(self):
        requested = timezone.now() + timedelta(days=2)
        response = self.client.post("/api/public/enquiries/", self.payload(kind="appointment", requested_at=requested.isoformat()), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        enquiry = Enquiry.objects.get(reference=response.data["reference"])
        self.assertIsNone(enquiry.scheduled_at)
        self.assertEqual(enquiry.status, Enquiry.Status.NEW)
        manager = self.make_user("staff-agent", User.Role.STAFF)
        self.client.force_authenticate(manager)
        bad = self.client.patch(f"/api/staff/enquiries/{enquiry.pk}/", {"status": "scheduled"}, format="json")
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)
        confirmed = timezone.now() + timedelta(days=3)
        good = self.client.patch(f"/api/staff/enquiries/{enquiry.pk}/", {"status": "scheduled", "scheduled_at": confirmed.isoformat(), "internal_notes": "Called and confirmed."}, format="json")
        self.assertEqual(good.status_code, status.HTTP_200_OK)
        self.assertEqual(good.data["status"], "scheduled")
        self.assertEqual(good.data["internal_notes"], "Called and confirmed.")
        self.assertIsNotNone(good.data["scheduled_at"])
        enquiry.refresh_from_db()
        self.assertEqual(enquiry.internal_notes, "Called and confirmed.")
        self.assertEqual(enquiry.status, Enquiry.Status.SCHEDULED)
        self.assertEqual(enquiry.scheduled_at.isoformat(), confirmed.isoformat())
        reloaded = self.client.get("/api/staff/enquiries/")
        saved_row = next(row for row in reloaded.data if row["id"] == enquiry.pk)
        self.assertEqual(saved_row["status"], "scheduled")
        self.assertEqual(saved_row["internal_notes"], "Called and confirmed.")
        self.assertEqual(saved_row["scheduled_at"], good.data["scheduled_at"])
        self.assertTrue(AuditEvent.objects.filter(action="enquiry.updated", subject=enquiry.reference).exists())
        public_response = self.client.get("/api/public/enquiries/")
        self.assertEqual(public_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def make_appointment(self, email="buyer@example.test", status_value=Enquiry.Status.NEW, scheduled_at=None):
        customer = Customer.objects.create(full_name="Test Customer", email=email, phone="0771234567")
        return Enquiry.objects.create(customer=customer, kind=Enquiry.Kind.APPOINTMENT,
            preferred_contact="phone", requested_at=timezone.now() + timedelta(days=2),
            status=status_value, scheduled_at=scheduled_at)

    def schedule_enquiry(self, enquiry, when, notes=""):
        return self.client.patch(f"/api/staff/enquiries/{enquiry.pk}/", {
            "status": Enquiry.Status.SCHEDULED,
            "scheduled_at": when.isoformat(),
            "internal_notes": notes,
        }, format="json")

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
        COMPANY_LOCATION="Configured showroom",
        COMPANY_PHONE="+94112223333",
        COMPANY_EMAIL="hello@example.test",
    )
    def test_scheduling_sends_confirmation_without_internal_notes_and_same_time_save_does_not_resend(self):
        vehicle = self.make_vehicle()
        enquiry = self.make_appointment()
        enquiry.vehicle = vehicle
        enquiry.save(update_fields=("vehicle",))
        staff = self.make_user("appointment-staff", User.Role.STAFF)
        self.client.force_authenticate(staff)
        when = timezone.now() + timedelta(days=3)
        output = StringIO()
        with redirect_stdout(output), self.captureOnCommitCallbacks(execute=True):
            response = self.schedule_enquiry(enquiry, when, notes="PRIVATE staff note")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        enquiry.refresh_from_db()
        self.assertEqual(enquiry.confirmation_email_status, Enquiry.ConfirmationEmailStatus.SENT)
        self.assertEqual(enquiry.confirmation_email_recipient, "buyer@example.test")
        self.assertIsNotNone(enquiry.confirmation_email_sent_at)
        self.assertIn("Test Customer", output.getvalue())
        self.assertIn("Vehicle: 2023 Honda Vezel", output.getvalue())
        self.assertIn("Sri Lanka time (Asia/Colombo)", output.getvalue())
        self.assertIn("Configured showroom", output.getvalue())
        self.assertIn("+94112223333", output.getvalue())
        self.assertIn("hello@example.test", output.getvalue())
        self.assertNotIn("PRIVATE staff note", output.getvalue())
        self.assertIn("enquiry.confirmation_email", AuditEvent.objects.filter(subject=enquiry.reference).values_list("action", flat=True))

        previous_output = output.getvalue()
        with redirect_stdout(output), self.captureOnCommitCallbacks(execute=True):
            repeated = self.client.patch(f"/api/staff/enquiries/{enquiry.pk}/", {
                "status": Enquiry.Status.SCHEDULED,
                "scheduled_at": enquiry.scheduled_at.isoformat(),
                "internal_notes": "A notes-only change.",
            }, format="json")
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        self.assertEqual(output.getvalue(), previous_output)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_schedule_change_sends_updated_confirmation_and_quote_does_not_send(self):
        original_time = timezone.now() + timedelta(days=3)
        enquiry = self.make_appointment(status_value=Enquiry.Status.SCHEDULED, scheduled_at=original_time)
        enquiry.confirmation_email_status = Enquiry.ConfirmationEmailStatus.SENT
        enquiry.confirmation_email_schedule = original_time
        enquiry.confirmation_email_recipient = enquiry.customer.email
        enquiry.confirmation_email_sent_at = timezone.now()
        enquiry.save(update_fields=("confirmation_email_status", "confirmation_email_schedule", "confirmation_email_recipient", "confirmation_email_sent_at"))
        manager = self.make_user("appointment-manager", User.Role.MANAGER)
        self.client.force_authenticate(manager)
        output = StringIO()
        updated_time = original_time + timedelta(days=1)
        with redirect_stdout(output), self.captureOnCommitCallbacks(execute=True):
            response = self.schedule_enquiry(enquiry, updated_time)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        enquiry.refresh_from_db()
        self.assertEqual(enquiry.confirmation_email_status, Enquiry.ConfirmationEmailStatus.SENT)
        self.assertTrue(enquiry.confirmation_email_is_update)
        self.assertIn("has been updated", output.getvalue())

        quote_customer = Customer.objects.create(full_name="Quote Customer", email="quote@example.test")
        quote = Enquiry.objects.create(customer=quote_customer, kind=Enquiry.Kind.QUOTE,
            preferred_contact="phone", vehicle_description="A fictional vehicle")
        before = output.getvalue()
        with redirect_stdout(output), self.captureOnCommitCallbacks(execute=True):
            quote_response = self.client.patch(f"/api/staff/enquiries/{quote.pk}/", {
                "internal_notes": "Quote follow-up only.",
            }, format="json")
        self.assertEqual(quote_response.status_code, status.HTTP_200_OK)
        self.assertEqual(output.getvalue(), before)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_missing_address_is_persisted_and_failed_email_can_be_retried_safely(self):
        staff = self.make_user("email-retry-staff", User.Role.STAFF)
        self.client.force_authenticate(staff)
        no_email = self.make_appointment(email="")
        missing_time = timezone.now() + timedelta(days=4)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.schedule_enquiry(no_email, missing_time)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        no_email.refresh_from_db()
        self.assertEqual(no_email.confirmation_email_status, Enquiry.ConfirmationEmailStatus.NO_EMAIL)

        failed = self.make_appointment()
        failed_time = timezone.now() + timedelta(days=5)
        with patch(
            "accounts.appointment_email.send_customer_email", side_effect=RuntimeError("credential must not be persisted")
        ), self.captureOnCommitCallbacks(execute=True):
            failure_response = self.schedule_enquiry(failed, failed_time)
        self.assertEqual(failure_response.status_code, status.HTTP_200_OK)
        failed.refresh_from_db()
        self.assertEqual(failed.confirmation_email_status, Enquiry.ConfirmationEmailStatus.FAILED)
        self.assertIn("RuntimeError", failed.confirmation_email_error)
        self.assertNotIn("credential", failed.confirmation_email_error)
        self.assertEqual(failed.status, Enquiry.Status.SCHEDULED)

        output = StringIO()
        with redirect_stdout(output), self.captureOnCommitCallbacks(execute=True):
            retry = self.client.post(f"/api/staff/enquiries/{failed.pk}/retry-confirmation-email/", {}, format="json")
        self.assertEqual(retry.status_code, status.HTTP_200_OK)
        failed.refresh_from_db()
        self.assertEqual(failed.confirmation_email_status, Enquiry.ConfirmationEmailStatus.SENT)
        self.assertIn("buyer@example.test", output.getvalue())

        repeated_retry = self.client.post(f"/api/staff/enquiries/{failed.pk}/retry-confirmation-email/", {}, format="json")
        self.assertEqual(repeated_retry.status_code, status.HTTP_400_BAD_REQUEST)
