from decimal import Decimal

from django.conf import settings
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from .models import AuditEvent, Customer, Quotation, User, Vehicle


class QuotationApiTests(APITestCase):
    def user(self, username, role):
        return User.objects.create_user(username=username, password="Quotation-Test-345!", role=role,
                                        email=f"{username}@example.test")

    def setUp(self):
        self.staff = self.user("quote-staff", User.Role.STAFF)
        self.manager = self.user("quote-manager", User.Role.MANAGER)
        self.ceo = self.user("quote-ceo", User.Role.CEO)
        self.admin = self.user("quote-admin", User.Role.ADMIN)
        self.rep = self.user("quote-rep", User.Role.REP)
        self.customer = Customer.objects.create(full_name="Quotation Customer", email="quote@example.test", phone="0771234567")
        self.vehicle = Vehicle.objects.create(make="Toyota", model="Corolla", manufacture_year=2024,
            mileage_km=10000, fuel_type=Vehicle.FuelType.HYBRID, transmission=Vehicle.Transmission.AUTOMATIC,
            color="Silver", condition=Vehicle.Condition.USED, internal_identifier="QUOTE-PRIVATE-CHASSIS",
            asking_price_lkr=Decimal("10000000.00"))

    def payload(self, **overrides):
        return {"customer": self.customer.pk, "vehicle": self.vehicle.pk,
            "vehicle_description": "2024 Toyota Corolla Hybrid", "vehicle_specifications": {"year": 2024, "fuel": "Hybrid"},
            "vehicle_selling_price_lkr": "1000000.00", "additional_charges_lkr": "25000.00",
            "discount_lkr": "5000.00", "quotation_total_lkr": "1.00", "issue_date": "2026-11-21",
            "expiry_date": "2026-12-21", "customer_terms": "Quotation valid until the stated date.",
            "finance_term": "60m", "finance_down_payment_lkr": "100000.00", **overrides}

    def create_quote(self, user=None, payload=None):
        self.client.force_authenticate(user or self.staff)
        return self.client.post("/api/staff/quotations/", payload or self.payload(), format="json")

    def test_draft_creation_calculates_total_and_rejects_invalid_discount(self):
        created = self.create_quote()
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(created.data["quotation_total_lkr"]), Decimal("1020000.00"))
        self.assertEqual(created.data["status"], Quotation.Status.DRAFT)
        self.assertNotEqual(Decimal(created.data["quotation_total_lkr"]), Decimal("1.00"))
        invalid = self.create_quote(payload=self.payload(discount_lkr="2000000.00"))
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(AuditEvent.objects.filter(action="quotation.created", subject=created.data["reference"]).exists())

    def test_finance_options_are_centralized_and_protected(self):
        self.client.force_authenticate(self.staff)
        response = self.client.get("/api/staff/quotations/finance-options/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual({option["id"]: option["rate_per_100k_lkr"] for option in response.data},
            {term: str(rate.quantize(Decimal("0.01"))) for term, rate in settings.FINANCE_ESTIMATE_PER_100K.items()})
        self.client.force_authenticate(self.rep)
        self.assertEqual(self.client.get("/api/staff/quotations/finance-options/").status_code, status.HTTP_403_FORBIDDEN)

    def test_multiple_finance_terms_use_vehicle_price_and_pdf_shows_each_calculation(self):
        terms = ["36m", "60m", "72m", "od"]
        created = self.create_quote(payload=self.payload(finance_terms=terms, finance_term="36m",
            finance_down_payment_lkr="100000.00"))
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(created.data["finance_terms"], terms)
        invalid = self.create_quote(payload=self.payload(finance_terms=terms, finance_down_payment_lkr="1000000.01"))
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("finance_down_payment_lkr", invalid.data)
        negative = self.create_quote(payload=self.payload(finance_terms=terms, finance_down_payment_lkr="-0.01"))
        self.assertEqual(negative.status_code, status.HTTP_400_BAD_REQUEST)

        reference = created.data["reference"]
        self.client.force_authenticate(self.manager)
        issued = self.client.post(f"/api/staff/quotations/{reference}/issue/", {}, format="json")
        self.assertEqual(issued.status_code, status.HTTP_200_OK)
        estimates = issued.data["issued_snapshot"]["finance_estimates"]
        self.assertEqual([row["term"] for row in estimates], terms)
        self.assertTrue(all(row["financed_amount_lkr"] == "900000.00" for row in estimates))
        self.assertEqual([row["monthly_estimate_lkr"] for row in estimates],
            ["32182.56", "22347.00", "20475.00", "11970.00"])
        pdf = self.client.get(f"/api/staff/quotations/{reference}/pdf/")
        self.assertEqual(pdf.status_code, status.HTTP_200_OK)
        for label, amount, rate in ((b"3 years", b"LKR 32,182.56", b"3,575.84"),
                                    (b"5 years", b"LKR 22,347.00", b"2,483.00"),
                                    (b"6 years", b"LKR 20,475.00", b"2,275.00"),
                                    (b"Speed Draft / OD", b"LKR 11,970.00", b"1,330.00")):
            self.assertIn(label, pdf.content)
            self.assertIn(amount, pdf.content)
            self.assertIn(rate, pdf.content)

    def test_role_permissions_draft_immutability_and_status_transitions(self):
        created = self.create_quote()
        reference = created.data["reference"]
        detail = f"/api/staff/quotations/{reference}/"
        self.client.force_authenticate(self.ceo)
        self.assertEqual(self.client.get(detail).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.patch(detail, {"vehicle_selling_price_lkr": "10"}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post("/api/staff/quotations/", self.payload(), format="json").status_code, status.HTTP_403_FORBIDDEN)
        for user in (self.admin, self.rep):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get("/api/staff/quotations/").status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(self.client.get(detail).status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.manager)
        issued = self.client.post(f"{detail}issue/", {}, format="json")
        self.assertEqual(issued.status_code, status.HTTP_200_OK)
        self.assertEqual(issued.data["status"], Quotation.Status.ISSUED)
        self.assertEqual(issued.data["issued_snapshot"]["customer"]["full_name"], self.customer.full_name)
        locked = self.client.patch(detail, {"vehicle_selling_price_lkr": "2"}, format="json")
        self.assertEqual(locked.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(self.client.post(f"{detail}issue/", {}, format="json").status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(self.client.post(f"{detail}void/", {}, format="json").status_code, status.HTTP_400_BAD_REQUEST)
        voided = self.client.post(f"{detail}void/", {"reason": "Customer requested cancellation."}, format="json")
        self.assertEqual(voided.status_code, status.HTTP_200_OK)
        self.assertEqual(voided.data["status"], Quotation.Status.VOIDED)
        self.assertTrue(AuditEvent.objects.filter(action="quotation.issued", subject=reference).exists())
        self.assertTrue(AuditEvent.objects.filter(action="quotation.voided", subject=reference).exists())

    def test_pdf_contains_snapshot_and_is_private_and_authorized(self):
        created = self.create_quote()
        reference = created.data["reference"]
        self.client.force_authenticate(self.manager)
        draft_pdf = self.client.get(f"/api/staff/quotations/{reference}/pdf/")
        self.assertEqual(draft_pdf.status_code, status.HTTP_409_CONFLICT)
        self.client.post(f"/api/staff/quotations/{reference}/issue/", {}, format="json")
        response = self.client.get(f"/api/staff/quotations/{reference}/pdf/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertTrue(response.content.startswith(b"%PDF-1.4"))
        self.assertIn(b"QUO-", response.content)
        self.assertIn(b"LKR 1,020,000.00", response.content)
        self.assertIn(b"Estimated monthly payment", response.content)
        self.client.force_authenticate(self.rep)
        self.assertEqual(self.client.get(f"/api/staff/quotations/{reference}/pdf/").status_code, status.HTTP_403_FORBIDDEN)

    def test_vehicle_not_registered_quote_expires_after_issue(self):
        created = self.create_quote(payload=self.payload(vehicle=None, vehicle_description="Vehicle to be imported",
            vehicle_specifications={"make": "Toyota", "model": "Land Cruiser"}, finance_term="", finance_down_payment_lkr="0"))
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        quote = Quotation.objects.get(reference=created.data["reference"])
        self.assertIsNone(quote.vehicle_id)
        self.client.force_authenticate(self.manager)
        issued = self.client.post(f"/api/staff/quotations/{quote.reference}/issue/", {}, format="json")
        self.assertEqual(issued.status_code, status.HTTP_200_OK)
        Quotation.objects.filter(pk=quote.pk).update(issue_date="2026-10-01", expiry_date="2026-10-30")
        listed = self.client.get("/api/staff/quotations/?status=expired")
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listed.data), 1)
        self.assertEqual(listed.data[0]["status"], Quotation.Status.EXPIRED)
        self.assertTrue(AuditEvent.objects.filter(action="quotation.expired", subject=quote.reference).exists())

    def test_long_customer_terms_paginate_the_pdf(self):
        created = self.create_quote(payload=self.payload(customer_terms="Detailed customer term " * 500))
        self.client.force_authenticate(self.manager)
        self.client.post(f"/api/staff/quotations/{created.data['reference']}/issue/", {}, format="json")
        response = self.client.get(f"/api/staff/quotations/{created.data['reference']}/pdf/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertRegex(response.content, rb"/Count [2-9]")
