from rest_framework import status
from rest_framework.test import APITestCase

from .models import AuditEvent, Customer, User, Vehicle


class ManualCustomerCreationTests(APITestCase):
    def make_user(self, username, role):
        return User.objects.create_user(username=username, password="Customer-Test-743!", role=role,
                                        email=f"{username}@example.test")

    def setUp(self):
        self.staff = self.make_user("customer-staff", User.Role.STAFF)
        self.payload = {"full_name": "Fictional Walk-in", "phone": "077 123-4567",
                        "email": "WalkIn@example.test", "preferred_contact": "phone",
                        "internal_notes": "Asked about weekday appointments."}

    def test_staff_can_create_normalized_customer_and_audit_without_contact_details(self):
        self.client.force_authenticate(self.staff)
        response = self.client.post("/api/staff/customers/", self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        customer = Customer.objects.get(pk=response.data["customer"]["id"])
        self.assertEqual(customer.full_name, "Fictional Walk-in")
        self.assertEqual(customer.phone, "+94771234567")
        self.assertEqual(customer.email, "walkin@example.test")
        self.assertTrue(response.data["created"])
        event = AuditEvent.objects.get(action="customer.created", subject=f"customer:{customer.pk}")
        self.assertEqual(event.actor, self.staff)
        self.assertEqual(event.details, {"source": "manual"})
        self.assertNotIn(customer.phone, str(event.details))
        self.assertIn(customer.pk, [item["id"] for item in self.client.get("/api/staff/customers/").data])
        self.assertIn(customer.pk, [item["id"] for item in self.client.get("/api/staff/reservations/options/").data["customers"]])
        vehicle = Vehicle.objects.create(make="Toyota", model="Walk-in test vehicle", manufacture_year=2024,
            mileage_km=5000, fuel_type=Vehicle.FuelType.HYBRID, transmission=Vehicle.Transmission.AUTOMATIC,
            color="Silver", condition=Vehicle.Condition.USED, internal_identifier="CUSTOMER-WALKIN-VEHICLE",
            asking_price_lkr="1000000.00")
        reservation = self.client.post("/api/staff/reservations/", {"customer_id": customer.pk,
            "vehicle_reference": vehicle.reference, "agreed_price_lkr": "950000.00", "advance_amount_lkr": "0.00"}, format="json")
        self.assertEqual(reservation.status_code, status.HTTP_201_CREATED)
        self.assertEqual(reservation.data["customer_id"], customer.pk)
        manager = self.make_user("customer-sales-manager", User.Role.MANAGER)
        self.client.force_authenticate(manager)
        self.assertIn(customer.pk, [item["id"] for item in self.client.get("/api/manager/sales/options/").data["customers"]])

    def test_invalid_name_phone_and_email_are_rejected(self):
        self.client.force_authenticate(self.staff)
        for changes, field in (({"full_name": "   "}, "full_name"),
                               ({"phone": "not a phone"}, "phone"),
                               ({"email": "bad-email"}, "email")):
            response = self.client.post("/api/staff/customers/", {**self.payload, **changes}, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn(field, response.data)
        self.assertEqual(Customer.objects.count(), 0)

    def test_normalized_phone_or_email_returns_existing_record_without_merging(self):
        existing_phone = Customer.objects.create(full_name="Existing Phone Match", phone="077-123-4567",
                                                 email="phone-match@example.test")
        existing_email = Customer.objects.create(full_name="Existing Email Match", phone="0719998888",
                                                 email="same@example.test")
        self.client.force_authenticate(self.staff)
        phone_result = self.client.post("/api/staff/customers/", {**self.payload, "full_name": "Different person", "email": ""}, format="json")
        self.assertEqual(phone_result.status_code, status.HTTP_200_OK)
        self.assertFalse(phone_result.data["created"])
        self.assertEqual(phone_result.data["customer"]["id"], existing_phone.pk)
        self.assertEqual(phone_result.data["matched_by"], ["phone"])
        email_result = self.client.post("/api/staff/customers/", {**self.payload, "phone": "071 555 0000", "email": "SAME@example.test"}, format="json")
        self.assertEqual(email_result.status_code, status.HTTP_200_OK)
        self.assertFalse(email_result.data["created"])
        self.assertEqual(email_result.data["customer"]["id"], existing_email.pk)
        self.assertEqual(email_result.data["matched_by"], ["email"])
        self.assertEqual(Customer.objects.count(), 2)
        self.assertEqual(existing_phone.full_name, "Existing Phone Match")

    def test_only_staff_can_create_and_existing_read_permissions_remain(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get("/api/staff/customers/").status_code, status.HTTP_200_OK)
        for role in (User.Role.MANAGER, User.Role.CEO):
            user = self.make_user(f"{role}-customer-review", role)
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get("/api/staff/customers/").status_code, status.HTTP_200_OK)
            self.assertEqual(self.client.post("/api/staff/customers/", self.payload, format="json").status_code,
                             status.HTTP_403_FORBIDDEN)
        for role in (User.Role.ADMIN, User.Role.REP):
            user = self.make_user(f"{role}-customer-denied", role)
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get("/api/staff/customers/").status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(self.client.post("/api/staff/customers/", self.payload, format="json").status_code,
                             status.HTTP_403_FORBIDDEN)
