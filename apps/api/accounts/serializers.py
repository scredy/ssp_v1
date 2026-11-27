from django.contrib.auth.password_validation import validate_password
from django.db.models import Q, Sum
from rest_framework import serializers
from django.utils import timezone
from decimal import Decimal

from .models import (BLApprovalRequest, Customer, Enquiry, HANDOVER_CONDITION_CHECKLIST,
    HANDOVER_KEYS_DOCUMENTS_CHECKLIST, Handover, HandoverApproval, HandoverDocumentReceipt, ImportMilestone, ImportOrder, Payment,
    Notification, Quotation, RepresentativeProfile, Reservation, Sale, User, Vehicle, VehiclePhoto)
from PIL import Image, UnidentifiedImageError
from .payment_summaries import sale_payment_summary


class CurrentUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "role", "account_type", "is_superuser")


class AccountSummarySerializer(serializers.ModelSerializer):
    is_onboarded = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "phone", "role", "account_type", "is_active", "is_onboarded", "is_superuser")

    def get_is_onboarded(self, user):
        return user.has_usable_password()


class AccountSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    account_type = serializers.ChoiceField(choices=[(User.AccountType.INTERNAL, "Internal")], default=User.AccountType.INTERNAL)

    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "phone", "role", "account_type")
        read_only_fields = ("id",)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account already uses this email address.")
        return value

    def validate(self, attrs):
        if attrs.get("account_type", User.AccountType.INTERNAL) != User.AccountType.INTERNAL:
            raise serializers.ValidationError({"account_type": "Only internal accounts can be created through this workflow."})
        return attrs

    def create(self, validated_data):
        user = User(**validated_data)
        user.account_type = User.AccountType.INTERNAL
        user.is_active = False
        user.is_staff = False
        user.is_superuser = False
        user.set_unusable_password()
        user.save()
        return user


class AccountUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "phone", "role", "account_type", "is_active")

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError("An account already uses this email address.")
        return value

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance


class PasswordSetupSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=256, trim_whitespace=True)
    password = serializers.CharField(max_length=128, write_only=True, trim_whitespace=False)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class VehiclePhotoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = VehiclePhoto
        fields = ("id", "url", "content_type", "created_at")

    def get_url(self, photo):
        return f"/api/vehicle-photos/{photo.pk}/"


class StaffVehicleSerializer(serializers.ModelSerializer):
    photos = VehiclePhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Vehicle
        fields = (
            "id", "reference", "make", "model", "variant", "manufacture_year", "mileage_km",
            "fuel_type", "transmission", "color", "condition", "internal_identifier",
            "asking_price_lkr", "description", "visibility", "status", "created_at", "updated_at", "photos",
        )
        read_only_fields = ("id", "reference", "created_at", "updated_at", "photos")

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if request and getattr(request.user, "role", None) != User.Role.STAFF:
            fields.pop("internal_identifier", None)
        return fields

    def validate_status(self, value):
        instance = self.instance
        if instance is None:
            if value != Vehicle.Status.AVAILABLE:
                raise serializers.ValidationError("New vehicles must start as available.")
            return value
        allowed = {(Vehicle.Status.AVAILABLE, Vehicle.Status.ARCHIVED),
                   (Vehicle.Status.ARCHIVED, Vehicle.Status.AVAILABLE)}
        if value != instance.status and (instance.status, value) not in allowed:
            raise serializers.ValidationError("Only available and archived transitions are enabled.")
        return value


class PublicVehicleSerializer(serializers.ModelSerializer):
    photos = VehiclePhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Vehicle
        fields = (
            "reference", "make", "model", "variant", "manufacture_year", "mileage_km",
            "fuel_type", "transmission", "color", "condition", "asking_price_lkr",
            "description", "photos",
        )


class PublicEnquirySerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=160, trim_whitespace=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, trim_whitespace=True)
    preferred_contact = serializers.ChoiceField(choices=Customer._meta.get_field("preferred_contact").choices)
    kind = serializers.ChoiceField(choices=Enquiry.Kind.choices)
    vehicle_reference = serializers.CharField(max_length=16, required=False, allow_blank=True)
    vehicle_description = serializers.CharField(max_length=160, required=False, allow_blank=True, trim_whitespace=True)
    requested_at = serializers.DateTimeField(required=False, allow_null=True)
    message = serializers.CharField(max_length=3000, required=False, allow_blank=True)
    idempotency_key = serializers.CharField(min_length=16, max_length=64, trim_whitespace=True)

    def validate_phone(self, value):
        value = value.strip()
        digits = "".join(character for character in value if character.isdigit())
        if value and (len(digits) < 7 or len(digits) > 15 or any(character not in "+-() .0123456789" for character in value)):
            raise serializers.ValidationError("Enter a valid phone number.")
        return ("+" if value.startswith("+") else "") + digits if value else ""

    def validate(self, attrs):
        if attrs["kind"] == Enquiry.Kind.QUOTE and not attrs.get("vehicle_description", "").strip():
            raise serializers.ValidationError({"vehicle_description": "Enter the vehicle you are requesting a quote for."})
        if attrs["kind"] in (Enquiry.Kind.APPOINTMENT, Enquiry.Kind.TEST_DRIVE):
            if not attrs.get("phone"):
                raise serializers.ValidationError({"phone": "Phone is required for an appointment request."})
            if not attrs.get("email"):
                raise serializers.ValidationError({"email": "Email is required so we can send your request confirmation."})
        if not attrs.get("email") and not attrs.get("phone"):
            raise serializers.ValidationError("Provide an email address or phone number.")
        if attrs["preferred_contact"] == "email" and not attrs.get("email"):
            raise serializers.ValidationError({"email": "Email is required for the selected contact method."})
        if attrs["kind"] in (Enquiry.Kind.APPOINTMENT, Enquiry.Kind.TEST_DRIVE):
            when = attrs.get("requested_at")
            if not when or when <= timezone.now():
                raise serializers.ValidationError({"requested_at": "Choose a future requested date and time."})
        elif attrs.get("requested_at"):
            raise serializers.ValidationError({"requested_at": "A requested time is only used for appointments."})
        reference = attrs.get("vehicle_reference", "").strip()
        if reference:
            vehicle = Vehicle.objects.filter(reference=reference, visibility=Vehicle.Visibility.PUBLISHED,
                                             status=Vehicle.Status.AVAILABLE).first()
            if not vehicle:
                raise serializers.ValidationError({"vehicle_reference": "This vehicle is no longer available."})
            attrs["vehicle"] = vehicle
        return attrs


class StaffEnquirySerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    customer_email = serializers.EmailField(source="customer.email", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)
    vehicle_reference = serializers.CharField(source="vehicle.reference", read_only=True, allow_null=True)
    vehicle_label = serializers.SerializerMethodField()

    class Meta:
        model = Enquiry
        fields = ("id", "reference", "kind", "status", "customer_name", "customer_email", "customer_phone",
                  "preferred_contact", "vehicle_reference", "vehicle_label", "vehicle_description", "requested_at", "scheduled_at",
                  "message", "internal_notes", "confirmation_email_status", "confirmation_email_schedule",
                  "confirmation_email_recipient", "confirmation_email_sent_at", "confirmation_email_error",
                  "created_at", "updated_at")
        read_only_fields = ("id", "reference", "kind", "customer_name", "customer_email", "customer_phone",
                            "preferred_contact", "vehicle_reference", "vehicle_label", "vehicle_description", "requested_at", "message",
                            "confirmation_email_status", "confirmation_email_schedule", "confirmation_email_recipient",
                            "confirmation_email_sent_at", "confirmation_email_error", "created_at", "updated_at")

    def get_vehicle_label(self, obj):
        return f"{obj.vehicle.manufacture_year} {obj.vehicle.make} {obj.vehicle.model}" if obj.vehicle else ""

    def validate(self, attrs):
        status_value = attrs.get("status", self.instance.status if self.instance else Enquiry.Status.NEW)
        scheduled = attrs.get("scheduled_at", self.instance.scheduled_at if self.instance else None)
        if status_value == Enquiry.Status.SCHEDULED:
            if self.instance is None or self.instance.kind not in (Enquiry.Kind.APPOINTMENT, Enquiry.Kind.TEST_DRIVE):
                raise serializers.ValidationError({"status": "Only appointment requests can be scheduled."})
            if not scheduled:
                raise serializers.ValidationError({"scheduled_at": "Set a confirmed date and time when scheduling."})
            if scheduled <= timezone.now():
                raise serializers.ValidationError({"scheduled_at": "Choose a future confirmed date and time."})
        return attrs


class StaffCustomerSerializer(serializers.ModelSerializer):
    enquiry_count = serializers.IntegerField(source="enquiries.count", read_only=True)

    class Meta:
        model = Customer
        fields = ("id", "full_name", "email", "phone", "preferred_contact", "internal_notes", "created_at", "updated_at", "enquiry_count")
        read_only_fields = ("id", "created_at", "updated_at", "enquiry_count")


def normalize_customer_phone(value):
    digits = "".join(character for character in value if character in "0123456789")
    if value.strip().startswith("00") and digits.startswith("00"):
        digits = digits[2:]
    elif len(digits) == 10 and digits.startswith("0"):
        digits = "94" + digits[1:]
    if not 8 <= len(digits) <= 15 or digits.startswith("0"):
        raise serializers.ValidationError("Enter a valid phone number, including its country code if international.")
    return f"+{digits}"


class CustomerCreateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=160, trim_whitespace=True)
    phone = serializers.CharField(max_length=32, trim_whitespace=True)
    email = serializers.EmailField(required=False, allow_blank=True, trim_whitespace=True)
    preferred_contact = serializers.ChoiceField(choices=Customer._meta.get_field("preferred_contact").choices,
                                                required=False, default="phone")
    internal_notes = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)

    def validate_phone(self, value):
        return normalize_customer_phone(value)

    def validate_email(self, value):
        return value.strip().lower()


