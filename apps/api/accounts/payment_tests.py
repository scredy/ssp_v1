from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless
from uuid import uuid4

from django.conf import settings
from django.db import close_old_connections, connections
from django.test import TransactionTestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from .models import AuditEvent, Customer, ImportOrder, Payment, Reservation, Sale, User, Vehicle


class PaymentApiTests(APITestCase):
    def user(self, username, role):
        return User.objects.create_user(username=username, password="Payments-Test-345!", role=role,
                                        email=f"{username}@example.test")

    def make_vehicle(self, suffix="1"):
        return Vehicle.objects.create(make="Toyota", model="Payment Test", manufacture_year=2023,
            mileage_km=10000, fuel_type=Vehicle.FuelType.PETROL, transmission=Vehicle.Transmission.AUTOMATIC,
            color="Silver", condition=Vehicle.Condition.USED, internal_identifier=f"PAYMENT-CHASSIS-{suffix}",
            asking_price_lkr=Decimal("1000000"), visibility=Vehicle.Visibility.PUBLISHED)

    def setUp(self):
        self.staff = self.user("payment-staff", User.Role.STAFF)
        self.manager = self.user("payment-manager", User.Role.MANAGER)
        self.ceo = self.user("payment-ceo", User.Role.CEO)
        self.admin = self.user("payment-admin", User.Role.ADMIN)
        self.rep = self.user("payment-rep", User.Role.REP)
        self.customer = Customer.objects.create(full_name="Payment Test Customer", email="pay@example.test")
        self.vehicle = self.make_vehicle()
        self.sale = Sale.objects.create(vehicle=self.vehicle, customer=self.customer, agreed_price_lkr=Decimal("1000.00"), created_by=self.manager)

    def tearDown(self):
        for payment in Payment.objects.exclude(evidence="").iterator():
            payment.evidence.storage.delete(payment.evidence.name)
        super().tearDown()

    def sale_payload(self, **overrides):
        return {"sale_reference": self.sale.reference, "amount_lkr": "250.00", "method": "bank_transfer",
                "transaction_reference": "BANK-PAYMENT-001", "funds_cleared": True, "payment_date": "2026-11-21", **overrides}

    def record_payment(self, user=None, payload=None):
        self.client.force_authenticate(user or self.manager)
        data = dict(payload or self.sale_payload())
        data.setdefault("idempotency_key", uuid4().hex)
        return self.client.post("/api/staff/payments/", data, format="json")

    def make_import(self, user=None, customer=None):
        self.client.force_authenticate(user or self.staff)
        return self.client.post("/api/staff/imports/", {"customer_id": (customer or self.customer).pk,
            "vehicle_description": "Toyota import order", "country_of_origin": "Japan"}, format="json")

    def import_payment(self, reference, transaction_reference="IMPORT-PAYMENT-001", user=None):
        return self.record_payment(user or self.manager, {"import_reference": reference, "amount_lkr": "125.50",
            "method": "bank_transfer", "transaction_reference": transaction_reference, "funds_cleared": True, "payment_date": "2026-11-21"})

    def test_import_payment_without_vehicle_verification_summary_and_milestone(self):
        created = self.make_import(self.staff)
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        order = ImportOrder.objects.get(reference=created.data["reference"])
        self.assertIsNone(order.vehicle_id)
        response = self.import_payment(order.reference)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["import_reference"], order.reference)
        self.assertEqual(response.data["status"], Payment.Status.VERIFIED)
        self.client.force_authenticate(self.staff)
        summary = self.client.get(f"/api/staff/imports/{order.reference}/payments/summary/")
        self.assertEqual(Decimal(summary.data["verified_amount_lkr"]), Decimal("125.50"))
        self.assertIsNone(summary.data["outstanding_balance_lkr"])
        milestone = self.client.post(f"/api/staff/imports/{order.reference}/milestones/", {
            "kind": "payment_verified", "payment_reference": response.data["reference"],
            "customer_description": "A payment for this import has been verified."}, format="json")
        self.assertEqual(milestone.status_code, status.HTTP_201_CREATED)

    def test_import_payment_permissions_customer_consistency_and_no_double_count(self):
        created = self.make_import(self.staff)
        order = ImportOrder.objects.get(reference=created.data["reference"])
        self.client.force_authenticate(self.staff)
        denied = self.import_payment(order.reference, "IMPORT-STAFF-DENIED", self.staff)
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.manager)
        payment = self.import_payment(order.reference, "IMPORT-PAYMENT-REJECT", self.manager)
        self.assertEqual(payment.status_code, status.HTTP_201_CREATED)
        other_customer = Customer.objects.create(full_name="Different Import Customer")
        other_import = ImportOrder.objects.create(customer=other_customer, vehicle_description="Other vehicle",
            country_of_origin="Japan", responsible_staff=self.staff)
        self.client.force_authenticate(self.staff)
        mismatch = self.client.post(f"/api/staff/imports/{other_import.reference}/milestones/", {
            "kind": "payment_verified", "payment_reference": payment.data["reference"],
            "customer_description": "Should not be allowed."}, format="json")
        self.assertEqual(mismatch.status_code, status.HTTP_409_CONFLICT)
        self.client.force_authenticate(self.ceo)
        rejected = self.client.post(f"/api/staff/payments/{payment.data['reference']}/reject/",
            {"rejection_reason": "Transfer receipt could not be matched."}, format="json")
        self.assertEqual(rejected.status_code, status.HTTP_409_CONFLICT)
        duplicate = self.import_payment(order.reference, "IMPORT-PAYMENT-REJECT", self.manager)
        self.assertEqual(duplicate.status_code, status.HTTP_409_CONFLICT)
        self.client.force_authenticate(self.manager)
        reversed_payment = self.client.post(f"/api/staff/payments/{payment.data['reference']}/reverse/",
            {"reason": "Duplicate import payment record."}, format="json")
        self.assertEqual(reversed_payment.status_code, status.HTTP_200_OK)
        self.assertEqual(reversed_payment.data["status"], Payment.Status.REVERSED)
        good = self.import_payment(order.reference, "IMPORT-PAYMENT-VERIFIED", self.manager)
        self.assertEqual(good.data["status"], Payment.Status.VERIFIED)
        order.vehicle = self.vehicle
        order.save(update_fields=["vehicle"])
        sale = Sale.objects.create(vehicle=self.vehicle, customer=self.customer, import_order=order,
            agreed_price_lkr=Decimal("1000.00"), created_by=self.manager)
        import_summary = self.client.get(f"/api/staff/imports/{order.reference}/payments/summary/")
        sale_summary = self.client.get(f"/api/manager/sales/{sale.reference}/payments/summary/")
        self.assertEqual(Decimal(import_summary.data["verified_amount_lkr"]), Decimal("125.50"))
        self.assertEqual(Decimal(sale_summary.data["verified_received_lkr"]), Decimal("125.50"))
        self.assertEqual(Payment.objects.filter(import_order=order).count(), 2)

    def test_import_agreed_price_and_remaining_payment_workflow(self):
        created = self.make_import()
        order = ImportOrder.objects.get(reference=created.data["reference"])
        url = f"/api/staff/imports/{order.reference}/payments/summary/"

        advance = self.import_payment(order.reference)
        self.assertEqual(advance.status_code, status.HTTP_201_CREATED)

        payload = {"agreed_price_lkr": "1000.00", "reason": "Customer agreement"}
        for denied in (self.staff, self.rep, self.admin):
            self.client.force_authenticate(denied)
            self.assertEqual(
                self.client.patch(url, payload, format="json").status_code,
                status.HTTP_403_FORBIDDEN,
            )

        self.client.force_authenticate(self.ceo)
        too_low = self.client.patch(url, {
            **payload, "agreed_price_lkr": "100.00"
        }, format="json")
        self.assertEqual(too_low.status_code, status.HTTP_400_BAD_REQUEST)

        saved = self.client.patch(url, payload, format="json")
        self.assertEqual(saved.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(saved.data["agreed_price_lkr"]), Decimal("1000.00"))
        self.assertEqual(Decimal(saved.data["outstanding_balance_lkr"]), Decimal("874.50"))
        self.assertTrue(AuditEvent.objects.filter(
            action="import.agreed_price.updated", subject=order.reference
        ).exists())

        overpayment = self.record_payment(self.manager, {
            "import_reference": order.reference,
            "amount_lkr": "875.00",
            "method": "cash",
        })
        self.assertEqual(overpayment.status_code, status.HTTP_409_CONFLICT)

        pending = Payment.objects.create(
            import_order=order, amount_lkr=Decimal("875.00"),
            method=Payment.Method.CASH, recorded_by=self.staff,
            status=Payment.Status.PENDING,
        )
        self.client.force_authenticate(self.ceo)
        result = self.client.post(
            f"/api/staff/payments/{pending.reference}/verify/", {}, format="json"
        )
        self.assertEqual(result.status_code, status.HTTP_409_CONFLICT)

        partial = self.record_payment(self.manager, {
            "import_reference": order.reference,
            "amount_lkr": "374.50",
            "method": "cash",
        })
        self.assertEqual(partial.status_code, status.HTTP_201_CREATED)

        vehicle = self.make_vehicle("import-price")
        order.refresh_from_db()
        order.vehicle = vehicle
        order.status = ImportOrder.Status.READY_FOR_COLLECTION
        order.save(update_fields=["vehicle", "status"])

        sale_payload = {
            "sale_type": "import",
            "import_reference": order.reference,
            "agreed_price_lkr": "1100.00",
            "sale_date": "2026-11-28",
        }
        mismatch = self.client.post("/api/manager/sales/", sale_payload, format="json")
        self.assertEqual(mismatch.status_code, status.HTTP_400_BAD_REQUEST)

        sale_payload["agreed_price_lkr"] = "1000.00"
        linked = self.client.post("/api/manager/sales/", sale_payload, format="json")
        self.assertEqual(linked.status_code, status.HTTP_201_CREATED, linked.data)

        locked = self.client.patch(url, {
            **payload, "agreed_price_lkr": "1200.00"
        }, format="json")
        self.assertEqual(locked.status_code, status.HTTP_409_CONFLICT)

        final = self.record_payment(self.ceo, {
            "import_reference": order.reference,
            "amount_lkr": "500.00",
            "method": "cash",
        })
        self.assertEqual(final.status_code, status.HTTP_201_CREATED)

        import_summary = self.client.get(url)
        sale_summary = self.client.get(
            f"/api/manager/sales/{linked.data['reference']}/payments/summary/"
        )
        self.assertEqual(import_summary.data["linked_sale_reference"], linked.data["reference"])
        self.assertEqual(Decimal(import_summary.data["verified_amount_lkr"]), Decimal("1000.00"))
        self.assertEqual(Decimal(import_summary.data["outstanding_balance_lkr"]), Decimal("0.00"))
        self.assertEqual(Decimal(sale_summary.data["outstanding_balance_lkr"]), Decimal("0.00"))
        self.assertEqual(Decimal(sale_summary.data["verified_received_lkr"]), Decimal("1000.00"))

    def test_payment_creation_is_confirmed_immediately_and_reduces_balance(self):
        response = self.record_payment()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], Payment.Status.VERIFIED)
        self.assertFalse(response.data["evidence_attached"])
        summary = self.client.get(f"/api/manager/sales/{self.sale.reference}/payments/summary/")
        self.assertEqual(Decimal(summary.data["verified_received_lkr"]), Decimal("250.00"))
        self.assertEqual(Decimal(summary.data["outstanding_balance_lkr"]), Decimal("750.00"))
        self.assertEqual(response.data["verified_by_name"], self.manager.username)
        summary = self.client.get(f"/api/manager/sales/{self.sale.reference}/payments/summary/")
        self.assertEqual(Decimal(summary.data["verified_received_lkr"]), Decimal("250.00"))
        self.assertEqual(Decimal(summary.data["outstanding_balance_lkr"]), Decimal("750.00"))
        self.assertTrue(AuditEvent.objects.filter(action="payment.recorded", subject=response.data["reference"]).exists())
        self.assertEqual(self.client.post(f"/api/staff/payments/{response.data['reference']}/verify/", {}, format="json").status_code, status.HTTP_409_CONFLICT)

    def test_dashboard_summary_reports_immediately_confirmed_records(self):
        pending = self.record_payment(payload=self.sale_payload(transaction_reference="BANK-SUMMARY-009"))
        verified_pending = self.record_payment(payload=self.sale_payload(amount_lkr="50.00", transaction_reference="BANK-SUMMARY-010"))
        self.client.force_authenticate(self.ceo)
        summary = self.client.get("/api/staff/payments/summary/")
        self.assertEqual(summary.status_code, status.HTTP_200_OK)
        self.assertEqual(summary.data["verified_count"], 2)
        self.assertEqual(Decimal(summary.data["verified_amount_lkr"]), Decimal("300.00"))

    def test_legacy_pending_payment_can_be_resolved_by_management(self):
        pending = Payment.objects.create(sale=self.sale, amount_lkr=Decimal("10.00"), method=Payment.Method.CASH,
            recorded_by=self.manager, status=Payment.Status.PENDING)
        self.client.force_authenticate(self.ceo)
        verified = self.client.post(f"/api/staff/payments/{pending.reference}/verify/", {}, format="json")
        self.assertEqual(verified.status_code, status.HTTP_200_OK)
        self.assertEqual(verified.data["status"], Payment.Status.VERIFIED)
        legacy = Payment.objects.create(sale=self.sale, amount_lkr=Decimal("10.00"), method=Payment.Method.CASH,
            recorded_by=self.manager, status=Payment.Status.PENDING)
        missing_reason = self.client.post(f"/api/staff/payments/{legacy.reference}/reject/", {"rejection_reason": "  "}, format="json")
        self.assertEqual(missing_reason.status_code, status.HTTP_400_BAD_REQUEST)
        rejected = self.client.post(f"/api/staff/payments/{legacy.reference}/reject/", {"rejection_reason": "Reference does not match the bank advice."}, format="json")
        self.assertEqual(rejected.status_code, status.HTTP_200_OK)
        self.assertEqual(rejected.data["status"], Payment.Status.REJECTED)
        self.assertTrue(AuditEvent.objects.filter(action="payment.rejected", subject=legacy.reference).exists())

    def test_role_permissions_restrict_financial_transaction_management(self):
        payload = self.sale_payload(transaction_reference="BANK-ROLE-003")
        ceo_payment = self.record_payment(self.ceo, payload)
        self.assertEqual(ceo_payment.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ceo_payment.data["status"], Payment.Status.VERIFIED)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get("/api/staff/payments/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post("/api/staff/payments/", self.sale_payload(transaction_reference="BANK-ROLE-004"), format="json").status_code, status.HTTP_403_FORBIDDEN)
        payment = Payment.objects.get(transaction_reference="BANK-ROLE-003")
        self.assertEqual(self.client.post(f"/api/staff/payments/{payment.reference}/verify/", {}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get(f"/api/staff/payments/{payment.reference}/").status_code, status.HTTP_403_FORBIDDEN)
        for denied in (self.admin, self.rep, None):
            self.client.force_authenticate(denied)
            self.assertEqual(self.client.get("/api/staff/payments/").status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(self.client.get(f"/api/staff/payments/{payment.reference}/").status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_transaction_reference_is_rejected(self):
        first = self.record_payment(payload=self.sale_payload(transaction_reference="BANK-DUPLICATE-005"))
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        second = self.record_payment(payload=self.sale_payload(amount_lkr="10.00", transaction_reference="BANK-DUPLICATE-005"))
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Payment.objects.filter(transaction_reference="BANK-DUPLICATE-005").count(), 1)

    def test_cleared_funds_and_idempotency_are_required_for_non_cash_duplicate_safety(self):
        uncleared = self.record_payment(payload=self.sale_payload(transaction_reference="BANK-UNCLEARED-005", funds_cleared=False))
        self.assertEqual(uncleared.status_code, status.HTTP_400_BAD_REQUEST)
        payload = self.sale_payload(transaction_reference="BANK-IDEMPOTENT-005", idempotency_key="payment-form-attempt-0005")
        first = self.record_payment(payload=payload)
        duplicate = self.record_payment(payload=payload)
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(duplicate.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Payment.objects.filter(idempotency_key="payment-form-attempt-0005").count(), 1)

    def test_reservation_payments_carry_forward_once_without_verifying_declared_advance(self):
        vehicle = self.make_vehicle("2")
        vehicle.status = Vehicle.Status.RESERVED
        vehicle.save(update_fields=["status"])
        reservation = Reservation.objects.create(customer=self.customer, vehicle=vehicle, responsible_staff=self.staff,
            agreed_price_lkr=Decimal("900.00"), advance_amount_lkr=Decimal("500.00"))
        actual = self.record_payment(self.manager, {"reservation_reference": reservation.reference, "amount_lkr": "250.00",
            "method": "cash", "payment_date": "2026-11-21"})
        self.assertEqual(actual.status_code, status.HTTP_201_CREATED)
        before = self.client.get(f"/api/staff/reservations/{reservation.reference}/payments/summary/")
        self.assertEqual(Decimal(before.data["advance_declared_unverified_lkr"]), Decimal("500.00"))
        self.assertEqual(Decimal(before.data["verified_received_lkr"]), Decimal("250.00"))

        self.client.force_authenticate(self.manager)
        sale_response = self.client.post("/api/manager/sales/", {"customer_id": self.customer.pk,
            "vehicle_reference": vehicle.reference, "reservation_reference": reservation.reference,
            "agreed_price_lkr": "800.00", "sale_date": "2026-11-21", "sale_type": "direct"}, format="json")
        self.assertEqual(sale_response.status_code, status.HTTP_201_CREATED)
        confirmed = self.client.post(f"/api/manager/sales/{sale_response.data['reference']}/confirm/", {}, format="json")
        self.assertEqual(confirmed.status_code, status.HTTP_200_OK)
        sale_summary = self.client.get(f"/api/manager/sales/{sale_response.data['reference']}/payments/summary/")
        self.assertEqual(Decimal(sale_summary.data["verified_received_lkr"]), Decimal("250.00"))
        self.assertEqual(Decimal(sale_summary.data["outstanding_balance_lkr"]), Decimal("550.00"))
        reservation_summary = self.client.get(f"/api/staff/reservations/{reservation.reference}/payments/summary/")
        self.assertEqual(Decimal(reservation_summary.data["advance_declared_unverified_lkr"]), Decimal("500.00"))
        self.assertEqual(Decimal(reservation_summary.data["verified_received_lkr"]), Decimal("250.00"))
        self.assertEqual(Payment.objects.filter(reservation=reservation).count(), 1)
        self.assertEqual(Payment.objects.filter(sale__reference=sale_response.data["reference"]).count(), 0)

    def test_verified_overpayment_is_rejected_and_verified_records_are_immutable(self):
        first = self.record_payment(payload=self.sale_payload(amount_lkr="700.00", transaction_reference="BANK-OVER-006"))
        second = self.record_payment(payload=self.sale_payload(amount_lkr="400.00", transaction_reference="BANK-OVER-007"))
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.client.force_authenticate(self.ceo)
        self.assertEqual(self.client.post(f"/api/staff/payments/{first.data['reference']}/verify/", {}, format="json").status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(self.client.patch(f"/api/staff/payments/{first.data['reference']}/", {"amount_lkr": "1.00"}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(f"/api/staff/payments/{first.data['reference']}/").status_code, status.HTTP_403_FORBIDDEN)

    def test_payment_evidence_is_stored_privately_and_authorized_download_is_required(self):
        self.client.force_authenticate(self.manager)
        proof = SimpleUploadedFile("proof.pdf", b"%PDF-1.4\nprivate evidence\n%%EOF", content_type="application/pdf")
        response = self.client.post("/api/staff/payments/", {**self.sale_payload(transaction_reference="BANK-EVIDENCE-008",
            idempotency_key="payment-evidence-test-008"), "evidence": proof}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payment = Payment.objects.get(reference=response.data["reference"])
        self.assertTrue(payment.evidence.name)
        self.assertNotEqual(str(payment.evidence.storage.location), str(settings.MEDIA_ROOT))
        self.client.force_authenticate(self.ceo)
        download = self.client.get(response.data["evidence_url"])
        self.assertEqual(download.status_code, status.HTTP_200_OK)
        self.assertEqual(download["Cache-Control"], "private, no-store")
        self.assertEqual(b"".join(download.streaming_content), b"%PDF-1.4\nprivate evidence\n%%EOF")
        payment.evidence.storage.delete(payment.evidence.name)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(response.data["evidence_url"]).status_code, status.HTTP_403_FORBIDDEN)


class ConcurrentPaymentVerificationTests(TransactionTestCase):
    reset_sequences = True

    @skipUnless(connections["default"].features.has_select_for_update, "Requires database row-lock support")
    def test_only_one_concurrent_verification_can_exceed_the_remaining_balance(self):
        recorder = User.objects.create_user(username="concurrent-recorder", password="Payment-Test-345!", role=User.Role.STAFF)
        reviewer = User.objects.create_user(username="concurrent-reviewer", password="Payment-Test-345!", role=User.Role.CEO)
        customer = Customer.objects.create(full_name="Concurrent Payment Customer")
        vehicle = Vehicle.objects.create(make="Toyota", model="Concurrent Test", manufacture_year=2023, mileage_km=10000,
            fuel_type=Vehicle.FuelType.PETROL, transmission=Vehicle.Transmission.AUTOMATIC, color="Silver",
            condition=Vehicle.Condition.USED, internal_identifier="CONCURRENT-PAYMENT-CHASSIS", asking_price_lkr=1000000)
        sale = Sale.objects.create(vehicle=vehicle, customer=customer, agreed_price_lkr=Decimal("100.00"), created_by=reviewer)
        payments = [Payment.objects.create(sale=sale, amount_lkr=Decimal("60.00"), method=Payment.Method.CASH, recorded_by=recorder) for _ in range(2)]
        barrier = Barrier(2)

        def verify(reference):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(reviewer)
                barrier.wait(timeout=10)
                response = client.post(f"/api/staff/payments/{reference}/verify/", {}, format="json")
                return response.status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(verify, payment.reference) for payment in payments]
            results = [future.result(timeout=20) for future in futures]
        self.assertCountEqual(results, [status.HTTP_200_OK, status.HTTP_409_CONFLICT])
        self.assertEqual(Payment.objects.filter(sale=sale, status=Payment.Status.VERIFIED).count(), 1)
