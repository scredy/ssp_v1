from rest_framework.test import APITestCase

from .models import Customer, Enquiry, User
from .serializers import StaffEnquirySerializer


class EnquiryVehicleDisplayTests(APITestCase):

    def setUp(self):
        self.staff = User.objects.create_user(
            username="enquiry-vehicle-staff",
            email="enquiry-vehicle-staff@example.test",
            password="Strong-password-914!",
            role=User.Role.STAFF,
        )

        self.customer = Customer.objects.create(
            full_name="Test Customer",
            phone="0771234567",
            preferred_contact="phone",
        )

        self.client.force_authenticate(self.staff)

    def create_quote(self):
        return Enquiry.objects.create(
            customer=self.customer,
            kind=Enquiry.Kind.QUOTE,
            preferred_contact="phone",
            vehicle_description="2025 Toyota Yaris Cross",
            message="Please provide a quotation.",
        )

    def test_manual_vehicle_description_is_returned_as_label(self):
        enquiry = self.create_quote()
        data = StaffEnquirySerializer(enquiry).data

        self.assertEqual(
            data["vehicle_label"],
            "2025 Toyota Yaris Cross",
        )
        self.assertIsNone(data["vehicle_reference"])

    def test_staff_can_find_quote_by_requested_vehicle(self):
        enquiry = self.create_quote()

        response = self.client.get(
            "/api/staff/enquiries/",
            {"search": "Yaris Cross"},
        )

        self.assertEqual(response.status_code, 200)

        record = next(
            item for item in response.data
            if item["reference"] == enquiry.reference
        )

        self.assertEqual(
            record["vehicle_label"],
            "2025 Toyota Yaris Cross",
        )

    def test_quote_and_general_enquiries_cannot_be_scheduled(self):
        for kind in (Enquiry.Kind.QUOTE, Enquiry.Kind.GENERAL):
            enquiry = Enquiry.objects.create(
                customer=self.customer,
                kind=kind,
                preferred_contact="phone",
                vehicle_description="Toyota",
            )

            response = self.client.patch(
                f"/api/staff/enquiries/{enquiry.pk}/",
                {"status": "scheduled"},
                format="json",
            )

            self.assertEqual(response.status_code, 400)

            enquiry.refresh_from_db()
            self.assertEqual(enquiry.status, Enquiry.Status.NEW)
