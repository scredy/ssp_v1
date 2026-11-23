from decimal import Decimal

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.test import APITestCase

from .models import AuditEvent, Customer, RepresentativeProfile, Reservation, User, Vehicle


class ReservationApiTests(APITestCase):
    def make_user(self, username, role):
        return User.objects.create_user(username=username, password="Valid-password-914!", role=role,
                                        email=f"{username}@example.test")

    def make_vehicle(self, suffix="1", visibility=Vehicle.Visibility.PUBLISHED):
        return Vehicle.objects.create(make="Toyota", model="Corolla", manufacture_year=2023, mileage_km=12000,
            fuel_type=Vehicle.FuelType.PETROL, transmission=Vehicle.Transmission.AUTOMATIC, color="White",
            condition=Vehicle.Condition.USED, internal_identifier=f"CHASSIS-{suffix}", asking_price_lkr="10000000",
            visibility=visibility)

    def setUp(self):
        self.staff = self.make_user("staff", User.Role.STAFF)
        self.manager = self.make_user("manager", User.Role.MANAGER)
        self.ceo = self.make_user("ceo", User.Role.CEO)
        self.rep_user = self.make_user("rep", User.Role.REP)
        self.rep = RepresentativeProfile.objects.create(user=self.rep_user)
        self.customer = Customer.objects.create(full_name="Reservation Customer", email="customer@example.test", phone="0770000000")
        self.vehicle = self.make_vehicle()

    def payload(self, vehicle=None):
        return {"customer_id": self.customer.pk, "vehicle_reference": (vehicle or self.vehicle).reference,
                "representative_id": self.rep.pk, "agreed_price_lkr": "9850000.00",
                "advance_amount_lkr": "250000.00", "notes": "Customer requested a short hold."}

    def test_staff_can_create_active_reservation_and_vehicle_is_atomically_reserved(self):
        self.client.force_authenticate(self.staff)
        response = self.client.post("/api/staff/reservations/", self.payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["reference"].startswith("RSV-"))
        self.assertEqual(response.data["status"], Reservation.Status.ACTIVE)
        self.assertEqual(response.data["advance_payment_status"], "unverified")
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, Vehicle.Status.RESERVED)
        self.assertEqual(Reservation.objects.get().responsible_staff, self.staff)
        self.assertTrue(AuditEvent.objects.filter(action="reservation.created", subject=response.data["reference"]).exists())

    def test_duplicate_active_reservations_are_rejected_by_workflow_and_database_constraint(self):
        self.client.force_authenticate(self.staff)
        first = self.client.post("/api/staff/reservations/", self.payload(), format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        second = self.client.post("/api/staff/reservations/", self.payload(), format="json")
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Reservation.objects.filter(status=Reservation.Status.ACTIVE, vehicle=self.vehicle).count(), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Reservation.objects.create(customer=self.customer, vehicle=self.vehicle, responsible_staff=self.staff,
                agreed_price_lkr=Decimal("9000000"), advance_amount_lkr=0)

    def test_staff_cannot_reserve_archived_or_sold_vehicles(self):
        self.client.force_authenticate(self.staff)
        for suffix, vehicle_status in (("archived", Vehicle.Status.ARCHIVED), ("sold", Vehicle.Status.SOLD)):
            vehicle = self.make_vehicle(suffix)
            vehicle.status = vehicle_status
            vehicle.save(update_fields=["status"])
            response = self.client.post("/api/staff/reservations/", self.payload(vehicle), format="json")
            self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
            self.assertFalse(Reservation.objects.filter(vehicle=vehicle).exists())

    def test_non_staff_roles_cannot_create_reservations(self):
        vehicle = self.make_vehicle("permission")
        for user in (self.manager, self.ceo, self.make_user("admin", User.Role.ADMIN), self.rep_user):
            self.client.force_authenticate(user)
            response = self.client.post("/api/staff/reservations/", self.payload(vehicle), format="json")
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Reservation.objects.filter(vehicle=vehicle).exists())

    def test_release_requires_reason_restores_stock_and_preserves_history(self):
        self.client.force_authenticate(self.staff)
        created = self.client.post("/api/staff/reservations/", self.payload(), format="json")
        ref = created.data["reference"]
        missing_reason = self.client.post(f"/api/staff/reservations/{ref}/release/", {"release_reason": "  "}, format="json")
        self.assertEqual(missing_reason.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(f"/api/staff/reservations/{ref}/release/", {"release_reason": "Customer changed plans."}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Reservation.Status.RELEASED)
        self.assertEqual(response.data["release_reason"], "Customer changed plans.")
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, Vehicle.Status.AVAILABLE)
        self.assertEqual(Reservation.objects.count(), 1)
        self.assertTrue(AuditEvent.objects.filter(action="reservation.released", subject=ref).exists())

    def test_ceo_and_manager_are_read_only_and_other_roles_are_denied(self):
        reservation = Reservation.objects.create(customer=self.customer, vehicle=self.vehicle, responsible_staff=self.staff,
            agreed_price_lkr=Decimal("9000000"), advance_amount_lkr=Decimal("100000"))
        for user in (self.manager, self.ceo):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get("/api/staff/reservations/").status_code, status.HTTP_200_OK)
            self.assertEqual(self.client.post("/api/staff/reservations/", self.payload(self.make_vehicle(str(user.pk))), format="json").status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(self.client.post(f"/api/staff/reservations/{reservation.reference}/release/", {"release_reason": "test"}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        for user in (self.make_user("admin", User.Role.ADMIN), self.rep_user):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get("/api/staff/reservations/").status_code, status.HTTP_403_FORBIDDEN)

    def test_public_available_stock_excludes_reserved_vehicle_and_returns_after_release(self):
        self.client.force_authenticate(self.staff)
        self.assertIn(self.vehicle.reference, [item["reference"] for item in self.client.get("/api/cars/").data])
        created = self.client.post("/api/staff/reservations/", self.payload(), format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertNotIn(self.vehicle.reference, [item["reference"] for item in self.client.get("/api/cars/").data])
        self.client.post(f"/api/staff/reservations/{created.data['reference']}/release/", {"release_reason": "Released for testing."}, format="json")
        self.assertIn(self.vehicle.reference, [item["reference"] for item in self.client.get("/api/cars/").data])
