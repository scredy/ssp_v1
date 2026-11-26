from decimal import Decimal

from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from .models import AuditEvent, BLApprovalRequest, Customer, ImportMilestone, ImportOrder, ImportTrackingAccess, Payment, Sale, User, Vehicle


class ImportApiTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="import-staff", password="Import-Test-912!", role=User.Role.STAFF)
        self.manager = User.objects.create_user(username="import-manager", password="Import-Test-912!", role=User.Role.MANAGER)
        self.ceo = User.objects.create_user(username="import-ceo", password="Import-Test-912!", role=User.Role.CEO)
        self.rep = User.objects.create_user(username="import-rep", password="Import-Test-912!", role=User.Role.REP)
        self.admin = User.objects.create_user(username="import-admin", password="Import-Test-912!", role=User.Role.ADMIN)
        self.customer = Customer.objects.create(full_name="Import Customer", email="import-private@example.test", phone="0770000000")
        self.vehicle = Vehicle.objects.create(make="Toyota", model="Import Test", manufacture_year=2024,
            mileage_km=0, fuel_type=Vehicle.FuelType.HYBRID, transmission=Vehicle.Transmission.AUTOMATIC,
            color="Silver", condition=Vehicle.Condition.NEW, internal_identifier="IMPORT-PRIVATE-CHASSIS",
            asking_price_lkr=Decimal("10000000"))

    def payload(self, **extra):
        return {"customer_id": self.customer.pk, "vehicle_id": self.vehicle.pk,
            "vehicle_description": "Toyota import vehicle", "vehicle_details": "Private chassis and broker file",
            "country_of_origin": "Japan", "shipping_information": "Private freight notes",
            "estimated_arrival": "2027-01-15", "internal_notes": "Confidential staff notes",
            "customer_updates": "Booking is being arranged.", **extra}

    def create_import(self, user=None, payload=None):
        self.client.force_authenticate(user or self.staff)
        return self.client.post("/api/staff/imports/", payload or self.payload(), format="json")

    def test_staff_can_create_import_without_creating_inventory_or_selling_vehicle(self):
        response = self.create_import()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = ImportOrder.objects.get(reference=response.data["reference"])
        self.assertEqual(order.status, ImportOrder.Status.NEW)
        self.assertEqual(order.responsible_staff, self.staff)
        self.assertEqual(Vehicle.objects.count(), 1)
        self.assertEqual(self.vehicle.status, Vehicle.Status.AVAILABLE)
        self.assertTrue(AuditEvent.objects.filter(action="import.created", subject=order.reference).exists())
        self.client.force_authenticate(self.manager)
        summary = self.client.get("/api/staff/imports/summary/")
        self.assertEqual(summary.data["total_count"], 1)
        self.assertEqual(summary.data["status_counts"][ImportOrder.Status.NEW], 1)

    def test_role_permissions_enforce_staff_write_and_leadership_read_only(self):
        created = self.create_import()
        detail = f"/api/staff/imports/{created.data['reference']}/"
        for user in (self.ceo, self.manager):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get("/api/staff/imports/").status_code, status.HTTP_200_OK)
            self.assertEqual(self.client.get(detail).status_code, status.HTTP_200_OK)
            self.assertEqual(self.client.post("/api/staff/imports/", self.payload(), format="json").status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(self.client.patch(detail, {"customer_updates": "Changed"}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        for user in (self.rep, self.admin):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get("/api/staff/imports/").status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(self.client.post("/api/staff/imports/", self.payload(), format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/staff/imports/").status_code, status.HTTP_403_FORBIDDEN)

    def test_milestones_are_append_only_and_follow_operational_prerequisites(self):
        order = self.create_import().data
        endpoint = f"/api/staff/imports/{order['reference']}/milestones/"
        self.client.force_authenticate(self.staff)
        blocked = self.client.post(endpoint, {"kind": "shipping", "customer_description": "Shipping started."}, format="json")
        self.assertEqual(blocked.status_code, status.HTTP_409_CONFLICT)
        booking = self.client.post(endpoint, {"kind": "booking_confirmed", "customer_description": "Your import booking is confirmed."}, format="json")
        self.assertEqual(booking.status_code, status.HTTP_201_CREATED)
        lc = self.client.post(endpoint, {"kind": "lc_opened", "customer_description": "The letter of credit has been opened."}, format="json")
        self.assertEqual(lc.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.client.post(endpoint, {"kind": "lc_opened", "customer_description": "Duplicate."}, format="json").status_code, status.HTTP_409_CONFLICT)
        milestone = ImportMilestone.objects.get(pk=booking.data["id"])
        milestone.customer_description = "Rewritten"
        with self.assertRaises(ValidationError):
            milestone.save()
        with self.assertRaises(ValidationError):
            milestone.delete()
        with self.assertRaises(ValidationError):
            ImportMilestone.objects.filter(pk=milestone.pk).update(customer_description="Rewritten")
        self.assertEqual(self.client.post(endpoint, {"kind": "finalized_handover", "customer_description": "Done."}, format="json").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.post(endpoint, {"kind": "payment_verified", "customer_description": "Payment verified."}, format="json").status_code, status.HTTP_400_BAD_REQUEST)

    def test_immediately_confirmed_payment_can_be_linked_to_financial_milestone(self):
        order = self.create_import().data
        endpoint = f"/api/staff/imports/{order['reference']}/milestones/"
        self.client.force_authenticate(self.staff)
        body = {"kind": "payment_verified", "customer_description": "A payment has been verified."}
        self.assertEqual(self.client.post(endpoint, body, format="json").status_code, status.HTTP_400_BAD_REQUEST)
        booking = self.client.post(endpoint, {"kind": "booking_confirmed", "customer_description": "Booking confirmed."}, format="json")
        self.assertEqual(booking.status_code, status.HTTP_201_CREATED)
        self.client.force_authenticate(self.manager)
        payment_response = self.client.post("/api/staff/payments/", {"import_reference": order["reference"],
            "amount_lkr": "100", "method": "cash", "transaction_reference": "IMPORT-MILESTONE-TEST",
            "idempotency_key": "import-milestone-payment-test"}, format="json")
        self.assertEqual(payment_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(payment_response.data["status"], Payment.Status.VERIFIED)
        payment = Payment.objects.get(reference=payment_response.data["reference"])
        self.client.force_authenticate(self.staff)
        body["payment_reference"] = payment.reference
        verified = self.client.post(endpoint, body, format="json")
        self.assertEqual(verified.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("payment_reference", verified.data)

    def test_bl_approval_is_ceo_only_reasoned_and_separate_from_bl_issuance(self):
        order = self.create_import().data
        request_url = f"/api/staff/imports/{order['reference']}/bl-requests/"
        self.client.force_authenticate(self.staff)
        approval = self.client.post(request_url, {"request_note": "Carrier documents are ready."}, format="json")
        self.assertEqual(approval.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.client.post(request_url, {}, format="json").status_code, status.HTTP_409_CONFLICT)
        decision_url = f"/api/staff/bl-requests/{approval.data['id']}/decision/"
        self.assertEqual(self.client.post(decision_url, {"decision": "approved"}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.ceo)
        missing_reason = self.client.post(decision_url, {"decision": "rejected"}, format="json")
        self.assertEqual(missing_reason.status_code, status.HTTP_400_BAD_REQUEST)
        decided = self.client.post(decision_url, {"decision": "approved"}, format="json")
        self.assertEqual(decided.status_code, status.HTTP_200_OK)
        self.assertEqual(decided.data["status"], BLApprovalRequest.Status.APPROVED)
        self.assertIsNotNone(decided.data["decided_at"])
        self.assertEqual(self.client.post(decision_url, {"decision": "rejected", "rejection_reason": "Late"}, format="json").status_code, status.HTTP_409_CONFLICT)
        order_detail = self.client.get(f"/api/staff/imports/{order['reference']}/").data
        self.assertEqual(order_detail["status"], ImportOrder.Status.NEW)
        self.client.force_authenticate(self.staff)
        milestone_url = f"/api/staff/imports/{order['reference']}/milestones/"
        self.client.post(milestone_url, {"kind": "booking_confirmed", "customer_description": "Booking confirmed."}, format="json")
        self.client.post(milestone_url, {"kind": "lc_opened", "customer_description": "LC opened."}, format="json")
        issued = self.client.post(milestone_url, {"kind": "bl_issued", "customer_description": "Bill of lading issued."}, format="json")
        self.assertEqual(issued.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ImportOrder.objects.get(reference=order["reference"]).status, ImportOrder.Status.BL_ISSUED)

    def test_bl_rejection_requires_reason_and_preserves_decision_history(self):
        order = self.create_import().data
        self.client.force_authenticate(self.staff)
        approval = self.client.post(f"/api/staff/imports/{order['reference']}/bl-requests/", {}, format="json")
        self.client.force_authenticate(self.ceo)
        endpoint = f"/api/staff/bl-requests/{approval.data['id']}/decision/"
        rejected = self.client.post(endpoint, {"decision": "rejected", "rejection_reason": "Carrier detail needs correction."}, format="json")
        self.assertEqual(rejected.status_code, status.HTTP_200_OK)
        self.assertEqual(rejected.data["rejection_reason"], "Carrier detail needs correction.")
        self.assertEqual(rejected.data["decided_by_name"], self.ceo.username)
        self.assertTrue(AuditEvent.objects.filter(action="import.bl_approval_rejected", subject=approval.data["reference"]).exists())

    def test_tracking_pin_is_hashed_and_public_response_exposes_only_customer_safe_data(self):
        order = self.create_import().data
        self.client.force_authenticate(self.staff)
        access_response = self.client.post(f"/api/staff/imports/{order['reference']}/tracking-access/", {}, format="json")
        self.assertEqual(access_response.status_code, status.HTTP_200_OK)
        access = ImportTrackingAccess.objects.get(import_order__reference=order["reference"])
        self.assertNotEqual(access.pin_hash, access_response.data["pin"])
        self.assertTrue(check_password(access_response.data["pin"], access.pin_hash))
        self.client.post(f"/api/staff/imports/{order['reference']}/milestones/", {"kind": "booking_confirmed", "customer_description": "Your booking is confirmed."}, format="json")
        public = self.client.post("/api/public/import-tracking/", {"tracking_reference": access.tracking_reference, "pin": access_response.data["pin"]}, format="json")
        self.assertEqual(public.status_code, status.HTTP_200_OK)
        for private_field in ("email", "phone", "customer_name", "vehicle_details", "internal_notes", "shipping_information", "pin", "pin_hash"):
            self.assertNotIn(private_field, public.data)
        self.assertEqual(public.data["milestones"][0]["description"], "Your booking is confirmed.")
        self.assertTrue(AuditEvent.objects.filter(action="import.tracking_access_issued", subject=order["reference"]).exists())
        rotated = self.client.post(f"/api/staff/imports/{order['reference']}/tracking-access/", {}, format="json")
        self.assertEqual(rotated.status_code, status.HTTP_200_OK)
        self.assertNotEqual(rotated.data["pin"], access_response.data["pin"])
        self.assertTrue(AuditEvent.objects.filter(action="import.tracking_access_rotated", subject=order["reference"]).exists())

    def test_tracking_invalid_credentials_are_generic_and_rate_limited(self):
        order = self.create_import().data
        self.client.force_authenticate(self.staff)
        access = self.client.post(f"/api/staff/imports/{order['reference']}/tracking-access/", {}, format="json").data
        self.client.force_authenticate(None)
        url = "/api/public/import-tracking/"
        unknown = self.client.post(url, {"tracking_reference": "TRK-UNKNOWN", "pin": "incorrect"}, format="json")
        wrong = self.client.post(url, {"tracking_reference": access["tracking_reference"], "pin": "incorrect"}, format="json")
        self.assertEqual(unknown.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(unknown.data, wrong.data)
        self.assertEqual(unknown.data["detail"], "Invalid tracking reference or PIN.")
        cache.clear()
        for _ in range(5):
            self.assertEqual(self.client.post(url, {"tracking_reference": "TRK-UNKNOWN", "pin": "wrong"}, format="json").status_code, status.HTTP_404_NOT_FOUND)
        limited = self.client.post(url, {"tracking_reference": "TRK-UNKNOWN", "pin": "wrong"}, format="json")
        self.assertEqual(limited.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
