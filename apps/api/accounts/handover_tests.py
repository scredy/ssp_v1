from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless

from django.conf import settings
from django.db import close_old_connections, connections
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from .models import AuditEvent, CommissionLedgerEntry, Customer, Handover, HandoverApproval, HandoverDocumentReceipt, Notification, Payment, Reservation, Sale, User, Vehicle


class HandoverApiTests(APITestCase):
    def user(self, username, role):
        return User.objects.create_user(username=username, password="Handover-Test-345!", role=role,
                                        email=f"{username}@example.test")

    def setUp(self):
        self.staff = self.user("handover-staff", User.Role.STAFF)
        self.manager = self.user("handover-manager", User.Role.MANAGER)
        self.ceo = self.user("handover-ceo", User.Role.CEO)
        self.admin = self.user("handover-admin", User.Role.ADMIN)
        self.rep = self.user("handover-rep", User.Role.REP)
        self.customer = Customer.objects.create(full_name="Handover Customer", email="handover@example.test")
        self.vehicle = self.make_vehicle("A")
        self.sale = self.make_confirmed_sale(self.vehicle)

    def make_vehicle(self, suffix):
        return Vehicle.objects.create(make="Toyota", model="Handover Test", manufacture_year=2024, mileage_km=10000,
            fuel_type=Vehicle.FuelType.HYBRID, transmission=Vehicle.Transmission.AUTOMATIC, color="Silver",
            condition=Vehicle.Condition.USED, internal_identifier=f"HANDOVER-CHASSIS-{suffix}", asking_price_lkr="1000000")

    def make_confirmed_sale(self, vehicle, status_value=Sale.Status.CONFIRMED):
        vehicle.status = Vehicle.Status.SOLD
        vehicle.save(update_fields=["status", "updated_at"])
        return Sale.objects.create(vehicle=vehicle, customer=self.customer, agreed_price_lkr=Decimal("900000.00"),
            sale_date="2026-11-21", status=status_value, confirmed_at="2026-11-21T09:00:00Z", created_by=self.manager)

    def checklist_payload(self):
        return {"vehicle_condition_checklist": {key: True for key in ("bodywork", "interior", "tyres", "lights", "odometer")},
                "keys_documents_checklist": {key: True for key in ("keys", "registration_documents", "insurance_documents", "service_documents")},
                "customer_acknowledgement": "Customer acknowledged receipt and the recorded vehicle condition.",
                "delivery_date": "2026-11-21"}

    def create_handover(self, sale=None, user=None, extra=None):
        self.client.force_authenticate(user or self.staff)
        return self.client.post("/api/staff/handovers/", {"sale_reference": (sale or self.sale).reference, **(extra or {})}, format="json")

    def ready_handover(self, sale=None):
        created = self.create_handover(sale=sale)
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.client.force_authenticate(self.staff)
        detail = f"/api/staff/handovers/{created.data['reference']}/"
        patched = self.client.patch(detail, self.checklist_payload(), format="json")
        self.assertEqual(patched.status_code, status.HTTP_200_OK)
        submitted = self.client.post(f"{detail}submit/", {}, format="json")
        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        return submitted.data

    def md_approved_handover(self, sale=None):
        handover = self.ready_handover(sale)
        self.client.force_authenticate(self.manager)
        response = self.client.post(f"/api/staff/handovers/{handover['reference']}/approve-md/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def ceo_approved_handover(self, sale=None):
        handover = self.md_approved_handover(sale)
        self.client.force_authenticate(self.ceo)
        response = self.client.post(f"/api/staff/handovers/{handover['reference']}/approve-ceo/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_completion_email_sent_once(self):
        from django.core import mail
        from django.test import override_settings
        from .models import HandoverCompletionEmail
        from .handover_email import send_handover_email

        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
        ):
            handover = self.ceo_approved_handover()
            detail = f"/api/staff/handovers/{handover['reference']}/"

            self.assertFalse(HandoverCompletionEmail.objects.exists())

            self.client.force_authenticate(self.manager)

            with self.captureOnCommitCallbacks(execute=True):
                result = self.client.post(
                    f"{detail}finalize/", {}, format="json"
                )
                self.assertEqual(result.status_code, 200)

            record = HandoverCompletionEmail.objects.get(
                handover_id=handover["id"]
            )

            self.assertEqual(record.status, "sent", record.error)
            self.assertIsNotNone(record.sent_at)
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].to, [self.customer.email])
            self.assertIn("Vehicle Handover Completed", mail.outbox[0].subject)
            self.assertIn(handover["reference"], mail.outbox[0].body)
            self.assertTrue(mail.outbox[0].alternatives)

            send_handover_email(record.pk, self.manager.pk)

            self.assertEqual(len(mail.outbox), 1)

            retry = self.client.post(
                f"{detail}retry-email/", {}, format="json"
            )
            self.assertEqual(retry.status_code, 409)

            self.assertEqual(
                self.client.get(detail).data["completion_email"]["status"],
                "sent"
            )

            self.assertTrue(AuditEvent.objects.filter(
                action="handover.completion_email",
                subject=handover["reference"],
            ).exists())

    def test_completion_email_failure_does_not_reverse_handover(self):
        from unittest.mock import patch
        from .models import HandoverCompletionEmail

        handover = self.ceo_approved_handover()
        detail = f"/api/staff/handovers/{handover['reference']}/"

        self.client.force_authenticate(self.manager)

        with patch(
            "accounts.handover_email.send_customer_email",
            side_effect=RuntimeError("Simulated mail failure")
        ):
            with self.captureOnCommitCallbacks(execute=True):
                result = self.client.post(
                    f"{detail}finalize/", {}, format="json"
                )
                self.assertEqual(result.status_code, 200)

        record = HandoverCompletionEmail.objects.get(
            handover_id=handover["id"]
        )

        self.assertEqual(record.status, "failed")
        self.assertEqual(record.handover.status, Handover.Status.FINALIZED)

        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, Vehicle.Status.HANDED_OVER)

        unconfirmed = self.client.post(
            f"{detail}retry-email/", {}, format="json"
        )
        self.assertEqual(unconfirmed.status_code, 400)

        for user in (self.staff, self.rep, self.admin):
            self.client.force_authenticate(user)
            denied = self.client.post(
                f"{detail}retry-email/",
                {"confirmed_not_accepted": True},
                format="json"
            )
            self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(self.ceo)

        with patch(
            "accounts.handover_email.send_customer_email",
            return_value=1
        ) as send:
            with self.captureOnCommitCallbacks(execute=True):
                retry = self.client.post(
                    f"{detail}retry-email/",
                    {"confirmed_not_accepted": True},
                    format="json"
                )
                self.assertEqual(retry.status_code, 200)

            send.assert_called_once()

        record.refresh_from_db()
        self.assertEqual(record.status, "sent")

        self.assertEqual(HandoverCompletionEmail.objects.filter(
            handover_id=handover["id"]
        ).count(), 1)

    def test_completion_email_missing_address(self):
        from unittest.mock import patch
        from .models import HandoverCompletionEmail

        self.customer.email = ""
        self.customer.save(update_fields=["email"])

        handover = self.ceo_approved_handover()
        detail = f"/api/staff/handovers/{handover['reference']}/"

        self.client.force_authenticate(self.manager)

        with patch(
            "accounts.handover_email.send_customer_email"
        ) as send:
            with self.captureOnCommitCallbacks(execute=True):
                result = self.client.post(
                    f"{detail}finalize/", {}, format="json"
                )
                self.assertEqual(result.status_code, 200)

            send.assert_not_called()

        record = HandoverCompletionEmail.objects.get(
            handover_id=handover["id"]
        )

        self.assertEqual(record.status, "no_email")

        retry = self.client.post(
            f"{detail}retry-email/", {}, format="json"
        )
        self.assertEqual(retry.status_code, 400)

        self.customer.email = "corrected@example.test"
        self.customer.save(update_fields=["email"])

        with patch(
            "accounts.handover_email.send_customer_email",
            return_value=1
        ) as send:
            with self.captureOnCommitCallbacks(execute=True):
                retry = self.client.post(
                    f"{detail}retry-email/", {}, format="json"
                )
                self.assertEqual(retry.status_code, 200)

            send.assert_called_once()

        record.refresh_from_db()
        self.assertEqual(record.status, "sent")
        self.assertEqual(record.recipient, "corrected@example.test")


    def test_verified_reservation_down_payment_release_document_receipt_and_later_finance_settlement(self):
        vehicle = self.make_vehicle("FINANCE")
        vehicle.status = Vehicle.Status.RESERVED
        vehicle.save(update_fields=["status", "updated_at"])
        reservation = Reservation.objects.create(customer=self.customer, vehicle=vehicle, responsible_staff=self.staff,
            agreed_price_lkr=Decimal("900000.00"), advance_amount_lkr=Decimal("200000.00"))
        initial = Payment.objects.create(reservation=reservation, amount_lkr=Decimal("150000.00"),
            method=Payment.Method.BANK_TRANSFER, transaction_reference="FINANCE-ADVANCE-VERIFIED-A",
            recorded_by=self.staff, status=Payment.Status.VERIFIED, verified_by=self.manager, verified_at=timezone.now())
        advance_remainder = Payment.objects.create(reservation=reservation, amount_lkr=Decimal("50000.00"),
            method=Payment.Method.BANK_TRANSFER, transaction_reference="FINANCE-ADVANCE-PENDING-A",
            recorded_by=self.staff, status=Payment.Status.PENDING)
        sale = Sale.objects.create(vehicle=vehicle, customer=self.customer, reservation=reservation,
            agreed_price_lkr=Decimal("900000.00"), sale_date="2026-11-21", status=Sale.Status.CONFIRMED,
            confirmed_at=timezone.now(), created_by=self.manager)
        reservation.status = Reservation.Status.CONVERTED
        reservation.save(update_fields=["status", "updated_at"])
        vehicle.status = Vehicle.Status.SOLD
        vehicle.save(update_fields=["status", "updated_at"])

        handover = self.ready_handover(sale)
        detail = f"/api/staff/handovers/{handover['reference']}/"
        self.client.force_authenticate(self.staff)
        premature_receipt = self.client.post(f"/api/staff/handovers/{handover['reference']}/document-receipt/", {}, format="json")
        self.assertEqual(premature_receipt.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(self.client.post(f"{detail}finalize/", {}, format="json").status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.manager)
        blocked = self.client.post(f"{detail}finalize/", {}, format="json")
        self.assertEqual(blocked.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("CEO-approved", blocked.data["detail"])
        self.assertEqual(self.client.post(f"{detail}approve-md/", {}, format="json").status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.ceo)
        blocked = self.client.post(f"{detail}approve-ceo/", {}, format="json")
        self.assertEqual(blocked.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("down payment", blocked.data["payment"].lower())
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.post(f"/api/staff/payments/{advance_remainder.reference}/verify/", {}, format="json").status_code,
                         status.HTTP_200_OK)
        self.client.force_authenticate(self.ceo)
        self.assertEqual(self.client.post(f"{detail}approve-ceo/", {}, format="json").status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.manager)
        finalized = self.client.post(f"{detail}finalize/", {}, format="json")
        self.assertEqual(finalized.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(finalized.data["financial_summary"]["verified_received_lkr"]), Decimal("200000.00"))
        self.assertEqual(Decimal(finalized.data["financial_summary"]["outstanding_balance_lkr"]), Decimal("700000.00"))
        self.assertTrue(finalized.data["financial_summary"]["down_payment_satisfied"])
        self.assertEqual(finalized.data["status"], Handover.Status.FINALIZED)
        self.assertTrue(finalized.data["commission_eligible"])

        self.client.force_authenticate(self.staff)
        issued = self.client.post(f"/api/staff/handovers/{handover['reference']}/document-receipt/", {}, format="json")
        self.assertEqual(issued.status_code, status.HTTP_201_CREATED)
        self.assertEqual(issued.data["sale_reference"], sale.reference)
        self.assertEqual(issued.data["vehicle_reference"], vehicle.reference)
        self.assertEqual(issued.data["customer_name"], self.customer.full_name)
        self.assertEqual({item["key"] for item in issued.data["items_handed_over"]},
                         {"keys", "registration_documents", "insurance_documents", "service_documents"})
        self.assertEqual(HandoverDocumentReceipt.objects.filter(handover_id=handover["id"]).count(), 1)
        duplicate = self.client.post(f"/api/staff/handovers/{handover['reference']}/document-receipt/", {}, format="json")
        self.assertEqual(duplicate.status_code, status.HTTP_200_OK)
        self.assertEqual(duplicate.data["reference"], issued.data["reference"])
        pdf = self.client.get(f"/api/staff/handovers/{handover['reference']}/document-receipt/{issued.data['reference']}/pdf/")
        self.assertEqual(pdf.status_code, status.HTTP_200_OK)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertEqual(pdf["Cache-Control"], "private, no-store")
        pdf_bytes = pdf.content
        pdf_text = lambda value: value.encode("utf-16-be").hex().upper().encode("ascii")
        self.assertIn(pdf_text("VEHICLE & DOCUMENT"), pdf_bytes)
        self.assertIn(pdf_text("HANDOVER ACKNOWLEDGMENT"), pdf_bytes)
        self.assertRegex(pdf_bytes, rb"/XObject << /Logo \d+ 0 R >>")
        self.assertIn(pdf_text("COMPANY AND VEHICLE ITEMS HANDED OVER"), pdf_bytes)
        self.assertIn(pdf_text("CUSTOMER ACKNOWLEDGMENT"), pdf_bytes)
        self.assertIn(pdf_text("Customer name"), pdf_bytes)
        self.assertIn(pdf_text("Issued by"), pdf_bytes)
        self.assertIn(pdf_text("not a payment receipt"), pdf_bytes)
        self.assertEqual(self.client.get(detail).data["financial_summary"]["outstanding_balance_lkr"], Decimal("700000.00"))

        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(f"/api/staff/handovers/{handover['reference']}/document-receipt/", {}, format="json").status_code,
                         status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get(f"/api/staff/handovers/{handover['reference']}/document-receipt/{issued.data['reference']}/pdf/").status_code,
                         status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.manager)
        finance = self.client.post("/api/staff/payments/", {"sale_reference": sale.reference,
            "amount_lkr": "700000.00", "method": "bank_transfer", "transaction_reference": "FINANCE-COMPANY-SETTLEMENT-A",
            "funds_cleared": True, "idempotency_key": "finance-company-settlement-handover-test",
            "payment_date": "2026-11-21"}, format="json")
        self.assertEqual(finance.status_code, status.HTTP_201_CREATED)
        self.assertEqual(finance.data["status"], Payment.Status.VERIFIED)
        self.assertEqual(self.client.get(detail).data["financial_summary"]["outstanding_balance_lkr"], Decimal("0.00"))
        self.assertEqual(self.client.post(f"/api/staff/payments/{finance.data['reference']}/verify/", {}, format="json").status_code,
                         status.HTTP_409_CONFLICT)
        final_summary = self.client.get(detail).data["financial_summary"]
        self.assertEqual(final_summary["verified_received_lkr"], Decimal("900000.00"))
        self.assertEqual(final_summary["outstanding_balance_lkr"], Decimal("0.00"))
        self.assertEqual(Payment.objects.filter(reservation=reservation, status=Payment.Status.VERIFIED).count(), 2)
        self.assertEqual(Payment.objects.filter(sale=sale, status=Payment.Status.VERIFIED).count(), 1)
        self.assertEqual(CommissionLedgerEntry.objects.filter(sale=sale).count(), 1)

    def test_confirmed_sale_preparation_checklist_review_and_atomic_finalization(self):
        vehicle = self.make_vehicle("DRAFT")
        draft = Sale.objects.create(vehicle=vehicle, customer=self.customer, agreed_price_lkr=Decimal("500000"), created_by=self.manager)
        self.assertEqual(self.create_handover(draft).status_code, status.HTTP_409_CONFLICT)

        prepared = self.create_handover()
        self.assertEqual(prepared.status_code, status.HTTP_201_CREATED)
        reference = prepared.data["reference"]
        detail = f"/api/staff/handovers/{reference}/"
        self.assertEqual(prepared.data["status"], Handover.Status.PREPARING)
        self.assertEqual(self.create_handover().status_code, status.HTTP_409_CONFLICT)

        self.client.force_authenticate(self.staff)
        incomplete = self.client.post(f"{detail}submit/", {}, format="json")
        self.assertEqual(incomplete.status_code, status.HTTP_400_BAD_REQUEST)
        invalid = self.client.patch(detail, {**self.checklist_payload(),
            "vehicle_condition_checklist": {"bodywork": "yes"}}, format="json")
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.patch(detail, self.checklist_payload(), format="json").status_code, status.HTTP_200_OK)
        submitted = self.client.post(f"{detail}submit/", {}, format="json")
        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        self.assertEqual(submitted.data["status"], Handover.Status.PENDING_MD_REVIEW)

        Payment.objects.create(sale=self.sale, amount_lkr=Decimal("200000"), method=Payment.Method.CASH, recorded_by=self.staff,
            status=Payment.Status.VERIFIED, verified_by=self.manager)
        self.client.force_authenticate(self.ceo)
        self.assertEqual(self.client.get(detail).data["financial_summary"]["balance_review_required"], True)
        self.assertEqual(self.client.get(detail).data["commission_eligible"], False)

        self.client.force_authenticate(self.manager)
        finalized = self.client.post(f"{detail}finalize/", {}, format="json")
        self.assertEqual(finalized.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(self.client.post(f"{detail}approve-md/", {}, format="json").status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.ceo)
        self.assertEqual(self.client.post(f"{detail}approve-ceo/", {}, format="json").status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.manager)
        finalized = self.client.post(f"{detail}finalize/", {}, format="json")
        self.assertEqual(finalized.status_code, status.HTTP_200_OK)
        self.assertEqual(finalized.data["status"], Handover.Status.FINALIZED)
        self.assertTrue(finalized.data["commission_eligible"])
        self.assertEqual(Decimal(finalized.data["financial_summary"]["outstanding_balance_lkr"]), Decimal("700000.00"))
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, Vehicle.Status.HANDED_OVER)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.Status.CONFIRMED)
        self.assertEqual(self.client.post(f"{detail}finalize/", {}, format="json").status_code, status.HTTP_409_CONFLICT)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.patch(detail, {"internal_notes": "changed"}, format="json").status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(AuditEvent.objects.filter(action="handover.prepared", subject=reference).exists())
        self.assertTrue(AuditEvent.objects.filter(action="handover.submitted_for_review", subject=reference).exists())
        self.assertTrue(AuditEvent.objects.filter(action="handover.finalized", subject=reference).exists())

    def test_ceo_cannot_finalize_and_manager_finalizes_after_ceo_approval(self):
        handover = self.ceo_approved_handover()
        self.client.force_authenticate(self.ceo)
        response = self.client.post(f"/api/staff/handovers/{handover['reference']}/finalize/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.manager)
        response = self.client.post(f"/api/staff/handovers/{handover['reference']}/finalize/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["finalized_by_name"], self.manager.username)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, Vehicle.Status.HANDED_OVER)


    def test_role_permissions_and_private_supporting_evidence(self):
        for denied_user in (self.admin, self.rep):
            self.client.force_authenticate(denied_user)
            self.assertEqual(self.client.get("/api/staff/handovers/").status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(self.client.post("/api/staff/handovers/", {"sale_reference": self.sale.reference}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.ceo)
        self.assertEqual(self.client.post("/api/staff/handovers/", {"sale_reference": self.sale.reference}, format="json").status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.manager)
        preparation = SimpleUploadedFile("receipt.pdf", b"%PDF-1.4\nprivate handover evidence\n%%EOF", content_type="application/pdf")
        denied = self.client.post("/api/staff/handovers/", {"sale_reference": self.sale.reference, "supporting_evidence": preparation}, format="multipart")
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.staff)
        preparation = SimpleUploadedFile("receipt.pdf", b"%PDF-1.4\nprivate handover evidence\n%%EOF", content_type="application/pdf")
        response = self.client.post("/api/staff/handovers/", {"sale_reference": self.sale.reference, "supporting_evidence": preparation}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        handover = Handover.objects.get(reference=response.data["reference"])
        self.assertTrue(handover.supporting_evidence.name)
        self.assertNotEqual(str(handover.supporting_evidence.storage.location), str(settings.MEDIA_ROOT))
        self.client.force_authenticate(self.ceo)
        evidence = self.client.get(response.data["evidence_url"])
        self.assertEqual(evidence.status_code, status.HTTP_200_OK)
        self.assertEqual(evidence["Cache-Control"], "private, no-store")
        self.assertEqual(b"".join(evidence.streaming_content), b"%PDF-1.4\nprivate handover evidence\n%%EOF")
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(response.data["evidence_url"]).status_code, status.HTTP_403_FORBIDDEN)
        handover.supporting_evidence.storage.delete(handover.supporting_evidence.name)

    def test_md_return_preserves_decision_history_then_staff_can_edit_and_resubmit(self):
        ready = self.ready_handover()
        url = f"/api/staff/handovers/{ready['reference']}/"
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.patch(url, {"internal_notes": "Must not retain approval."}, format="json").status_code, status.HTTP_409_CONFLICT)
        self.client.force_authenticate(self.manager)
        returned = self.client.post(f"/api/staff/handovers/{ready['reference']}/return/", {"comments": "Please attach the final condition checklist."}, format="json")
        self.assertEqual(returned.status_code, status.HTTP_200_OK)
        self.assertEqual(returned.data["status"], Handover.Status.PREPARING)
        self.assertEqual(returned.data["approval_history"][-1]["comments"], "Please attach the final condition checklist.")
        self.client.force_authenticate(self.staff)
        updated = self.client.patch(url, {"internal_notes": "Recheck odometer reading."}, format="json")
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(updated.data["status"], Handover.Status.PREPARING)


    def test_eligible_sale_selector_is_private_searchable_and_excludes_existing_handovers(self):
        self.client.force_authenticate(self.staff)
        response = self.client.get("/api/staff/handovers/eligible-sales/?search=Handover")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["reference"], self.sale.reference)
        self.assertNotIn("email", response.data[0])
        self.assertNotIn("phone", response.data[0])
        self.assertEqual(self.create_handover().status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.client.get("/api/staff/handovers/eligible-sales/").data, [])
        self.client.force_authenticate(self.ceo)
        self.assertEqual(self.client.get("/api/staff/handovers/eligible-sales/").status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_cannot_prepare_or_submit_handover(self):
        prepared = self.create_handover(user=self.manager)
        self.assertEqual(prepared.status_code, status.HTTP_403_FORBIDDEN)

    def test_commission_policy_ceo_only_and_pending_entry_created_at_finalized_handover(self):
        brackets = [{"minimum_lkr": "0.00", "maximum_lkr": "1000000.00", "percentage": "2.5",
                     "effective_date": "2026-01-01", "active": True}]
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.get("/api/commission-rules/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.put("/api/commission-rules/brackets/", brackets, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.ceo)
        self.assertEqual(self.client.put("/api/commission-rules/brackets/", brackets, format="json").status_code, status.HTTP_200_OK)
        history = self.client.get("/api/commission-rules/?history=1")
        self.assertEqual(history.status_code, status.HTTP_200_OK)
        self.assertEqual(history.data[0]["current"][0]["minimum_lkr"], "0.00")
        self.assertEqual(history.data[0]["current"][0]["percentage"], "2.500")
        self.assertIsNone(history.data[0]["previous"])
        self.client.force_authenticate(self.manager)
        manager_history = self.client.get("/api/commission-rules/?history=1")
        self.assertEqual(manager_history.status_code, status.HTTP_200_OK)
        self.assertEqual(manager_history.data[0]["actor"], self.ceo.username)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get("/api/commission-rules/?history=1").status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.ceo)
        overlap = brackets + [{"minimum_lkr": "999999.00", "maximum_lkr": None, "percentage": "3.0",
                               "effective_date": "2026-01-01", "active": True}]
        self.assertEqual(self.client.put("/api/commission-rules/brackets/", overlap, format="json").status_code, status.HTTP_400_BAD_REQUEST)
        handover = self.ceo_approved_handover()
        self.assertEqual(CommissionLedgerEntry.objects.count(), 0)
        self.client.force_authenticate(self.manager)
        result = self.client.post(f"/api/staff/handovers/{handover['reference']}/finalize/", {}, format="json")
        self.assertEqual(result.status_code, status.HTTP_200_OK)
        entry = CommissionLedgerEntry.objects.get(sale=self.sale)
        self.assertEqual(entry.status, "pending")
        self.assertIsNone(entry.recipient_id)
        self.assertEqual(entry.commission_rate_percent, Decimal("2.500"))
        self.assertEqual(entry.commission_amount_lkr, Decimal("22500.00"))
        self.assertEqual(entry.policy_snapshot["effective_date"], "2026-01-01")
        self.assertEqual(CommissionLedgerEntry.objects.count(), 1)
        self.assertTrue(AuditEvent.objects.filter(action="commission.pending_created", subject=self.sale.reference).exists())
        self.assertEqual(self.client.get("/api/commissions/").status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get("/api/commissions/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post("/api/commissions/", {}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.rep)
        self.assertEqual(self.client.get("/api/commissions/").status_code, status.HTTP_403_FORBIDDEN)

    def test_mandatory_chain_history_notification_routing_and_repeat_protection(self):
        handover = self.ready_handover()
        reference = handover["reference"]
        detail = f"/api/staff/handovers/{reference}/"
        self.assertEqual(handover["status"], Handover.Status.PENDING_MD_REVIEW)
        self.assertEqual(Notification.objects.filter(recipient=self.manager).count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.ceo).count(), 0)

        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.post(f"{detail}approve-md/", {}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(f"{detail}approve-ceo/", {}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(f"{detail}finalize/", {}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(f"{detail}submit/", {}, format="json").status_code, status.HTTP_409_CONFLICT)

        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.post(f"{detail}approve-ceo/", {}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(f"{detail}finalize/", {}, format="json").status_code, status.HTTP_409_CONFLICT)
        md = self.client.post(f"{detail}approve-md/", {}, format="json")
        self.assertEqual(md.status_code, status.HTTP_200_OK)
        self.assertEqual(md.data["status"], Handover.Status.PENDING_CEO_APPROVAL)
        self.assertEqual(self.client.post(f"{detail}approve-md/", {}, format="json").status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Notification.objects.filter(recipient=self.ceo).count(), 1)

        self.client.force_authenticate(self.ceo)
        self.assertEqual(self.client.post(f"{detail}return/", {}, format="json").status_code, status.HTTP_400_BAD_REQUEST)
        returned = self.client.post(f"{detail}return/", {"comments": "Correct the delivery date evidence."}, format="json")
        self.assertEqual(returned.status_code, status.HTTP_200_OK)
        self.assertEqual(returned.data["status"], Handover.Status.PENDING_MD_REVIEW)
        self.assertIsNone(returned.data["md_approved_by_name"])
        self.assertEqual(returned.data["approval_history"][-1]["status_before"], Handover.Status.PENDING_CEO_APPROVAL)
        self.assertEqual(returned.data["approval_history"][-1]["comments"], "Correct the delivery date evidence.")
        self.assertEqual(Notification.objects.filter(recipient=self.manager).count(), 2)
        self.assertEqual(self.client.post(f"{detail}approve-ceo/", {}, format="json").status_code, status.HTTP_409_CONFLICT)

        self.client.force_authenticate(self.manager)
        second_md = self.client.post(f"{detail}approve-md/", {}, format="json")
        self.assertEqual(second_md.status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.ceo)
        approved = self.client.post(f"{detail}approve-ceo/", {}, format="json")
        self.assertEqual(approved.status_code, status.HTTP_200_OK)
        self.assertFalse(approved.data["commission_eligible"])
        self.assertEqual(CommissionLedgerEntry.objects.filter(sale=self.sale).count(), 0)
        self.assertEqual(Notification.objects.filter(recipient=self.manager).count(), 3)

        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.patch(detail, {"delivery_date": "2026-11-22"}, format="json").status_code, status.HTTP_409_CONFLICT)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.post(f"{detail}finalize/", {}, format="json").status_code, status.HTTP_200_OK)
        duplicate_finalize = self.client.post(f"{detail}finalize/", {}, format="json")
        self.assertEqual(duplicate_finalize.status_code, status.HTTP_409_CONFLICT)
        result = self.client.get(detail).data
        self.assertEqual([entry["decision"] for entry in result["approval_history"]], [
            HandoverApproval.Decision.SUBMITTED_FOR_MD,
            HandoverApproval.Decision.MD_APPROVED,
            HandoverApproval.Decision.CEO_RETURNED,
            HandoverApproval.Decision.MD_APPROVED,
            HandoverApproval.Decision.CEO_APPROVED,
            HandoverApproval.Decision.FINALIZED,
        ])
        self.assertEqual(CommissionLedgerEntry.objects.filter(sale=self.sale).count(), 1)

    def test_md_can_return_ceo_approved_handover_before_material_edits_and_history_survives(self):
        approved = self.ceo_approved_handover()
        detail = f"/api/staff/handovers/{approved['reference']}/"
        self.client.force_authenticate(self.manager)
        returned = self.client.post(f"{detail}return/", {"comments": "Customer acknowledgement must be refreshed."}, format="json")
        self.assertEqual(returned.status_code, status.HTTP_200_OK)
        self.assertEqual(returned.data["status"], Handover.Status.PREPARING)
        self.assertIsNone(returned.data["md_approved_by_name"])
        self.assertIsNone(returned.data["ceo_approved_by_name"])
        self.client.force_authenticate(self.staff)
        edited = self.client.patch(detail, {"customer_acknowledgement": "Updated acknowledgement."}, format="json")
        self.assertEqual(edited.status_code, status.HTTP_200_OK)
        self.assertEqual(edited.data["status"], Handover.Status.PREPARING)
        self.assertEqual(edited.data["approval_history"][-1]["decision"], HandoverApproval.Decision.MD_RETURNED)

    def test_non_approval_roles_are_denied_and_approval_history_is_append_only(self):
        pending = self.ready_handover()
        detail = f"/api/staff/handovers/{pending['reference']}/"
        for user in (self.admin, self.rep):
            self.client.force_authenticate(user)
            for action in ("submit/", "approve-md/", "approve-ceo/", "return/", "finalize/"):
                self.assertEqual(self.client.post(f"{detail}{action}", {"comments": "reason"}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.patch(detail, self.checklist_payload(), format="json").status_code, status.HTTP_403_FORBIDDEN)
        approval = HandoverApproval.objects.get(handover__reference=pending["reference"])
        with self.assertRaises(Exception):
            HandoverApproval.objects.filter(pk=approval.pk).update(comments="rewrite")
        with self.assertRaises(Exception):
            approval.delete()


class ConcurrentHandoverFinalizationTests(TransactionTestCase):
    reset_sequences = True

    @skipUnless(connections["default"].features.has_select_for_update, "Concurrent row-lock verification requires a database with SELECT FOR UPDATE.")
    def test_only_one_concurrent_finalization_succeeds(self):
        staff = User.objects.create_user(username="parallel-handover-staff", password="Handover-Test-345!", role=User.Role.STAFF)
        manager = User.objects.create_user(username="parallel-handover-manager", password="Handover-Test-345!", role=User.Role.MANAGER)
        customer = Customer.objects.create(full_name="Concurrent Handover Customer")
        vehicle = Vehicle.objects.create(make="Toyota", model="Concurrent Handover", manufacture_year=2024, mileage_km=5000,
            fuel_type=Vehicle.FuelType.PETROL, transmission=Vehicle.Transmission.AUTOMATIC, color="White",
            condition=Vehicle.Condition.USED, internal_identifier="CONCURRENT-HANDOVER-CHASSIS", asking_price_lkr=1000000)
        vehicle.status = Vehicle.Status.SOLD
        vehicle.save(update_fields=["status", "updated_at"])
        sale = Sale.objects.create(vehicle=vehicle, customer=customer, agreed_price_lkr=Decimal("900000"), status=Sale.Status.CONFIRMED,
            confirmed_at="2026-11-21T09:00:00Z", created_by=manager)
        checklist_a = {key: True for key in ("bodywork", "interior", "tyres", "lights", "odometer")}
        checklist_b = {key: True for key in ("keys", "registration_documents", "insurance_documents", "service_documents")}
        ceo = User.objects.create_user(username="parallel-handover-ceo", password="Handover-Test-345!", role=User.Role.CEO)
        handover = Handover.objects.create(sale=sale, customer=customer, vehicle=vehicle, prepared_by=staff,
            status=Handover.Status.CEO_APPROVED, delivery_date="2026-11-21", vehicle_condition_checklist=checklist_a,
            keys_documents_checklist=checklist_b, customer_acknowledgement="Acknowledged.", customer_acknowledged_at=timezone.now(),
            md_approved_by=manager, md_approved_at=timezone.now(), ceo_approved_by=ceo, ceo_approved_at=timezone.now())
        barrier = Barrier(2)

        def finalize():
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(manager)
                barrier.wait(timeout=10)
                response = client.post(f"/api/staff/handovers/{handover.reference}/finalize/", {}, format="json")
                return response.status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: finalize(), range(2)))
        self.assertCountEqual(results, [status.HTTP_200_OK, status.HTTP_409_CONFLICT])
        handover.refresh_from_db()
        vehicle.refresh_from_db()
        self.assertEqual(handover.status, Handover.Status.FINALIZED)
        self.assertEqual(vehicle.status, Vehicle.Status.HANDED_OVER)
