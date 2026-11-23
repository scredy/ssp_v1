from decimal import Decimal
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import AuditEvent, CommissionLedgerEntry, Customer, Handover, RepresentativeProfile, Sale, User, Vehicle


class RepresentativeApiTests(APITestCase):
    def user(self, username, role, **extra):
        return User.objects.create_user(username=username, password="Valid-password-914!", role=role,
                                        email=f"{username}@example.test", **extra)

    def test_manager_links_existing_rep_account_and_duplicate_is_rejected(self):
        manager = self.user("manager", User.Role.MANAGER)
        rep = self.user("rep-one", User.Role.REP, first_name="Ravi", last_name="Perera", phone="0771234567")
        self.client.force_authenticate(manager)
        response = self.client.post("/api/manager/reps/", {"account_id": rep.pk}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["full_name"], "Ravi Perera")
        self.assertTrue(response.data["reference"].startswith("REP-"))
        self.assertEqual(self.client.get("/api/manager/rep-accounts/").data, [])
        duplicate = self.client.post("/api/manager/reps/", {"account_id": rep.pk}, format="json")
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(RepresentativeProfile.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.filter(action="representative.linked").count(), 1)

    def test_manager_can_search_filter_and_update_business_status_without_disabling_login(self):
        manager = self.user("manager", User.Role.MANAGER)
        rep = self.user("rep-one", User.Role.REP, first_name="Ravi", last_name="Perera")
        profile = RepresentativeProfile.objects.create(user=rep, created_by=manager)
        self.client.force_authenticate(manager)
        self.assertEqual(len(self.client.get("/api/manager/reps/?search=Ravi").data), 1)
        self.assertEqual(self.client.get("/api/manager/reps/?status=inactive").data, [])
        response = self.client.patch(f"/api/manager/reps/{profile.pk}/", {"business_status": "inactive"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rep.refresh_from_db()
        self.assertEqual(response.data["business_status"], "inactive")
        self.assertTrue(rep.is_active)
        self.assertTrue(AuditEvent.objects.filter(action="representative.updated", subject=profile.reference).exists())

    def test_ceo_can_read_but_cannot_change_or_link_representatives(self):
        ceo = self.user("ceo", User.Role.CEO)
        rep = self.user("rep-one", User.Role.REP)
        profile = RepresentativeProfile.objects.create(user=rep)
        self.client.force_authenticate(ceo)
        self.assertEqual(self.client.get("/api/manager/reps/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/api/manager/reps/" + str(profile.pk) + "/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/api/manager/rep-accounts/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.patch(f"/api/manager/reps/{profile.pk}/", {"business_status": "inactive"}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post("/api/manager/reps/", {"account_id": rep.pk}, format="json").status_code, status.HTTP_403_FORBIDDEN)

    def test_representative_self_access_is_limited_to_own_profile(self):
        rep = self.user("rep-one", User.Role.REP)
        other = self.user("rep-two", User.Role.REP)
        own_profile = RepresentativeProfile.objects.create(user=rep)
        RepresentativeProfile.objects.create(user=other)
        self.client.force_authenticate(rep)
        response = self.client.get("/api/representative/profile/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["profile"]["id"], own_profile.pk)
        self.assertEqual(self.client.get("/api/manager/reps/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get("/api/manager/rep-accounts/").status_code, status.HTTP_403_FORBIDDEN)


    def make_assigned_sale(self, profile, manager, suffix):
        customer = Customer.objects.create(full_name=f"Customer {suffix}", email=f"customer-{suffix}@example.test")
        vehicle = Vehicle.objects.create(make="Toyota", model=f"Portal {suffix}", manufacture_year=2025, mileage_km=5000,
            fuel_type=Vehicle.FuelType.HYBRID, transmission=Vehicle.Transmission.AUTOMATIC, color="Blue",
            condition=Vehicle.Condition.USED, internal_identifier=f"REP-PORTAL-{suffix}", asking_price_lkr=Decimal("1000000.00"))
        vehicle.status = Vehicle.Status.SOLD
        vehicle.save(update_fields=["status", "updated_at"])
        sale = Sale.objects.create(vehicle=vehicle, customer=customer, representative=profile,
            agreed_price_lkr=Decimal("900000.00"), status=Sale.Status.CONFIRMED, confirmed_at=timezone.now(), created_by=manager)
        return sale, customer, vehicle

    def make_ledger_entry(self, sale, customer, vehicle, rep, manager):
        handover = Handover.objects.create(sale=sale, customer=customer, vehicle=vehicle, prepared_by=manager,
            status=Handover.Status.FINALIZED, delivery_date=timezone.localdate(),
            vehicle_condition_checklist={key: True for key in ("bodywork", "interior", "tyres", "lights", "odometer")},
            keys_documents_checklist={key: True for key in ("keys", "registration_documents", "insurance_documents", "service_documents")},
            customer_acknowledgement="Acknowledged.", customer_acknowledged_at=timezone.now(),
            finalized_by=manager, finalized_at=timezone.now())
        vehicle.status = Vehicle.Status.HANDED_OVER
        vehicle.save(update_fields=["status", "updated_at"])
        return CommissionLedgerEntry.objects.create(sale=sale, handover=handover, recipient=rep,
            sale_price_lkr=sale.agreed_price_lkr, commission_rate_percent=Decimal("2.500"),
            commission_amount_lkr=Decimal("22500.00"), policy_snapshot={"effective_date": "2026-01-01"}, created_by=manager)

    def test_rep_sales_and_commissions_are_read_only_and_scoped_to_authenticated_rep(self):
        manager = self.user("manager", User.Role.MANAGER)
        rep = self.user("rep-one", User.Role.REP, first_name="Ravi")
        other_rep = self.user("rep-two", User.Role.REP)
        profile = RepresentativeProfile.objects.create(user=rep)
        other_profile = RepresentativeProfile.objects.create(user=other_rep)
        sale, customer, vehicle = self.make_assigned_sale(profile, manager, "OWN")
        other_sale, other_customer, other_vehicle = self.make_assigned_sale(other_profile, manager, "OTHER")
        self.make_ledger_entry(sale, customer, vehicle, rep, manager)
        self.make_ledger_entry(other_sale, other_customer, other_vehicle, other_rep, manager)

        self.client.force_authenticate(rep)
        dashboard = self.client.get("/api/rep/dashboard/")
        self.assertEqual(dashboard.status_code, status.HTTP_200_OK)
        self.assertEqual(dashboard.data["confirmed_sales"], 1)
        self.assertEqual(dashboard.data["handed_over_sales"], 1)
        self.assertEqual(Decimal(dashboard.data["pending_commission_lkr"]), Decimal("22500.00"))
        sales = self.client.get("/api/rep/sales/?search=OWN")
        self.assertEqual(sales.status_code, status.HTTP_200_OK)
        self.assertEqual([row["reference"] for row in sales.data], [sale.reference])
        self.assertNotIn("customer_email", sales.data[0])
        self.assertNotIn("created_by_name", sales.data[0])
        self.assertEqual(self.client.get(f"/api/rep/sales/{other_sale.reference}/").status_code, status.HTTP_404_NOT_FOUND)
        commissions = self.client.get("/api/rep/commissions/")
        self.assertEqual(commissions.status_code, status.HTTP_200_OK)
        self.assertEqual([row["sale_reference"] for row in commissions.data], [sale.reference])
        self.assertNotIn("policy_snapshot", commissions.data[0])
        self.assertEqual(self.client.post("/api/rep/commissions/", {}, format="json").status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        self.client.force_authenticate(manager)
        self.assertEqual(self.client.get("/api/rep/sales/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get("/api/rep/commissions/").status_code, status.HTTP_403_FORBIDDEN)

    def test_commission_payout_transitions_leaderboard_and_rep_privacy(self):
        manager = self.user("payout-manager", User.Role.MANAGER)
        ceo = self.user("payout-ceo", User.Role.CEO)
        staff = self.user("payout-staff", User.Role.STAFF)
        rep = self.user("payout-rep-one", User.Role.REP, first_name="Asha")
        other_rep = self.user("payout-rep-two", User.Role.REP, first_name="Banu")
        own_profile = RepresentativeProfile.objects.create(user=rep)
        other_profile = RepresentativeProfile.objects.create(user=other_rep)
        own_sale, own_customer, own_vehicle = self.make_assigned_sale(own_profile, manager, "PAYOUT-OWN")
        other_sale, other_customer, other_vehicle = self.make_assigned_sale(other_profile, manager, "PAYOUT-OTHER")
        own_entry = self.make_ledger_entry(own_sale, own_customer, own_vehicle, rep, manager)
        other_entry = self.make_ledger_entry(other_sale, other_customer, other_vehicle, other_rep, manager)
        original_snapshot = own_entry.policy_snapshot.copy()

        self.client.force_authenticate(manager)
        self.assertEqual(self.client.post(f"/api/commissions/{own_entry.pk}/transition/", {"status": "paid", "payout_reference": "TOO-EARLY", "payout_date": "2026-11-21", "payout_amount_lkr": "22500.00"}, format="json").status_code, status.HTTP_409_CONFLICT)
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get("/api/commissions/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(f"/api/commissions/{own_entry.pk}/transition/", {"status": "approved"}, format="json").status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(ceo)
        approved = self.client.post(f"/api/commissions/{own_entry.pk}/transition/", {"status": "approved"}, format="json")
        self.assertEqual(approved.status_code, status.HTTP_200_OK)
        self.assertEqual(approved.data["approved_by"], ceo.username)
        self.client.post(f"/api/commissions/{own_entry.pk}/transition/", {"status": "approved"}, format="json")
        self.assertEqual(AuditEvent.objects.filter(action="commission.approved", subject=own_sale.reference).count(), 1)

        self.client.force_authenticate(manager)
        self.assertEqual(self.client.post(f"/api/commissions/{other_entry.pk}/transition/", {"status": "approved"}, format="json").status_code, status.HTTP_200_OK)
        invalid_amount = self.client.post(f"/api/commissions/{other_entry.pk}/transition/", {"status": "paid", "payout_reference": "BANK-OTHER", "payout_date": "2026-11-22", "payout_amount_lkr": "22000.00"}, format="json")
        self.assertEqual(invalid_amount.status_code, status.HTTP_400_BAD_REQUEST)
        payout_payload = {"status": "paid", "payout_reference": "BANK-OTHER", "payout_date": "2026-11-22", "payout_amount_lkr": "22500.00"}
        paid = self.client.post(f"/api/commissions/{other_entry.pk}/transition/", payout_payload, format="json")
        self.assertEqual(paid.status_code, status.HTTP_200_OK)
        self.assertEqual(paid.data["paid_by"], manager.username)
        self.assertEqual(self.client.post(f"/api/commissions/{other_entry.pk}/transition/", payout_payload, format="json").status_code, status.HTTP_200_OK)
        self.assertEqual(AuditEvent.objects.filter(action="commission.paid", subject=other_sale.reference).count(), 1)

        self.client.force_authenticate(ceo)
        self.assertEqual(self.client.post(f"/api/commissions/{own_entry.pk}/transition/", payout_payload, format="json").status_code, status.HTTP_409_CONFLICT)
        own_entry.refresh_from_db()
        self.assertEqual(own_entry.sale_price_lkr, own_sale.agreed_price_lkr)
        self.assertEqual(own_entry.commission_rate_percent, Decimal("2.500"))
        self.assertEqual(own_entry.commission_amount_lkr, Decimal("22500.00"))
        self.assertEqual(own_entry.policy_snapshot, original_snapshot)

        self.client.force_authenticate(manager)
        leaderboard = self.client.get("/api/commissions/?view=leaderboard")
        self.assertEqual(leaderboard.status_code, status.HTTP_200_OK)
        self.assertEqual([row["rep_name"] for row in leaderboard.data], ["Banu"])
        self.client.force_authenticate(rep)
        self.assertEqual(self.client.get("/api/rep/commissions/?view=leaderboard").data, [])
        own_rows = self.client.get("/api/rep/commissions/").data
        self.assertEqual([row["sale_reference"] for row in own_rows], [own_sale.reference])
        self.assertEqual(self.client.post(f"/api/commissions/{own_entry.pk}/transition/", {"status": "approved"}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(other_rep)
        private_board = self.client.get("/api/rep/commissions/?view=leaderboard")
        self.assertEqual([row["rep_name"] for row in private_board.data], ["Banu"])
        rep_summary = self.client.get("/api/rep/dashboard/")
        self.assertEqual(rep_summary.data["paid_commissions"], 1)
        self.assertEqual(Decimal(rep_summary.data["paid_commission_lkr"]), Decimal("22500.00"))

        self.client.force_authenticate(ceo)
        reversed_response = self.client.post(f"/api/commissions/{other_entry.pk}/transition/", {"status": "reversed", "reason": "Payout was duplicated by bank."}, format="json")
        self.assertEqual(reversed_response.status_code, status.HTTP_200_OK)
        self.assertEqual(reversed_response.data["status"], "reversed")
        self.assertEqual(self.client.post(f"/api/commissions/{other_entry.pk}/transition/", {"status": "reversed", "reason": "Payout was duplicated by bank."}, format="json").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/api/commissions/?view=leaderboard").data, [])
        self.client.force_authenticate(other_rep)
        self.assertEqual(self.client.get("/api/rep/commissions/?view=leaderboard").data, [])
        self.assertEqual(self.client.get("/api/rep/dashboard/").data["paid_commissions"], 0)
        self.client.force_authenticate(ceo)
        self.assertEqual(self.client.post(f"/api/commissions/{other_entry.pk}/transition/", payout_payload, format="json").status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(AuditEvent.objects.filter(action="commission.reversed", subject=other_sale.reference).count(), 1)
