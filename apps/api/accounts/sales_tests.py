from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.test import APITestCase
from django.utils import timezone

from .models import (AuditEvent, BLApprovalRequest, CommissionLedgerEntry, Customer, Handover, ImportMilestone,
                     ImportOrder, Payment, RepresentativeProfile, Reservation, Sale, User, Vehicle)


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

    def test_import_order_requires_registered_ready_stock_then_completes_sale_payment_handover_and_commission(self):
        self.vehicle.visibility = Vehicle.Visibility.DRAFT
        self.vehicle.save(update_fields=["visibility"])
        rep_user = User.objects.create_user(username="import-sale-rep", password="Test-pass-912!", role=User.Role.REP)
        rep = RepresentativeProfile.objects.create(user=rep_user)
        self.client.force_authenticate(self.staff)
        created = self.client.post("/api/staff/imports/", {
            "customer_id": self.customer.pk, "vehicle_id": self.vehicle.pk,
            "vehicle_description": "Toyota Corolla import", "vehicle_details": "Fictional test vehicle",
            "country_of_origin": "Japan", "shipping_information": "Fictional freight",
            "estimated_arrival": "2026-12-20", "internal_notes": "Test only",
            "customer_updates": "Booking confirmed for test.",
        }, format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        order_ref = created.data["reference"]
        order = ImportOrder.objects.get(reference=order_ref)
        self.assertEqual(order.vehicle_id, self.vehicle.pk)
        self.assertEqual(order.status, ImportOrder.Status.NEW)

        self.client.force_authenticate(self.ceo)
        sale_payload = {"sale_type": "import", "import_reference": order_ref, "representative_id": rep.pk,
                        "agreed_price_lkr": "9750000.00", "sale_date": "2026-11-21"}
        blocked = self.client.post("/api/manager/sales/", sale_payload, format="json")
        self.assertEqual(blocked.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("Only ready imports", blocked.data["import_reference"])

        milestone_url = f"/api/staff/imports/{order_ref}/milestones/"
        self.client.force_authenticate(self.staff)
        booking = self.client.post(milestone_url, {
            "kind": "booking_confirmed",
            "customer_description": "Fictional booking confirmed.",
        }, format="json")
        self.assertEqual(booking.status_code, 201, booking.data)

        self.client.force_authenticate(self.ceo)
        advance = self.client.post("/api/staff/payments/", {
            "import_reference": order_ref,
            "amount_lkr": "100000.00",
            "method": "cash",
            "payment_type": "advance",
            "idempotency_key": "import-sale-integration-advance",
        }, format="json")
        self.assertEqual(advance.status_code, 201, advance.data)

        for kind, description in (("lc_opened", "Fictional letter of credit opened."),):
            response = self.client.post(milestone_url, {"kind": kind, "customer_description": description}, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.client.force_authenticate(self.staff)
        approval = self.client.post(f"/api/staff/imports/{order_ref}/bl-requests/",
                                    {"request_note": "Fictional carrier document ready."}, format="json")
        self.assertEqual(approval.status_code, status.HTTP_201_CREATED, approval.data)
        self.client.force_authenticate(self.ceo)
        decision = self.client.post(f"/api/staff/bl-requests/{approval.data['id']}/decision/",
                                    {"decision": "approved"}, format="json")
        self.assertEqual(decision.status_code, status.HTTP_200_OK, decision.data)
        self.client.force_authenticate(self.ceo)
        for kind, description in (("bl_issued", "Fictional bill of lading issued."),
                                  ("shipping", "Fictional shipment departed."),
                                  ("arrival", "Fictional vehicle arrived."),
                                  ("customs_clearance", "Fictional customs clearance completed."),
                                  ("ready_for_collection", "Fictional vehicle ready for collection.")):
            response = self.client.post(milestone_url, {"kind": kind, "customer_description": description}, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        order.refresh_from_db()
        self.assertEqual(order.status, ImportOrder.Status.READY_FOR_COLLECTION)
        self.assertEqual(order.vehicle_id, self.vehicle.pk)
        self.assertEqual(self.vehicle.status, Vehicle.Status.AVAILABLE)

        self.client.force_authenticate(self.manager)
        denied = self.client.post("/api/manager/sales/", sale_payload, format="json")
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(self.ceo)
        sale = self.client.post("/api/manager/sales/", sale_payload, format="json")
        self.assertEqual(sale.status_code, status.HTTP_201_CREATED, sale.data)
        self.assertEqual(sale.data["customer_id"], self.customer.pk)
        self.assertEqual(sale.data["vehicle_reference"], self.vehicle.reference)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.post(f"/api/manager/sales/{sale.data['reference']}/confirm/", {}, format="json").status_code, 403)

        self.client.force_authenticate(self.ceo)
        confirmed = self.client.post(f"/api/manager/sales/{sale.data['reference']}/confirm/", {}, format="json")
        self.assertEqual(confirmed.status_code, status.HTTP_200_OK, confirmed.data)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, Vehicle.Status.SOLD)

        payment = self.client.post("/api/staff/payments/", {
            "sale_reference": sale.data["reference"], "amount_lkr": "2400000.00", "method": "bank_transfer",
            "transaction_reference": "IMPORT-SALE-INTEGRATION-PAYMENT", "idempotency_key": "import-sale-integration-payment",
            "payment_date": "2026-11-21", "funds_cleared": True,
        }, format="json")
        self.assertEqual(payment.status_code, status.HTTP_201_CREATED, payment.data)
        self.assertEqual(payment.data["status"], Payment.Status.VERIFIED)
        summary = self.client.get(f"/api/manager/sales/{sale.data['reference']}/payments/summary/")
        self.assertEqual(summary.status_code, status.HTTP_200_OK)
        self.assertEqual(summary.data["verified_received_lkr"], Decimal("2500000.00"))
        self.assertEqual(summary.data["outstanding_balance_lkr"], Decimal("7250000.00"))

        today = timezone.localdate().isoformat()
        self.client.force_authenticate(self.ceo)
        policy = self.client.put("/api/commission-rules/brackets/", [{
            "minimum_lkr": "0", "maximum_lkr": None, "percentage": "2.5", "effective_date": today, "active": True,
        }], format="json")
        self.assertEqual(policy.status_code, status.HTTP_200_OK, policy.data)
        self.client.force_authenticate(self.staff)
        prepared = self.client.post("/api/staff/handovers/", {
            "sale_reference": sale.data["reference"],
            "delivery_date": "2026-11-27",
            "customer_acknowledgement": "Fictional customer acknowledges the delivery details.",
            "vehicle_condition_checklist": {key: True for key in ("bodywork", "interior", "tyres", "lights", "odometer")},
            "keys_documents_checklist": {key: True for key in ("keys", "registration_documents", "insurance_documents", "service_documents")},
        }, format="json")
        self.assertEqual(prepared.status_code, status.HTTP_201_CREATED, prepared.data)
        handover_ref = prepared.data["reference"]
        self.assertEqual(prepared.data["financial_summary"]["outstanding_balance_lkr"], Decimal("7250000.00"))
        detail = f"/api/staff/handovers/{handover_ref}/"
        self.assertEqual(self.client.post(f"{detail}submit/", {}, format="json").status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.post(f"{detail}approve-md/", {}, format="json").status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.ceo)
        approved = self.client.post(f"{detail}approve-ceo/", {}, format="json")
        self.assertEqual(approved.status_code, status.HTTP_200_OK, approved.data)
        self.client.force_authenticate(self.manager)
        finalized = self.client.post(f"{detail}finalize/", {}, format="json")
        self.assertEqual(finalized.status_code, status.HTTP_200_OK, finalized.data)
        self.assertTrue(finalized.data["commission_eligible"])
        self.assertEqual(finalized.data["financial_summary"]["outstanding_balance_lkr"], Decimal("7250000.00"))
        order.refresh_from_db(); self.vehicle.refresh_from_db()
        self.assertEqual(order.status, ImportOrder.Status.HANDED_OVER)
        self.assertEqual(self.vehicle.status, Vehicle.Status.HANDED_OVER)
        ledger = CommissionLedgerEntry.objects.get(sale__reference=sale.data["reference"])
        self.assertEqual(ledger.recipient_id, rep_user.pk)
        self.assertEqual(ledger.commission_rate_percent, Decimal("2.500"))

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

        self.client.force_authenticate(self.manager)
        first_payment = self.client.post("/api/staff/payments/", {"reservation_reference": reservation.reference,
            "amount_lkr": "250.00", "method": "bank_transfer", "transaction_reference": "FICTIONAL-TRANSFER-CLEARED",
            "funds_cleared": True, "idempotency_key": "reservation-transfer-cleared-001",
            "payment_date": "2026-11-21"}, format="json")
        second_payment = self.client.post("/api/staff/payments/", {"reservation_reference": reservation.reference,
            "amount_lkr": "250.00", "method": "cash", "transaction_reference": "FICTIONAL-CASH-RECEIVED",
            "idempotency_key": "reservation-cash-received-001", "payment_date": "2026-11-21"}, format="json")
        self.assertEqual(first_payment.status_code, status.HTTP_201_CREATED, first_payment.data)
        self.assertEqual(second_payment.status_code, status.HTTP_201_CREATED, second_payment.data)
        self.assertEqual(first_payment.data["status"], Payment.Status.VERIFIED)
        self.assertEqual(second_payment.data["status"], Payment.Status.VERIFIED)
        before_sale = self.client.get(f"/api/staff/reservations/{reservation.reference}/payments/summary/")
        self.assertEqual(before_sale.data["verified_received_lkr"], Decimal("500.00"))
        self.assertEqual(before_sale.data["pending_verification_lkr"], Decimal("0.00"))

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
        self.assertEqual(summary.data["verified_received_lkr"], Decimal("500.00"))
        self.assertEqual(summary.data["pending_verification_lkr"], Decimal("0.00"))
        self.assertEqual(summary.data["outstanding_balance_lkr"], Decimal("400.00"))
        self.client.force_authenticate(self.staff)
        eligible = self.client.get("/api/staff/handovers/eligible-sales/?search=" + draft.data["reference"])
        self.assertEqual(eligible.status_code, status.HTTP_200_OK)
        self.assertEqual([item["reference"] for item in eligible.data], [draft.data["reference"]])
        prepared = self.client.post("/api/staff/handovers/", {"sale_reference": draft.data["reference"],
            "internal_notes": "Manager approved delivery with LKR 400.00 outstanding; balance due by agreement."}, format="json")
        self.assertEqual(prepared.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.client.post("/api/staff/handovers/", {"sale_reference": draft.data["reference"]}, format="json").status_code,
                         status.HTTP_409_CONFLICT)
        self.assertEqual(prepared.data["financial_summary"]["verified_received_lkr"], Decimal("500.00"))
        self.assertEqual(prepared.data["financial_summary"]["pending_verification_lkr"], Decimal("0.00"))
        self.assertEqual(prepared.data["financial_summary"]["outstanding_balance_lkr"], Decimal("400.00"))
        self.assertEqual(prepared.data["internal_notes"], "Manager approved delivery with LKR 400.00 outstanding; balance due by agreement.")
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
        md_approval = self.client.post(f"{handover_url}approve-md/", {"comments": "Preparation reviewed."}, format="json")
        self.assertEqual(md_approval.status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.ceo)
        ceo_approval = self.client.post(f"{handover_url}approve-ceo/", {"comments": "Handover approved."}, format="json")
        self.assertEqual(ceo_approval.status_code, status.HTTP_200_OK, ceo_approval.data)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.get(f"/api/manager/sales/{draft.data['reference']}/payments/summary/").data[
            "outstanding_balance_lkr"], Decimal("400.00"))
        self.client.force_authenticate(self.manager)
        finalized = self.client.post(f"{handover_url}finalize/", {}, format="json")
        self.assertEqual(finalized.status_code, status.HTTP_200_OK)
        self.assertTrue(finalized.data["commission_eligible"])
        self.assertEqual(finalized.data["financial_summary"]["outstanding_balance_lkr"], Decimal("400.00"))
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
        options = self.client.get("/api/manager/sales/options/")
        self.assertEqual(options.status_code, 200)
        self.assertEqual(options.data["vehicles"], [])
        self.assertEqual(options.data["reservations"], [])
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get("/api/manager/sales/summary/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/api/manager/sales/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post("/api/manager/sales/", self.payload(), format="json").status_code, status.HTTP_403_FORBIDDEN)

    def test_reserved_vehicle_cannot_be_sold_without_its_active_reservation(self):
        self.vehicle.status = Vehicle.Status.RESERVED
        self.vehicle.save(update_fields=["status"])
        response = self.create_draft(self.vehicle)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