class RepresentativeProfileSerializer(serializers.ModelSerializer):
    account_id = serializers.IntegerField(source="user_id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    full_name = serializers.SerializerMethodField()
    email = serializers.EmailField(source="user.email", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True, allow_null=True)
    system_account_active = serializers.BooleanField(source="user.is_active", read_only=True)

    class Meta:
        model = RepresentativeProfile
        fields = ("id", "reference", "account_id", "username", "first_name", "last_name", "full_name", "email", "phone", "system_account_active", "business_status", "created_at", "updated_at")
        read_only_fields = fields

    def get_full_name(self, obj):
        return " ".join(part for part in (obj.user.first_name, obj.user.last_name) if part) or obj.user.username


class RepresentativeCreateSerializer(serializers.ModelSerializer):
    account_id = serializers.PrimaryKeyRelatedField(source="user", queryset=User.objects.filter(role=User.Role.REP), write_only=True)

    class Meta:
        model = RepresentativeProfile
        fields = ("account_id", "business_status")

    def validate_account_id(self, user):
        if RepresentativeProfile.objects.filter(user=user).exists():
            raise serializers.ValidationError("This representative account is already linked.")
        return user


class RepresentativeUpdateSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source="user.first_name", max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(source="user.last_name", max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(source="user.email", required=False, allow_blank=True)
    phone = serializers.CharField(source="user.phone", max_length=32, required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = RepresentativeProfile
        fields = ("business_status", "first_name", "last_name", "email", "phone")

    def update(self, instance, validated_data):
        user_changes = validated_data.pop("user", {})
        for field, value in validated_data.items():
            setattr(instance, field, value)
        for field, value in user_changes.items():
            setattr(instance.user, field, value)
        if user_changes:
            instance.user.save(update_fields=list(user_changes.keys()))
        if validated_data or user_changes:
            instance.save()
        return instance


class ReservationCreateSerializer(serializers.Serializer):
    customer_id = serializers.PrimaryKeyRelatedField(source="customer", queryset=Customer.objects.all())
    vehicle_reference = serializers.CharField(max_length=16)
    representative_id = serializers.PrimaryKeyRelatedField(source="representative", queryset=RepresentativeProfile.objects.filter(business_status=RepresentativeProfile.BusinessStatus.ACTIVE), required=False, allow_null=True)
    agreed_price_lkr = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    advance_amount_lkr = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"), required=False, default=0)
    notes = serializers.CharField(max_length=5000, required=False, allow_blank=True)

    def validate_vehicle_reference(self, value):
        return value.strip()

    def validate(self, attrs):
        if attrs.get("advance_amount_lkr", Decimal("0")) > attrs["agreed_price_lkr"]:
            raise serializers.ValidationError({"advance_amount_lkr": "Advance amount cannot exceed the agreed price."})
        return attrs


class ReservationSerializer(serializers.ModelSerializer):
    customer_id = serializers.IntegerField(read_only=True)
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    customer_email = serializers.EmailField(source="customer.email", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)
    vehicle_reference = serializers.CharField(source="vehicle.reference", read_only=True)
    vehicle_name = serializers.SerializerMethodField()
    representative_reference = serializers.CharField(source="representative.reference", read_only=True, allow_null=True)
    representative_id = serializers.IntegerField(read_only=True, allow_null=True)
    representative_name = serializers.SerializerMethodField()
    responsible_staff_id = serializers.IntegerField(read_only=True)
    responsible_staff_name = serializers.SerializerMethodField()
    advance_payment_status = serializers.SerializerMethodField()
    released_by_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Reservation
        fields = ("id", "reference", "customer_id", "customer_name", "customer_email", "customer_phone",
                  "vehicle_reference", "vehicle_name", "representative_id", "representative_reference", "representative_name",
                  "responsible_staff_id", "responsible_staff_name", "agreed_price_lkr", "advance_amount_lkr",
                  "advance_payment_status", "notes", "status", "release_reason", "released_by_id",
                  "created_at", "updated_at", "released_at")
        read_only_fields = fields

    def get_vehicle_name(self, obj):
        return f"{obj.vehicle.manufacture_year} {obj.vehicle.make} {obj.vehicle.model}"

    def get_representative_name(self, obj):
        if not obj.representative:
            return ""
        user = obj.representative.user
        return " ".join(part for part in (user.first_name, user.last_name) if part) or user.username

    def get_responsible_staff_name(self, obj):
        user = obj.responsible_staff
        return " ".join(part for part in (user.first_name, user.last_name) if part) or user.username

    def get_advance_payment_status(self, obj):
        return "unverified" if obj.advance_amount_lkr else "not_recorded"


class ReservationReleaseSerializer(serializers.Serializer):
    release_reason = serializers.CharField(max_length=1000, trim_whitespace=True)

    def validate_release_reason(self, value):
        if not value:
            raise serializers.ValidationError("A release reason is required.")
        return value


class SaleCreateSerializer(serializers.Serializer):
    customer_id = serializers.PrimaryKeyRelatedField(source="customer", queryset=Customer.objects.all(), required=False)
    vehicle_reference = serializers.CharField(max_length=16, required=False)
    representative_id = serializers.PrimaryKeyRelatedField(source="representative", queryset=RepresentativeProfile.objects.all(), required=False, allow_null=True)
    reservation_reference = serializers.CharField(max_length=24, required=False, allow_blank=True, allow_null=True)
    sale_type = serializers.ChoiceField(choices=Sale.SaleType.choices, default=Sale.SaleType.DIRECT)
    import_reference = serializers.CharField(max_length=24, required=False, allow_blank=True)
    agreed_price_lkr = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    sale_date = serializers.DateField(required=False, default=timezone.localdate)

    def validate_vehicle_reference(self, value):
        return value.strip()

    def validate_reservation_reference(self, value):
        return value.strip() if value else ""

    def validate(self, attrs):
        sale_type = attrs["sale_type"]
        import_reference = attrs.get("import_reference", "").strip()
        if sale_type == Sale.SaleType.IMPORT:
            if not import_reference:
                raise serializers.ValidationError({"import_reference": "Select a ready import order."})
            if attrs.get("reservation_reference"):
                raise serializers.ValidationError({"reservation_reference": "Import orders cannot be linked to a stock reservation."})
            if attrs.get("customer") or attrs.get("vehicle_reference"):
                raise serializers.ValidationError("Import customer and vehicle are taken from the selected import order.")
            attrs["import_reference"] = import_reference
        else:
            reservation_reference = attrs.get("reservation_reference", "")
            if not attrs.get("customer") and not reservation_reference:
                raise serializers.ValidationError({"customer_id": "Select a customer."})
            if not attrs.get("vehicle_reference", "").strip() and not reservation_reference:
                raise serializers.ValidationError({"vehicle_reference": "Select a vehicle."})
            if import_reference:
                raise serializers.ValidationError({"import_reference": "Only import sales can use an import order."})
        return attrs


class SaleSerializer(serializers.ModelSerializer):
    customer_id = serializers.IntegerField(read_only=True)
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    vehicle_reference = serializers.CharField(source="vehicle.reference", read_only=True)
    vehicle_name = serializers.SerializerMethodField()
    representative_id = serializers.IntegerField(read_only=True, allow_null=True)
    representative_name = serializers.SerializerMethodField()
    reservation_reference = serializers.CharField(source="reservation.reference", read_only=True, allow_null=True)
    import_reference = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Sale
        fields = ("id", "reference", "vehicle_reference", "vehicle_name", "customer_id", "customer_name",
                  "representative_id", "representative_name", "reservation_reference", "import_reference", "sale_type",
                  "agreed_price_lkr", "sale_date", "status", "created_by_name", "created_at", "updated_at", "confirmed_at")
        read_only_fields = fields

    def get_vehicle_name(self, obj):
        return f"{obj.vehicle.manufacture_year} {obj.vehicle.make} {obj.vehicle.model}"

    def get_import_reference(self, obj):
        return obj.import_order.reference if obj.import_order_id else ""

    def get_representative_name(self, obj):
        if not obj.representative:
            return ""
        user = obj.representative.user
        return " ".join(p for p in (user.first_name, user.last_name) if p) or user.username

    def get_created_by_name(self, obj):
        user = obj.created_by
        return " ".join(p for p in (user.first_name, user.last_name) if p) or user.username


class PaymentCreateSerializer(serializers.Serializer):
    sale_reference = serializers.CharField(max_length=24, required=False, allow_blank=True, allow_null=True)
    reservation_reference = serializers.CharField(max_length=24, required=False, allow_blank=True, allow_null=True)
    import_reference = serializers.CharField(max_length=24, required=False, allow_blank=True, allow_null=True)
    amount_lkr = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    payment_type = serializers.ChoiceField(choices=[
        (value, label) for value, label in Payment.PaymentType.choices
        if value != Payment.PaymentType.UNSPECIFIED
    ], required=False, default=Payment.PaymentType.PARTIAL)
    method = serializers.ChoiceField(choices=Payment.Method.choices)
    funds_cleared = serializers.BooleanField(required=False, default=False)
    transaction_reference = serializers.CharField(max_length=120, required=False, allow_blank=True, default="", trim_whitespace=True)
    idempotency_key = serializers.CharField(max_length=64, trim_whitespace=True)
    payment_date = serializers.DateField(required=False, default=timezone.localdate)
    evidence = serializers.FileField(required=False, allow_empty_file=False)
    notes = serializers.CharField(max_length=3000, required=False, allow_blank=True)

    def validate_sale_reference(self, value):
        return value.strip() if value else ""

    def validate_reservation_reference(self, value):
        return value.strip() if value else ""

    def validate_import_reference(self, value):
        return value.strip() if value else ""

    def validate_evidence(self, file):
        if file.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("Payment evidence must be 10 MB or smaller.")
        allowed = {"image/jpeg", "image/png", "application/pdf"}
        content_type = getattr(file, "content_type", "")
        if content_type not in allowed:
            raise serializers.ValidationError("Evidence must be a JPEG, PNG, or PDF file.")
        head = file.read(8)
        file.seek(0)
        if content_type == "application/pdf":
            if not head.startswith(b"%PDF-"):
                raise serializers.ValidationError("The uploaded file is not a valid PDF.")
        else:
            try:
                image = Image.open(file)
                expected = "JPEG" if content_type == "image/jpeg" else "PNG"
                if image.format != expected:
                    raise serializers.ValidationError("Evidence image type does not match its content.")
                if image.width < 1 or image.height < 1 or image.width > 12000 or image.height > 12000 or image.width * image.height > 50_000_000:
                    raise serializers.ValidationError("The uploaded evidence image dimensions are not allowed.")
                image.verify()
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
                raise serializers.ValidationError("The uploaded evidence image is invalid.")
            finally:
                file.seek(0)
        return file

    def validate(self, attrs):
        if attrs.get("method") != Payment.Method.CASH and not attrs.get("funds_cleared"):
            raise serializers.ValidationError({"funds_cleared": "Confirm that non-cash funds have been received and cleared before recording."})
        sale_ref = attrs.get("sale_reference", "")
        reservation_ref = attrs.get("reservation_reference", "")
        import_ref = attrs.get("import_reference", "")
        if sum(bool(target) for target in (sale_ref, reservation_ref, import_ref)) != 1:
            raise serializers.ValidationError("Provide exactly one sale_reference, reservation_reference, or import_reference.")
        if attrs.get("transaction_reference") == "":
            attrs.pop("transaction_reference", None)
        return attrs


class PaymentSerializer(serializers.ModelSerializer):
    sale_reference = serializers.CharField(source="sale.reference", read_only=True, allow_null=True)
    reservation_reference = serializers.CharField(source="reservation.reference", read_only=True, allow_null=True)
    import_reference = serializers.CharField(source="import_order.reference", read_only=True, allow_null=True)
    customer_name = serializers.SerializerMethodField()
    recorded_by_name = serializers.CharField(source="recorded_by.username", read_only=True)
    verified_by_name = serializers.CharField(source="verified_by.username", read_only=True, allow_null=True)
    rejected_by_name = serializers.CharField(source="rejected_by.username", read_only=True, allow_null=True)
    reversed_by_name = serializers.CharField(source="reversed_by.username", read_only=True, allow_null=True)
    evidence_attached = serializers.SerializerMethodField()
    evidence_url = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = ("reference", "sale_reference", "reservation_reference", "import_reference", "customer_name", "amount_lkr", "payment_type", "funds_cleared", "method",
                  "transaction_reference", "payment_date", "notes", "recorded_by_name", "created_at", "status",
                  "verified_by_name", "verified_at", "rejected_by_name", "rejected_at", "rejection_reason",
                  "reversed_by_name", "reversed_at", "reversal_reason",
                  "evidence_attached", "evidence_url")
        read_only_fields = fields

    def get_customer_name(self, obj):
        if obj.sale_id:
            return obj.sale.customer.full_name
        if obj.reservation_id:
            return obj.reservation.customer.full_name
        return obj.import_order.customer.full_name

    def get_import_reference(self, obj):
        if obj.import_order_id:
            return obj.import_order.reference
        if obj.sale_id and obj.sale.import_order_id:
            return obj.sale.import_order.reference
        return None

    def get_evidence_attached(self, obj):
        return bool(obj.evidence)

    def get_evidence_url(self, obj):
        if not obj.evidence:
            return None
        return f"/api/staff/payments/{obj.reference}/evidence/"


class PaymentRejectSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField(max_length=1000, trim_whitespace=True)

    def validate_rejection_reason(self, value):
        if not value:
            raise serializers.ValidationError("A rejection reason is required.")
        return value


class ImportOrderSerializer(serializers.ModelSerializer):
    customer_id = serializers.PrimaryKeyRelatedField(source="customer", queryset=Customer.objects.all(), write_only=True)
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    vehicle_id = serializers.PrimaryKeyRelatedField(source="vehicle", queryset=Vehicle.objects.all(), required=False, allow_null=True)
    vehicle_reference = serializers.CharField(source="vehicle.reference", read_only=True, allow_null=True)
    responsible_staff_name = serializers.CharField(source="responsible_staff.username", read_only=True)

    class Meta:
        model = ImportOrder
        fields = ("id", "reference", "customer_id", "customer_name", "vehicle_id", "vehicle_reference",
                  "vehicle_description", "vehicle_details", "country_of_origin", "status", "shipping_information",
                  "estimated_arrival", "internal_notes", "customer_updates", "responsible_staff_name", "created_at", "updated_at")
        read_only_fields = ("id", "reference", "customer_name", "vehicle_reference", "status", "responsible_staff_name", "created_at", "updated_at")

    def validate_vehicle(self, value):
        if self.instance and self.instance.vehicle_id == (value.pk if value else None):
            return value
        if value and value.status != Vehicle.Status.AVAILABLE:
            raise serializers.ValidationError("Link only an available vehicle to an import order.")
        if self.instance and self.instance.vehicle_id != (value.pk if value else None) and self.instance.sales.exists():
            raise serializers.ValidationError("The vehicle link cannot change after a sale has been created.")
        return value

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if request and getattr(request.user, "role", None) != User.Role.STAFF:
            for name in ("internal_notes", "vehicle_details"):
                fields.pop(name, None)
        return fields


class ImportMilestoneCreateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=ImportMilestone.Kind.choices)
    occurred_at = serializers.DateTimeField(required=False)
    customer_description = serializers.CharField(max_length=500, trim_whitespace=True)
    payment_reference = serializers.CharField(max_length=24, required=False, allow_blank=True, write_only=True)

    def validate(self, attrs):
        payment_reference = attrs.get("payment_reference", "").strip()
        if attrs["kind"] == ImportMilestone.Kind.PAYMENT_VERIFIED and not payment_reference:
            raise serializers.ValidationError({"payment_reference": "Select an existing verified payment for this milestone."})
        if attrs["kind"] != ImportMilestone.Kind.PAYMENT_VERIFIED and payment_reference:
            raise serializers.ValidationError({"payment_reference": "A payment can only be linked to a payment verification milestone."})
        if attrs["kind"] == ImportMilestone.Kind.FINALIZED_HANDOVER:
            raise serializers.ValidationError({"kind": "Finalized handover is reserved for the handover workflow."})
        attrs["payment_reference"] = payment_reference
        return attrs


class ImportMilestoneSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = ImportMilestone
        fields = ("id", "kind", "occurred_at", "actor_name", "customer_description", "created_at")
        read_only_fields = fields


class BLApprovalRequestCreateSerializer(serializers.Serializer):
    request_note = serializers.CharField(max_length=2000, required=False, allow_blank=True, trim_whitespace=True)


class BLApprovalDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=(BLApprovalRequest.Status.APPROVED, BLApprovalRequest.Status.REJECTED))
    rejection_reason = serializers.CharField(max_length=1000, required=False, allow_blank=True, trim_whitespace=True)

    def validate(self, attrs):
        if attrs["decision"] == BLApprovalRequest.Status.REJECTED and not attrs.get("rejection_reason", "").strip():
            raise serializers.ValidationError({"rejection_reason": "A rejection reason is required."})
        if attrs["decision"] == BLApprovalRequest.Status.APPROVED:
            attrs["rejection_reason"] = ""
        return attrs


class BLApprovalRequestSerializer(serializers.ModelSerializer):
    import_reference = serializers.CharField(source="import_order.reference", read_only=True)
    requested_by_name = serializers.CharField(source="requested_by.username", read_only=True)
    decided_by_name = serializers.CharField(source="decided_by.username", read_only=True, allow_null=True)

    class Meta:
        model = BLApprovalRequest
        fields = ("id", "reference", "import_reference", "request_note", "status", "requested_by_name", "requested_at",
                  "decided_by_name", "decided_at", "rejection_reason")
        read_only_fields = fields


class QuotationDraftSerializer(serializers.ModelSerializer):
    vehicle_selling_price_lkr = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"), required=False)
    additional_charges_lkr = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.00"), required=False, default=Decimal("0.00"))
    discount_lkr = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.00"), required=False, default=Decimal("0.00"))
    finance_down_payment_lkr = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.00"), required=False, default=Decimal("0.00"))
    finance_terms = serializers.ListField(child=serializers.ChoiceField(choices=Quotation.FinanceTerm.choices), required=False, allow_empty=True)

    class Meta:
        model = Quotation
        fields = ("id", "reference", "customer", "vehicle", "import_order", "vehicle_description", "vehicle_specifications",
                  "vehicle_selling_price_lkr", "additional_charges_lkr", "discount_lkr", "quotation_total_lkr", "issue_date",
                  "expiry_date", "internal_notes", "customer_terms", "finance_term", "finance_terms", "finance_down_payment_lkr", "status",
                  "responsible_staff", "issued_at", "issued_snapshot", "void_reason", "created_at", "updated_at")
        read_only_fields = ("id", "reference", "quotation_total_lkr", "status", "responsible_staff", "issued_at",
                            "issued_snapshot", "void_reason", "created_at", "updated_at")

    def validate(self, attrs):
        instance = self.instance
        vehicle = attrs.get("vehicle", getattr(instance, "vehicle", None))
        import_order = attrs.get("import_order", getattr(instance, "import_order", None))
        customer = attrs.get("customer", getattr(instance, "customer", None))
        if import_order and customer and import_order.customer_id != customer.pk:
            raise serializers.ValidationError({"import_order": "The import order must belong to the selected customer."})
        if vehicle:
            if import_order and import_order.vehicle_id and import_order.vehicle_id != vehicle.pk:
                raise serializers.ValidationError({"vehicle": "The vehicle must match the linked import order."})
            attrs.setdefault("vehicle_description", f"{vehicle.manufacture_year} {vehicle.make} {vehicle.model} {vehicle.variant}".strip())
            if not attrs.get("vehicle_specifications") and not (instance and instance.vehicle_specifications):
                attrs.setdefault("vehicle_specifications", {"year": vehicle.manufacture_year, "make": vehicle.make,
                    "model": vehicle.model, "variant": vehicle.variant, "mileage_km": vehicle.mileage_km,
                    "fuel_type": vehicle.get_fuel_type_display(), "transmission": vehicle.get_transmission_display(),
                    "condition": vehicle.get_condition_display(), "colour": vehicle.color})
            if "vehicle_selling_price_lkr" not in attrs and not instance:
                attrs["vehicle_selling_price_lkr"] = vehicle.asking_price_lkr
        description = attrs.get("vehicle_description", getattr(instance, "vehicle_description", ""))
        if not description.strip():
            raise serializers.ValidationError({"vehicle_description": "Enter the vehicle description."})
        issue_date = attrs.get("issue_date", getattr(instance, "issue_date", timezone.localdate()))
        expiry_date = attrs.get("expiry_date", getattr(instance, "expiry_date", None))
        if expiry_date and expiry_date < issue_date:
            raise serializers.ValidationError({"expiry_date": "Expiry date cannot be before the issue date."})
        price = attrs.get("vehicle_selling_price_lkr", getattr(instance, "vehicle_selling_price_lkr", None))
        if price is None:
            raise serializers.ValidationError({"vehicle_selling_price_lkr": "Enter the vehicle selling price."})
        if "finance_terms" in attrs:
            selected_terms = attrs["finance_terms"]
            attrs["finance_term"] = selected_terms[0] if selected_terms else ""
        elif "finance_term" in attrs:
            selected_terms = [attrs["finance_term"]] if attrs["finance_term"] else []
            attrs["finance_terms"] = selected_terms
        elif instance:
            selected_terms = instance.finance_terms or ([instance.finance_term] if instance.finance_term else [])
            attrs["finance_terms"] = selected_terms
            attrs["finance_term"] = selected_terms[0] if selected_terms else ""
        charges = attrs.get("additional_charges_lkr", getattr(instance, "additional_charges_lkr", Decimal("0.00")))
        discount = attrs.get("discount_lkr", getattr(instance, "discount_lkr", Decimal("0.00")))
        down_payment = attrs.get("finance_down_payment_lkr", getattr(instance, "finance_down_payment_lkr", Decimal("0.00")))
        total = price + charges - discount
        if total < 0:
            raise serializers.ValidationError({"discount_lkr": "Discount cannot exceed the vehicle price and charges."})
        if down_payment > price:
            raise serializers.ValidationError({"finance_down_payment_lkr": "Down payment cannot exceed the vehicle selling price."})
        return attrs


class QuotationSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    vehicle_reference = serializers.CharField(source="vehicle.reference", read_only=True, allow_null=True)
    import_reference = serializers.CharField(source="import_order.reference", read_only=True, allow_null=True)
    responsible_staff_name = serializers.CharField(source="responsible_staff.username", read_only=True)

    class Meta:
        model = Quotation
        fields = ("id", "reference", "customer", "customer_name", "vehicle", "vehicle_reference", "import_order",
                  "import_reference", "vehicle_description", "vehicle_specifications", "vehicle_selling_price_lkr",
                  "additional_charges_lkr", "discount_lkr", "quotation_total_lkr", "issue_date", "expiry_date",
                  "internal_notes", "customer_terms", "finance_term", "finance_terms", "finance_down_payment_lkr", "status",
                  "responsible_staff_name", "issued_at", "issued_snapshot", "voided_at", "voided_by",
                  "void_reason", "created_at", "updated_at")
        read_only_fields = fields


class HandoverPreparationSerializer(serializers.Serializer):
    sale_reference = serializers.CharField(max_length=24, required=False, write_only=True)
    delivery_date = serializers.DateField(required=False, allow_null=True)
    vehicle_condition_checklist = serializers.JSONField(required=False)
    keys_documents_checklist = serializers.JSONField(required=False)
    customer_acknowledgement = serializers.CharField(max_length=2000, required=False, allow_blank=True, trim_whitespace=True)
    supporting_evidence = serializers.FileField(required=False, allow_empty_file=False)
    internal_notes = serializers.CharField(max_length=5000, required=False, allow_blank=True)

    def _validate_checklist(self, value, allowed, field):
        if not isinstance(value, dict):
            raise serializers.ValidationError({field: "Checklist must be an object of item names and boolean values."})
        unknown = set(value) - set(allowed)
        if unknown:
            raise serializers.ValidationError({field: f"Unknown checklist item(s): {', '.join(sorted(unknown))}."})
        if any(not isinstance(item, bool) for item in value.values()):
            raise serializers.ValidationError({field: "Checklist values must be true or false."})
        return value

    def validate_vehicle_condition_checklist(self, value):
        return self._validate_checklist(value, HANDOVER_CONDITION_CHECKLIST, "vehicle_condition_checklist")

    def validate_keys_documents_checklist(self, value):
        return self._validate_checklist(value, HANDOVER_KEYS_DOCUMENTS_CHECKLIST, "keys_documents_checklist")

    def validate_supporting_evidence(self, file):
        if file.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("Supporting evidence must be 10 MB or smaller.")
        content_type = getattr(file, "content_type", "")
        allowed = {"image/jpeg", "image/png", "application/pdf"}
        if content_type not in allowed:
            raise serializers.ValidationError("Evidence must be a JPEG, PNG, or PDF file.")
        head = file.read(8)
        file.seek(0)
        if content_type == "application/pdf":
            if not head.startswith(b"%PDF-"):
                raise serializers.ValidationError("The uploaded file is not a valid PDF.")
        else:
            try:
                image = Image.open(file)
                expected = "JPEG" if content_type == "image/jpeg" else "PNG"
                if image.format != expected:
                    raise serializers.ValidationError("Evidence image type does not match its content.")
                if image.width < 1 or image.height < 1 or image.width > 12000 or image.height > 12000 or image.width * image.height > 50_000_000:
                    raise serializers.ValidationError("Evidence image dimensions are not allowed.")
                image.verify()
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
                raise serializers.ValidationError("The uploaded evidence image is invalid.")
            finally:
                file.seek(0)
        return file

    def validate(self, attrs):
        if self.instance and "sale_reference" in attrs:
            raise serializers.ValidationError({"sale_reference": "A handover cannot be moved to another sale."})
        evidence = attrs.get("supporting_evidence")
        if evidence:
            attrs["evidence_content_type"] = evidence.content_type
        return attrs


class HandoverApprovalSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.SerializerMethodField()

    class Meta:
        model = HandoverApproval
        fields = ("reviewer_name", "reviewer_role", "decision", "status_before", "status_after", "comments", "created_at")
        read_only_fields = fields

    def get_reviewer_name(self, obj):
        return obj.reviewer.get_full_name().strip() or obj.reviewer.username


class HandoverDecisionSerializer(serializers.Serializer):
    comments = serializers.CharField(max_length=2000, required=True, allow_blank=False, trim_whitespace=True)


class HandoverSerializer(serializers.ModelSerializer):
    sale_reference = serializers.CharField(source="sale.reference", read_only=True)
    customer_id = serializers.IntegerField(read_only=True)
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    vehicle_reference = serializers.CharField(source="vehicle.reference", read_only=True)
    vehicle_name = serializers.SerializerMethodField()
    prepared_by_name = serializers.CharField(source="prepared_by.username", read_only=True)
    finalized_by_name = serializers.CharField(source="finalized_by.username", read_only=True, allow_null=True)
    md_approved_by_name = serializers.CharField(source="md_approved_by.username", read_only=True, allow_null=True)
    md_approved_at = serializers.DateTimeField(read_only=True)
    ceo_approved_by_name = serializers.CharField(source="ceo_approved_by.username", read_only=True, allow_null=True)
    ceo_approved_at = serializers.DateTimeField(read_only=True)
    approval_history = HandoverApprovalSerializer(many=True, read_only=True)
    evidence_attached = serializers.SerializerMethodField()
    evidence_url = serializers.SerializerMethodField()
    financial_summary = serializers.SerializerMethodField()
    document_receipt = serializers.SerializerMethodField()
    commission_eligible = serializers.BooleanField(read_only=True)

    class Meta:
        model = Handover
        fields = ("id", "reference", "sale_reference", "customer_id", "customer_name", "vehicle_reference", "vehicle_name",
                  "status", "delivery_date", "vehicle_condition_checklist", "keys_documents_checklist", "customer_acknowledgement",
                  "customer_acknowledged_at", "evidence_attached", "evidence_url", "internal_notes", "prepared_by_name",
                  "created_at", "updated_at", "md_approved_by_name", "md_approved_at", "ceo_approved_by_name", "ceo_approved_at",
                  "approval_history", "finalized_by_name", "finalized_at", "financial_summary", "commission_eligible", "document_receipt")
        read_only_fields = fields

    def get_vehicle_name(self, obj):
        return f"{obj.vehicle.manufacture_year} {obj.vehicle.make} {obj.vehicle.model} {obj.vehicle.variant}".strip()

    def get_evidence_attached(self, obj):
        return bool(obj.supporting_evidence)

    def get_evidence_url(self, obj):
        return f"/api/staff/handovers/{obj.reference}/evidence/" if obj.supporting_evidence else None

    def get_financial_summary(self, obj):
        summary = sale_payment_summary(obj.sale)
        summary["balance_review_required"] = summary["outstanding_balance_lkr"] > 0
        return summary

    def get_document_receipt(self, obj):
        receipt = getattr(obj, "document_receipt", None)
        if receipt is None:
            return None
        return {
            "reference": receipt.reference,
            "issued_at": receipt.issued_at,
            "issued_by_name": receipt.issued_by_name,
            "items_handed_over": receipt.items_handed_over,
            "download_url": f"/api/staff/handovers/{obj.reference}/document-receipt/{receipt.reference}/pdf/",
        }


class HandoverDocumentReceiptSerializer(serializers.ModelSerializer):
    issued_by_name = serializers.CharField(read_only=True)

    class Meta:
        model = HandoverDocumentReceipt
        fields = ("reference", "sale_reference", "customer_name", "vehicle_reference", "vehicle_name",
                  "delivery_date", "items_handed_over", "customer_acknowledgement", "issued_by_name", "issued_at")
        read_only_fields = fields

class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ("id", "title", "message", "target_url", "created_at", "read_at", "is_read")
        read_only_fields = fields

    def get_is_read(self, obj):
        return obj.read_at is not None


class NotificationReadSerializer(serializers.Serializer):
    is_read = serializers.BooleanField()
