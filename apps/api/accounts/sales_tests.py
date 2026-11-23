from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.test import APITestCase

from .models import AuditEvent, CommissionLedgerEntry, Customer, Handover, Payment, RepresentativeProfile, Reservation, Sale, User, Vehicle


class SalesApiTests(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="sales-manager", password="Test-pass-912!", role=User.Role.MANAGER)
        self.ceo = User.objects.create_user(username="sales-ceo", password="Test-pass-912!", role=User.Role.CEO)
        self.staff = User.objects.create_user(username="sales-staff", password="Test-pass-912!", role=User.Role.STAFF)
        self.customer = Customer.objects.create(full_name="Sale Customer", email="sale@example.test")
        self.vehicle = self.make_vehicle("A")

    def make_vehicle(self, suffix):
        return Vehicle.objects.create(make="Toyota", model="Corolla", manufacture_year=2023, mileage_km=12000,
            fuel_type=Vehicle.FuelType.PETROL, transmission=Vehicle.Transmission.AUTOMATIC, color="White",
            condition=Vehicle.Condition.USED, internal_identifier=f"SALE-CHASSIS-{suffix}", asking_price_lkr="10000000",
            visibility=Vehicle.Visibility.PUBLISHED)

    def payload(self, vehicle=None, **extra):
        return {"customer_id": self.customer.pk, "vehicle_reference": (vehicle or self.vehicle).reference,
                "agreed_price_lkr": "9750000.00", "sale_date": "2026-11-21", **extra}

    def create_draft(self, vehicle=None, **extra):
        self.client.force_authenticate(self.manager)
        return self.client.post("/api/manager/sales/", self.payload(vehicle, **extra), format="json")

    def test_direct_sale_creation_and_confirmation_marks_stock_sold_and_hides_public_listing(self):
        response = self.create_draft()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], Sale.Status.DRAFT)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, Vehicle.Status.AVAILABLE)
        confirmed = self.client.post(f"/api/manager/sales/{response.data['reference']}/confirm/", {}, format="json")
        self.assertEqual(confirmed.status_code, status.HTTP_200_OK)
        self.assertEqual(confirmed.data["status"], Sale.Status.CONFIRMED)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, Vehicle.Status.SOLD)
        self.assertNotIn(self.vehicle.reference, [v["reference"] for v in self.client.get("/api/cars/").data])
        self.assertTrue(AuditEvent.objects.filter(action="sale.confirmed", subject=response.data["reference"]).exists())

    def test_reserved_vehicle_sale_converts_matching_reservation_and_preserves_it(self):
        self.vehicle.status = Vehicle.Status.RESERVED
        self.vehicle.save(update_fields=["status"])
        reservation = Reservation.objects.create(customer=self.customer, vehicle=self.vehicle,
            responsible_staff=self.staff, agreed_price_lkr=Decimal("9750000"), advance_amount_lkr=Decimal("100000"))
        draft = self.create_draft(self.vehicle, reservation_reference=reservation.reference)
        self.assertEqual(draft.status_code, status.HTTP_201_CREATED)
        confirmed = self.client.post(f"/api/manager/sales/{draft.data['reference']}/confirm/", {}, format="json")
        self.assertEqual(confirmed.status_code, status.HTTP_200_OK)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CONVERTED)
        self.assertEqual(Reservation.objects.count(), 1)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, Vehicle.Status.SOLD)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.post(f"/api/staff/reservations/{reservation.reference}/release/", {"release_reason": "no"}, format="json").status_code, status.HTTP_409_CONFLICT)

    def test_reservation_conversion_carries_customer_vehicle_and_advances_to_handover_with_unpaid_balance(self):
        self.client.force_authenticate(self.staff)
        manual_customer = self.client.post("/api/staff/customers/", {"full_name": "Fictional Walk-in Client",
            "phone": "077 555-0123", "email": "walkin-client@example.test", "preferred_contact": "phone"}, format="json")
        self.assertEqual(manual_customer.status_code, status.HTTP_201_CREATED)
        customer_id = manual_customer.data["customer"]["id"]
        reserved = self.client.post("/api/staff/reservations/", {
            "customer_id": customer_id, "vehicle_reference": self.vehicle.reference,
            "agreed_price_lkr": "1000.00", "advance_amount_lkr": "500.00",
        }, format="json")
        self.assertEqual(reserved.status_code, status.HTTP_201_CREATED)
        reservation = Reservation.objects.get(reference=reserved.data["reference"])
        self.assertEqual(reservation.customer_id, customer_id)

        pending = self.client.post("/api/staff/payments/", {"reservation_reference": reservation.reference,
            "amount_lkr": "250.00", "method": "bank_transfer", "transaction_reference": "FICTIONAL-TRANSFER-PENDING",
            "payment_date": "2026-11-21"}, format="json")
        verified = self.client.post("/api/staff/payments/", {"reservation_reference": reservation.reference,
            "amount_lkr": "250.00", "method": "cash", "transaction_reference": "FICTIONAL-CASH-VERIFIED",
            "payment_date": "2026-11-21"}, format="json")
        self.assertEqual(pending.status_code, status.HTTP_201_CREATED)
        self.assertEqual(verified.status_code, status.HTTP_201_CREATED)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.post(f"/api/staff/payments/{verified.data['reference']}/verify/", {}, format="json").status_code,
                         status.HTTP_200_OK)
        before_sale = self.client.get(f"/api/staff/reservations/{reservation.reference}/payments/summary/")
        self.assertEqual(before_sale.data["verified_received_lkr"], Decimal("250.00"))
        self.assertEqual(before_sale.data["pending_verification_lkr"], Decimal("250.00"))

        rep_user = User.objects.create_user(username="sale-assigned-rep", password="Test-pass-912!", role=User.Role.REP)
        rep = RepresentativeProfile.objects.create(user=rep_user)
        reservation_option = next(item for item in self.client.get("/api/manager/sales/options/").data["reservations"]
                                 if item["reference"] == reservation.reference)
        self.assertEqual(reservation_option["customer_id"], customer_id)
        self.assertEqual(reservation_option["agreed_price_lkr"], Decimal("1000.00"))
        sale_payload = {"reservation_reference": reservation.reference, "agreed_price_lkr": "900.00",
                        "sale_date": "2026-11-21", "representative_id": rep.pk}
        draft = self.client.post("/api/manager/sales/", sale_payload, format="json")
        self.assertEqual(draft.status_code, status.HTTP_201_CREATED)
        self.assertEqual(draft.data["customer_id"], customer_id)
        self.assertEqual(draft.data["vehicle_reference"], self.vehicle.reference)
        self.assertEqual(draft.data["representative_id"], rep.pk)
        self.assertEqual(draft.data["reservation_reference"], reservation.reference)
        duplicate = self.client.post("/api/manager/sales/", sale_payload, format="json")
        self.assertEqual(duplicate.status_code, status.HTTP_409_CONFLICT)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Sale.objects.create(vehicle=self.vehicle, customer=reservation.customer, reservation=reservation,
                agreed_price_lkr=Decimal("900.00"), created_by=self.manager)

        self.client.force_authenticate(self.ceo)
        self.assertEqual(self.client.post(f"/api/manager/sales/{draft.data['reference']}/confirm/", {}, format="json").status_code,
                         status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.manager)
        confirmed = self.client.post(f"/api/manager/sales/{draft.data['reference']}/confirm/", {}, format="json")
        self.assertEqual(confirmed.status_code, status.HTTP_200_OK)
        self.vehicle.refresh_from_db(); reservation.refresh_from_db()
        self.assertEqual(self.vehicle.status, Vehicle.Status.SOLD)
        self.assertEqual(reservation.status, Reservation.Status.CONVERTED)
        summary = self.client.get(f"/api/manager/sales/{draft.data['reference']}/payments/summary/")
        self.assertEqual(summary.data["verified_received_lkr"], Decimal("250.00"))
        self.assertEqual(summary.data["pending_verification_lkr"], Decimal("250.00"))
        self.assertEqual(summary.data["outstanding_balance_lkr"], Decimal("650.00"))
        self.client.force_authenticate(self.staff)
        eligible = self.client.get("/api/staff/handovers/eligible-sales/?search=" + draft.data["reference"])
        self.assertEqual(eligible.status_code, status.HTTP_200_OK)
        self.assertEqual([item["reference"] for item in eligible.data], [draft.data["reference"]])
        prepared = self.client.post("/api/staff/handovers/", {"sale_reference": draft.data["reference"],
            "internal_notes": "Manager approved delivery with LKR 650.00 outstanding; balance due by agreement."}, format="json")
        self.assertEqual(prepared.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.client.post("/api/staff/handovers/", {"sale_reference": draft.data["reference"]}, format="json").status_code,
                         status.HTTP_409_CONFLICT)
        self.assertEqual(prepared.data["financial_summary"]["verified_received_lkr"], Decimal("250.00"))
        self.assertEqual(prepared.data["financial_summary"]["pending_verification_lkr"], Decimal("250.00"))
        self.assertEqual(prepared.data["financial_summary"]["outstanding_balance_lkr"], Decimal("650.00"))
        self.assertEqual(prepared.data["internal_notes"], "Manager approved delivery with LKR 650.00 outstanding; balance due by agreement.")
        handover_url = f"/api/staff/handovers/{prepared.data['reference']}/"
        checklist = {key: True for key in ("bodywork", "interior", "tyres", "lights", "odometer")}
        documents = {key: True for key in ("keys", "registration_documents", "insurance_documents", "service_documents")}
        ready = self.client.patch(handover_url, {"delivery_date": "2026-11-21", "vehicle_condition_checklist": checklist,
            "keys_documents_checklist": documents, "customer_acknowledgement": "Fictional customer acknowledged delivery."}, format="json")
        self.assertEqual(ready.status_code, status.HTTP_200_OK)
        submitted = self.client.post(f"{handover_url}submit/", {}, format="json")
        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        self.assertEqual(submitted.data["commission_eligible"], False)
        self.assertFalse(CommissionLedgerEntry.objects.filter(sale__reference=draft.data["reference"]).exists())
        self.assertEqual(self.client.post(f"{handover_url}finalize/", {}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.manager)
        finalized = self.client.post(f"{handover_url}finalize/", {}, format="json")
        self.assertEqual(finalized.status_code, status.HTTP_200_OK)
        self.assertTrue(finalized.data["commission_eligible"])
        self.assertEqual(finalized.data["financial_summary"]["outstanding_balance_lkr"], Decimal("650.00"))
        self.assertEqual(CommissionLedgerEntry.objects.filter(sale__reference=draft.data["reference"]).count(), 1)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, Vehicle.Status.HANDED_OVER)

    def test_double_sale_and_invalid_vehicle_transition_are_prevented(self):
        first = self.create_draft()
        second = self.create_draft()
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.client.post(f"/api/manager/sales/{first.data['reference']}/confirm/", {}, format="json").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.post(f"/api/manager/sales/{second.data['reference']}/confirm/", {}, format="json").status_code, status.HTTP_409_CONFLICT)
        self.vehicle.refresh_from_db()
        self.vehicle.status = Vehicle.Status.AVAILABLE
        with self.assertRaises(ValidationError):
            self.vehicle.save(update_fields=["status"])
        with self.assertRaises(IntegrityError), transaction.atomic():
            Sale.objects.create(vehicle=self.vehicle, customer=self.customer, agreed_price_lkr=Decimal("9000000"),
                status=Sale.Status.CONFIRMED, created_by=self.manager)

    def test_role_permissions_and_summary_scope(self):
        for user in (self.manager, self.ceo):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get("/api/manager/sales/").status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.ceo)
        self.assertEqual(self.client.post("/api/manager/sales/", self.payload(), format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get("/api/manager/sales/options/").status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get("/api/manager/sales/summary/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/api/manager/sales/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post("/api/manager/sales/", self.payload(), format="json").status_code, status.HTTP_403_FORBIDDEN)

    def test_reserved_vehicle_cannot_be_sold_without_its_active_reservation(self):
        self.vehicle.status = Vehicle.Status.RESERVED
        self.vehicle.save(update_fields=["status"])
        response = self.create_draft(self.vehicle)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
