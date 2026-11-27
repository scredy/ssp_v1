from django.contrib.auth.models import AbstractUser
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone
from uuid import uuid4
import secrets
from decimal import Decimal
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


def vehicle_reference():
    return f"SSP-{uuid4().hex[:12].upper()}"


def validate_manufacture_year(value):
    if value < 1886 or value > timezone.localdate().year + 1:
        raise ValidationError("Enter a valid manufacture year.")


def vehicle_photo_path(instance, filename):
    # Never use an uploaded filename as a path component.
    extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[instance.content_type]
    return f"vehicles/{instance.vehicle.reference}/{uuid4().hex}.{extension}"


@deconstructible
class PrivatePaymentEvidenceStorage(FileSystemStorage):
    """Payment evidence is stored outside the public MEDIA_ROOT tree."""
    def __init__(self):
        super().__init__(location=settings.PRIVATE_PAYMENT_EVIDENCE_ROOT, base_url=None)


def payment_evidence_path(instance, filename):
    extension = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}.get(instance.evidence_content_type, "bin")
    return f"payments/{instance.reference}/{uuid4().hex}.{extension}"


@deconstructible
class PrivateHandoverEvidenceStorage(FileSystemStorage):
    """Handover evidence is stored outside the public media tree."""
    def __init__(self):
        super().__init__(location=settings.PRIVATE_HANDOVER_EVIDENCE_ROOT, base_url=None)


def handover_evidence_path(instance, filename):
    extension = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}.get(instance.evidence_content_type, "bin")
    return f"handovers/{instance.reference}/{uuid4().hex}.{extension}"


HANDOVER_CONDITION_CHECKLIST = ("bodywork", "interior", "tyres", "lights", "odometer")
HANDOVER_KEYS_DOCUMENTS_CHECKLIST = ("keys", "registration_documents", "insurance_documents", "service_documents")


class User(AbstractUser):
    REQUIRED_FIELDS = ["email", "role"]

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        CEO = "ceo", "CEO"
        MANAGER = "manager", "MD/Manager"
        STAFF = "staff", "Staff"
        REP = "rep", "Rep"

    class AccountType(models.TextChoices):
        INTERNAL = "internal", "Internal"
        EXTERNAL = "external", "External"

    role = models.CharField(max_length=16, choices=Role.choices)
    account_type = models.CharField(max_length=16, choices=AccountType.choices, default=AccountType.INTERNAL)
    phone = models.CharField(max_length=32, blank=True, null=True)


class AuditEvent(models.Model):
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="audit_events")
    action = models.CharField(max_length=80)
    subject = models.CharField(max_length=150, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class Notification(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    deduplication_key = models.CharField(max_length=200)
    title = models.CharField(max_length=120)
    message = models.CharField(max_length=280)
    target_url = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [models.UniqueConstraint(fields=("recipient", "deduplication_key"), name="notification_recipient_event_unique")]
        indexes = [models.Index(fields=("recipient", "read_at", "-created_at"), name="notification_inbox_idx")]

    def __str__(self):
        return f"{self.title} for {self.recipient.username}"

class AccountActionToken(models.Model):
    class Kind(models.TextChoices):
        INVITATION = "invitation", "Invitation"
        PASSWORD_RESET = "password_reset", "Password reset"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="account_action_tokens")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="issued_account_action_tokens")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class Customer(models.Model):
    full_name = models.CharField(max_length=160)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    preferred_contact = models.CharField(max_length=16, choices=(("phone", "Phone"), ("email", "Email"), ("whatsapp", "WhatsApp")), default="phone")
    internal_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name", "id"]


class Enquiry(models.Model):
    class Kind(models.TextChoices):
        GENERAL = "general", "General enquiry"
        QUOTE = "quote", "Quote request"
        APPOINTMENT = "appointment", "Showroom appointment"
        TEST_DRIVE = "test_drive", "Test drive"

    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        SCHEDULED = "scheduled", "Scheduled"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class ConfirmationEmailStatus(models.TextChoices):
        NO_EMAIL = "no_email", "No email address"
        QUEUED = "queued", "Queued"
        SENDING = "sending", "Sending"
        SENT = "sent", "Accepted by mail service"
        FAILED = "failed", "Failed"

    reference = models.CharField(max_length=24, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="enquiries")
    vehicle = models.ForeignKey("Vehicle", on_delete=models.SET_NULL, null=True, blank=True, related_name="enquiries")
    vehicle_description = models.CharField(max_length=160, blank=True)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW, db_index=True)
    preferred_contact = models.CharField(max_length=16, choices=Customer._meta.get_field("preferred_contact").choices)
    requested_at = models.DateTimeField(null=True, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    confirmation_email_status = models.CharField(max_length=16, choices=ConfirmationEmailStatus.choices, blank=True, default="")
    confirmation_email_schedule = models.DateTimeField(null=True, blank=True)
    confirmation_email_is_update = models.BooleanField(default=False)
    confirmation_email_recipient = models.EmailField(blank=True)
    confirmation_email_sent_at = models.DateTimeField(null=True, blank=True)
    confirmation_email_error = models.CharField(max_length=500, blank=True)
    message = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    idempotency_key = models.CharField(max_length=64, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"ENQ-{uuid4().hex[:12].upper()}"
        return super().save(*args, **kwargs)


class RepresentativeProfile(models.Model):
    class BusinessStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    reference = models.CharField(max_length=20, unique=True, editable=False)
    user = models.OneToOneField("User", on_delete=models.PROTECT, related_name="representative_profile")
    business_status = models.CharField(max_length=10, choices=BusinessStatus.choices, default=BusinessStatus.ACTIVE, db_index=True)
    created_by = models.ForeignKey("User", on_delete=models.SET_NULL, null=True, blank=True, related_name="created_representative_profiles")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__first_name", "user__last_name", "user__username"]

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"REP-{uuid4().hex[:10].upper()}"
        return super().save(*args, **kwargs)


class CommissionRule(models.Model):
    """Stores rule configuration only; commission calculations are outside this slice."""

    key = models.SlugField(unique=True)
    value = models.JSONField(default=dict)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    updated_at = models.DateTimeField(auto_now=True)


class Vehicle(models.Model):
    class FuelType(models.TextChoices):
        PETROL = "petrol", "Petrol"
        DIESEL = "diesel", "Diesel"
        HYBRID = "hybrid", "Hybrid"
        ELECTRIC = "electric", "Electric"
        OTHER = "other", "Other"

    class Transmission(models.TextChoices):
        AUTOMATIC = "automatic", "Automatic"
        MANUAL = "manual", "Manual"
        OTHER = "other", "Other"

    class Condition(models.TextChoices):
        NEW = "new", "New"
        USED = "used", "Used"
        RECONDITIONED = "reconditioned", "Reconditioned"

    class Visibility(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        RESERVED = "reserved", "Reserved"
        SOLD = "sold", "Sold"
        HANDED_OVER = "handed_over", "Handed Over"
        ARCHIVED = "archived", "Archived"

    reference = models.CharField(max_length=16, unique=True, default=vehicle_reference, editable=False)
    make = models.CharField(max_length=80)
    model = models.CharField(max_length=100)
    variant = models.CharField(max_length=120, blank=True)
    manufacture_year = models.PositiveSmallIntegerField(validators=[validate_manufacture_year])
    mileage_km = models.PositiveIntegerField(validators=[MinValueValidator(0), MaxValueValidator(2_000_000)])
    fuel_type = models.CharField(max_length=16, choices=FuelType.choices)
    transmission = models.CharField(max_length=16, choices=Transmission.choices)
    color = models.CharField(max_length=50)
    condition = models.CharField(max_length=20, choices=Condition.choices)
    internal_identifier = models.CharField(max_length=100, unique=True, help_text="Private chassis, VIN, or stock identifier")
    asking_price_lkr = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0.01)])
    description = models.TextField(blank=True)
    visibility = models.CharField(max_length=12, choices=Visibility.choices, default=Visibility.DRAFT, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.AVAILABLE, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self._state.adding:
            if self.status != self.Status.AVAILABLE:
                raise ValidationError({"status": "New vehicles must start as available."})
        else:
            previous = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            allowed = {(self.Status.AVAILABLE, self.Status.ARCHIVED),
                       (self.Status.ARCHIVED, self.Status.AVAILABLE),
                       (self.Status.AVAILABLE, self.Status.RESERVED),
                       (self.Status.RESERVED, self.Status.AVAILABLE),
                       (self.Status.AVAILABLE, self.Status.SOLD),
                       (self.Status.RESERVED, self.Status.SOLD),
                       (self.Status.SOLD, self.Status.HANDED_OVER)}
            if previous and previous != self.status and (previous, self.status) not in allowed:
                raise ValidationError({"status": "This vehicle lifecycle transition is not enabled."})
        return super().save(*args, **kwargs)


class Reservation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RELEASED = "released", "Released"
        CONVERTED = "converted", "Converted to sale"

    reference = models.CharField(max_length=24, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="reservations")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="reservations")
    representative = models.ForeignKey(RepresentativeProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="reservations")
    responsible_staff = models.ForeignKey(User, on_delete=models.PROTECT, related_name="responsible_reservations")
    agreed_price_lkr = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    advance_amount_lkr = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    release_reason = models.TextField(blank=True)
    released_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="released_reservations")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["vehicle"], condition=models.Q(status="active"), name="unique_active_reservation_per_vehicle"),
            models.CheckConstraint(condition=models.Q(agreed_price_lkr__gt=0), name="reservation_agreed_price_positive"),
            models.CheckConstraint(condition=models.Q(advance_amount_lkr__gte=0), name="reservation_advance_nonnegative"),
        ]

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"RSV-{uuid4().hex[:12].upper()}"
        return super().save(*args, **kwargs)


class VehiclePhoto(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="photos")
    image = models.FileField(upload_to=vehicle_photo_path)
    content_type = models.CharField(max_length=30)
    content_sha256 = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [models.UniqueConstraint(
            fields=("vehicle", "content_sha256"), name="unique_vehicle_photo_content"
        )]


class Sale(models.Model):
    class SaleType(models.TextChoices):
        DIRECT = "direct", "Direct"
        IMPORT = "import", "Import"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        CONFIRMED = "confirmed", "Confirmed"

    reference = models.CharField(max_length=24, unique=True, editable=False)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="sales")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="sales")
    representative = models.ForeignKey(RepresentativeProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="sales")
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, null=True, blank=True, related_name="sales")
    import_order = models.ForeignKey("ImportOrder", on_delete=models.PROTECT, null=True, blank=True, related_name="sales")
    sale_type = models.CharField(max_length=10, choices=SaleType.choices, default=SaleType.DIRECT)
    agreed_price_lkr = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    sale_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_sales")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["vehicle"], condition=models.Q(status="confirmed"), name="unique_confirmed_sale_per_vehicle"),
            models.UniqueConstraint(fields=["reservation"], condition=models.Q(reservation__isnull=False), name="unique_sale_per_reservation"),
            models.UniqueConstraint(fields=["import_order"], condition=models.Q(import_order__isnull=False), name="unique_sale_per_import_order"),
            models.CheckConstraint(condition=models.Q(agreed_price_lkr__gt=0), name="sale_agreed_price_positive"),
        ]

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"SAL-{uuid4().hex[:12].upper()}"
        return super().save(*args, **kwargs)


class HandoverQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if self.filter(status="finalized").exists():
            raise ValidationError("Finalized handovers are immutable.")
        return super().update(**kwargs)

    def delete(self):
        if self.exists():
            raise ValidationError("Handover history must be preserved.")
        return 0, {}


class Handover(models.Model):
    class Status(models.TextChoices):
        PREPARING = "preparing", "Preparing"
        PENDING_MD_REVIEW = "pending_md_review", "Pending MD Review"
        PENDING_CEO_APPROVAL = "pending_ceo_approval", "Pending CEO Approval"
        CEO_APPROVED = "ceo_approved", "CEO Approved"
        FINALIZED = "finalized", "Finalized"

    reference = models.CharField(max_length=24, unique=True, editable=False)
    sale = models.OneToOneField(Sale, on_delete=models.PROTECT, related_name="handover")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="handovers")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="handovers")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PREPARING, db_index=True)
    delivery_date = models.DateField(null=True, blank=True)
    vehicle_condition_checklist = models.JSONField(default=dict, blank=True)
    keys_documents_checklist = models.JSONField(default=dict, blank=True)
    customer_acknowledgement = models.TextField(blank=True)
    customer_acknowledged_at = models.DateTimeField(null=True, blank=True)
    supporting_evidence = models.FileField(storage=PrivateHandoverEvidenceStorage(), upload_to=handover_evidence_path, blank=True)
    evidence_content_type = models.CharField(max_length=32, blank=True, default="")
    internal_notes = models.TextField(blank=True)
    prepared_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="prepared_handovers")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    md_approved_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="md_approved_handovers")
    md_approved_at = models.DateTimeField(null=True, blank=True)
    ceo_approved_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="ceo_approved_handovers")
    ceo_approved_at = models.DateTimeField(null=True, blank=True)
    finalized_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="finalized_handovers")
    finalized_at = models.DateTimeField(null=True, blank=True)

    objects = HandoverQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(status="finalized", finalized_by__isnull=False, finalized_at__isnull=False) |
                                   (~models.Q(status="finalized") & models.Q(finalized_by__isnull=True, finalized_at__isnull=True)),
                                   name="handover_finalization_audit_required"),
        ]

    @property
    def commission_eligible(self):
        return self.status == self.Status.FINALIZED and self.finalized_by_id is not None and self.finalized_at is not None

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"HND-{uuid4().hex[:12].upper()}"
        if self.sale_id and self.sale.status != Sale.Status.CONFIRMED:
            raise ValidationError({"sale": "Only a confirmed sale can have a handover."})
        if self.status == self.Status.FINALIZED:
            condition_complete = all((self.vehicle_condition_checklist or {}).get(key) is True for key in HANDOVER_CONDITION_CHECKLIST)
            documents_complete = all((self.keys_documents_checklist or {}).get(key) is True for key in HANDOVER_KEYS_DOCUMENTS_CHECKLIST)
            if not self.delivery_date or not condition_complete or not documents_complete or not self.customer_acknowledgement.strip() or not self.customer_acknowledged_at:
                raise ValidationError("A finalized handover requires a delivery date, complete checklists, and recorded customer acknowledgement.")
            if not self.finalized_by_id or not self.finalized_at:
                raise ValidationError("Finalization must record the responsible manager and timestamp.")
        if self._state.adding:
            if self.customer_id != self.sale.customer_id or self.vehicle_id != self.sale.vehicle_id:
                raise ValidationError("Handover customer and vehicle must match the linked sale.")
        else:
            previous = type(self).objects.get(pk=self.pk)
            immutable_fields = ("sale_id", "customer_id", "vehicle_id", "delivery_date", "vehicle_condition_checklist",
                "keys_documents_checklist", "customer_acknowledgement", "customer_acknowledged_at", "supporting_evidence",
                "evidence_content_type", "internal_notes", "prepared_by_id", "created_at")
            if previous.status == self.Status.FINALIZED and (
                any(getattr(previous, field) != getattr(self, field) for field in immutable_fields) or
                previous.finalized_by_id != self.finalized_by_id or previous.finalized_at != self.finalized_at or
                self.status != self.Status.FINALIZED
            ):
                raise ValidationError("Finalized handovers are immutable and cannot be reversed.")
            material_fields = ("delivery_date", "vehicle_condition_checklist", "keys_documents_checklist",
                               "customer_acknowledgement", "customer_acknowledged_at", "supporting_evidence",
                               "evidence_content_type", "internal_notes")
            if previous.status in {self.Status.PENDING_CEO_APPROVAL, self.Status.CEO_APPROVED} and any(
                getattr(previous, field) != getattr(self, field) for field in material_fields
            ):
                raise ValidationError("Preparation data cannot change while an MD or CEO approval is active.")
            if previous.status != self.status:
                allowed = ((previous.status == self.Status.PREPARING and self.status == self.Status.PENDING_MD_REVIEW) or
                           (previous.status == self.Status.PENDING_MD_REVIEW and self.status in {self.Status.PREPARING, self.Status.PENDING_CEO_APPROVAL}) or
                           (previous.status == self.Status.PENDING_CEO_APPROVAL and self.status in {self.Status.PENDING_MD_REVIEW, self.Status.CEO_APPROVED}) or
                           (previous.status == self.Status.CEO_APPROVED and self.status == self.Status.PREPARING) or
                           (previous.status == self.Status.CEO_APPROVED and self.status == self.Status.FINALIZED and
                            self.md_approved_by_id and self.md_approved_at and self.ceo_approved_by_id and self.ceo_approved_at and
                            self.finalized_by_id and self.finalized_at))
                if not allowed:
                    raise ValidationError("This handover status transition is not allowed.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Handover history must be preserved.")


class HandoverApprovalQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Handover approval history is append-only.")

    def delete(self):
        if self.exists():
            raise ValidationError("Handover approval history is append-only.")
        return 0, {"accounts.HandoverApproval": 0}


class HandoverApproval(models.Model):
    class Decision(models.TextChoices):
        SUBMITTED_FOR_MD = "submitted_for_md", "Submitted for MD review"
        MD_APPROVED = "md_approved", "Approved by MD"
        CEO_APPROVED = "ceo_approved", "Approved by CEO"
        MD_RETURNED = "md_returned", "Returned to Staff"
        CEO_RETURNED = "ceo_returned", "Returned to MD"
        FINALIZED = "finalized", "Finalized by MD"

    handover = models.ForeignKey(Handover, on_delete=models.PROTECT, related_name="approval_history")
    reviewer = models.ForeignKey(User, on_delete=models.PROTECT, related_name="handover_approval_decisions")
    reviewer_role = models.CharField(max_length=16)
    decision = models.CharField(max_length=32, choices=Decision.choices)
    status_before = models.CharField(max_length=20)
    status_after = models.CharField(max_length=20)
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    objects = HandoverApprovalQuerySet.as_manager()

    class Meta:
        ordering = ["created_at", "pk"]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Handover approval history is append-only.")
        if self.reviewer_id and self.reviewer_role != self.reviewer.role:
            raise ValidationError("Reviewer role must match the role at the time of the decision.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Handover approval history is append-only.")


class HandoverDocumentReceipt(models.Model):
    """Immutable customer acknowledgment of documents delivered with a vehicle."""

    reference = models.CharField(max_length=24, unique=True, editable=False)
    handover = models.OneToOneField(Handover, on_delete=models.PROTECT, related_name="document_receipt")
    sale_reference = models.CharField(max_length=24)
    customer_name = models.CharField(max_length=160)
    vehicle_reference = models.CharField(max_length=16)
    vehicle_name = models.CharField(max_length=320)
    delivery_date = models.DateField()
    items_handed_over = models.JSONField(default=list)
    customer_acknowledgement = models.TextField(blank=True)
    issued_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="issued_handover_document_receipts")
    issued_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-issued_at"]

    @property
    def issued_by_name(self):
        return self.issued_by.get_full_name().strip() or self.issued_by.username

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"DRC-{uuid4().hex[:12].upper()}"
        if not self._state.adding:
            raise ValidationError("Issued document receipts are immutable.")
        if self.handover_id and self.handover.status != Handover.Status.FINALIZED:
            raise ValidationError("A document receipt can only be issued for a finalized handover.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Issued document receipt history must be preserved.")


class CommissionLedgerEntryQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Commission ledger entries are immutable.")

    def delete(self):
        if self.exists():
            raise ValidationError("Commission ledger history must be preserved.")
        return 0, {}


class CommissionLedgerEntry(models.Model):
    """Immutable handover snapshot with an auditable payout state machine."""

    sale = models.OneToOneField(Sale, on_delete=models.PROTECT, related_name="commission_entry")
    handover = models.OneToOneField(Handover, on_delete=models.PROTECT, related_name="commission_entry")
    recipient = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="commission_entries")
    sale_price_lkr = models.DecimalField(max_digits=14, decimal_places=2)
    commission_rate_percent = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    commission_amount_lkr = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    policy_snapshot = models.JSONField(default=dict)
    status = models.CharField(max_length=16, default="pending", choices=[
        ("pending", "Pending"), ("approved", "Approved"), ("paid", "Paid"), ("reversed", "Reversed"),
    ])
    approved_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="approved_commission_entries")
    approved_at = models.DateTimeField(null=True, blank=True)
    payout_reference = models.CharField(max_length=100, blank=True, default="")
    payout_date = models.DateField(null=True, blank=True)
    payout_amount_lkr = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    paid_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="paid_commission_entries")
    paid_at = models.DateTimeField(null=True, blank=True)
    reversal_reason = models.TextField(blank=True, default="")
    reversed_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_commission_entries")
    reversed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_commission_entries")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = CommissionLedgerEntryQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["payout_reference"], condition=~models.Q(payout_reference=""),
                                                name="commission_payout_reference_unique")]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            previous = type(self).objects.get(pk=self.pk)
            immutable = ("sale_id", "handover_id", "recipient_id", "sale_price_lkr", "commission_rate_percent",
                         "commission_amount_lkr", "policy_snapshot", "created_by_id", "created_at")
            if any(getattr(previous, field) != getattr(self, field) for field in immutable):
                raise ValidationError("Finalized sale and commission snapshots are immutable.")
            allowed_next = {"pending": {"approved", "reversed"}, "approved": {"paid", "reversed"},
                            "paid": {"reversed"}, "reversed": set()}
            if self.status not in allowed_next.get(previous.status, set()):
                raise ValidationError("Commission ledger status can only move through valid payout transitions.")
            if self.status == "approved" and (not self.approved_by_id or not self.approved_at or not self.recipient_id or self.commission_amount_lkr is None):
                raise ValidationError("A rated commission assigned to a Rep is required for approval.")
            if self.status == "paid" and (not self.payout_reference or not self.payout_date or not self.payout_amount_lkr or
                    self.payout_amount_lkr != self.commission_amount_lkr or not self.paid_by_id or not self.paid_at):
                raise ValidationError("A payout must include a reference, date, full commission amount, and paying actor.")
            if self.status == "reversed" and (not self.reversal_reason.strip() or not self.reversed_by_id or not self.reversed_at):
                raise ValidationError("A reversal requires a reason and recording actor.")
            if previous.status == "paid" and self.status == "reversed" and any(
                    getattr(previous, field) != getattr(self, field) for field in
                    ("payout_reference", "payout_date", "payout_amount_lkr", "paid_by_id", "paid_at")):
                raise ValidationError("Paid payout details must remain unchanged when reversed.")
            return super().save(*args, **kwargs)
        if self.handover_id and not self.handover.commission_eligible:
            raise ValidationError("Commission can only be recorded after a finalized handover.")
        if self.handover_id and self.sale_id != self.handover.sale_id:
            raise ValidationError("The ledger sale must match the finalized handover sale.")
        if self.sale_id and (self.sale.status != Sale.Status.CONFIRMED or self.sale.agreed_price_lkr != self.sale_price_lkr):
            raise ValidationError("The ledger must snapshot the confirmed sale price.")
        expected_recipient = self.sale.representative.user_id if self.sale_id and self.sale.representative_id else None
        if self.recipient_id != expected_recipient:
            raise ValidationError("A commission recipient must come from the sale's assigned representative.")
        if self.status != "pending" or ((self.commission_rate_percent is None) != (self.commission_amount_lkr is None)):
            raise ValidationError("New ledger entries must start pending and require both rate and amount or neither.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Commission ledger history must be preserved.")


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        CHEQUE = "cheque", "Cheque"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"
        REVERSED = "reversed", "Reversed"

    class PaymentType(models.TextChoices):
        UNSPECIFIED = "unspecified", "Unspecified (historical)"
        ADVANCE = "advance", "Advance"
        PARTIAL = "partial", "Partial Payment"
        FINAL = "final", "Final Payment"
        FINANCE_SETTLEMENT = "finance_settlement", "Finance Settlement"

    reference = models.CharField(max_length=24, unique=True, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, null=True, blank=True, related_name="payments")
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, null=True, blank=True, related_name="payments")
    import_order = models.ForeignKey("ImportOrder", on_delete=models.PROTECT, null=True, blank=True, related_name="payments")
    amount_lkr = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    payment_type = models.CharField(max_length=24, choices=PaymentType.choices, default=PaymentType.PARTIAL)
    funds_cleared = models.BooleanField(default=False)
    method = models.CharField(max_length=16, choices=Method.choices)
    transaction_reference = models.CharField(max_length=120, blank=True, default="")
    idempotency_key = models.CharField(max_length=64, blank=True, default="")
    payment_date = models.DateField(default=timezone.localdate)
    evidence = models.FileField(storage=PrivatePaymentEvidenceStorage(), upload_to=payment_evidence_path, blank=True)
    evidence_content_type = models.CharField(max_length=32, blank=True, default="")
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="recorded_payments")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    verified_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="verified_payments")
    verified_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="rejected_payments")
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    reversed_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_payments")
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversal_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=(
                models.Q(sale__isnull=False, reservation__isnull=True, import_order__isnull=True) |
                models.Q(sale__isnull=True, reservation__isnull=False, import_order__isnull=True) |
                models.Q(sale__isnull=True, reservation__isnull=True, import_order__isnull=False)),
                name="payment_exactly_one_parent"),
            models.CheckConstraint(condition=models.Q(amount_lkr__gt=0), name="payment_amount_positive"),
            models.UniqueConstraint(fields=["transaction_reference"], condition=~models.Q(transaction_reference=""), name="payment_transaction_reference_unique"),
            models.UniqueConstraint(fields=["idempotency_key"], condition=~models.Q(idempotency_key=""), name="payment_idempotency_key_unique"),
        ]

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"PAY-{uuid4().hex[:12].upper()}"
        return super().save(*args, **kwargs)


class ImportOrder(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        BOOKING_CONFIRMED = "booking_confirmed", "Booking Confirmed"
        LC_OPENED = "lc_opened", "LC Opened"
        BL_ISSUED = "bl_issued", "BL Issued"
        SHIPPING = "shipping", "Shipping"
        ARRIVED = "arrived", "Arrived"
        CUSTOMS_CLEARANCE = "customs_clearance", "Customs Clearance"
        READY_FOR_COLLECTION = "ready_for_collection", "Ready for Collection"
        HANDED_OVER = "handed_over", "Handed Over"

    reference = models.CharField(max_length=24, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="import_orders")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, blank=True, related_name="import_orders")
    agreed_price_lkr = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    vehicle_description = models.CharField(max_length=240)
    vehicle_details = models.TextField(blank=True)
    country_of_origin = models.CharField(max_length=100)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.NEW, db_index=True)
    shipping_information = models.TextField(blank=True)
    estimated_arrival = models.DateField(null=True, blank=True)
    internal_notes = models.TextField(blank=True)
    customer_updates = models.TextField(blank=True)
    responsible_staff = models.ForeignKey(User, on_delete=models.PROTECT, related_name="responsible_import_orders")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(agreed_price_lkr__isnull=True) |
                          models.Q(agreed_price_lkr__gt=0),
                name="import_agreed_price_positive",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"IMP-{uuid4().hex[:12].upper()}"
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Import records are retained for operational history.")


class Quotation(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"
        EXPIRED = "expired", "Expired"
        VOIDED = "voided", "Voided"

    class FinanceTerm(models.TextChoices):
        THREE_YEARS = "36m", "3 years"
        FIVE_YEARS = "60m", "5 years"
        SIX_YEARS = "72m", "6 years"
        SPEED_DRAFT = "od", "Speed Draft / OD"

    reference = models.CharField(max_length=24, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="quotations")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, null=True, blank=True, related_name="quotations")
    import_order = models.ForeignKey(ImportOrder, on_delete=models.PROTECT, null=True, blank=True, related_name="quotations")
    responsible_staff = models.ForeignKey(User, on_delete=models.PROTECT, related_name="responsible_quotations")
    vehicle_description = models.CharField(max_length=240)
    vehicle_specifications = models.JSONField(default=dict, blank=True)
    vehicle_selling_price_lkr = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    additional_charges_lkr = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00"))])
    discount_lkr = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00"))])
    quotation_total_lkr = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    issue_date = models.DateField(default=timezone.localdate)
    expiry_date = models.DateField()
    internal_notes = models.TextField(blank=True)
    customer_terms = models.TextField(blank=True)
    finance_term = models.CharField(max_length=8, choices=FinanceTerm.choices, blank=True, default="")
    finance_terms = models.JSONField(default=list, blank=True)
    finance_down_payment_lkr = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00"))])
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    issued_snapshot = models.JSONField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="voided_quotations")
    void_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(quotation_total_lkr__gte=0), name="quotation_total_nonnegative"),
            models.CheckConstraint(condition=models.Q(additional_charges_lkr__gte=0), name="quotation_charges_nonnegative"),
            models.CheckConstraint(condition=models.Q(discount_lkr__gte=0), name="quotation_discount_nonnegative"),
            models.CheckConstraint(condition=models.Q(finance_down_payment_lkr__gte=0), name="quotation_downpayment_nonnegative"),
            models.CheckConstraint(condition=models.Q(expiry_date__gte=models.F("issue_date")), name="quotation_expiry_after_issue"),
        ]

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"QUO-{uuid4().hex[:12].upper()}"
        self.quotation_total_lkr = self.vehicle_selling_price_lkr + self.additional_charges_lkr - self.discount_lkr
        if self.quotation_total_lkr < 0:
            raise ValidationError({"discount_lkr": "Discount cannot exceed the price and additional charges."})
        if self.finance_down_payment_lkr > self.vehicle_selling_price_lkr:
            raise ValidationError({"finance_down_payment_lkr": "Down payment cannot exceed the vehicle selling price."})
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            if previous.status != self.Status.DRAFT:
                fields = ("customer_id", "vehicle_id", "import_order_id", "responsible_staff_id", "vehicle_description",
                          "vehicle_specifications", "vehicle_selling_price_lkr", "additional_charges_lkr", "discount_lkr",
                          "quotation_total_lkr", "issue_date", "expiry_date", "internal_notes", "customer_terms",
                          "finance_term", "finance_terms", "finance_down_payment_lkr", "issued_snapshot", "issued_at")
                if any(getattr(previous, field) != getattr(self, field) for field in fields):
                    raise ValidationError("Issued quotation details are immutable.")
                if previous.status != self.status:
                    allowed = ((previous.status == self.Status.DRAFT and self.status == self.Status.ISSUED and self.issued_snapshot and self.issued_at) or
                               (previous.status == self.Status.ISSUED and self.status in (self.Status.EXPIRED, self.Status.VOIDED)) or
                               (previous.status == self.Status.EXPIRED and self.status == self.Status.VOIDED))
                    if not allowed:
                        raise ValidationError("This quotation status transition is not allowed.")
        return super().save(*args, **kwargs)


class ImportMilestoneQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Import milestone history is append-only.")

    def delete(self):
        raise ValidationError("Import milestone history is append-only.")


class ImportMilestone(models.Model):
    class Kind(models.TextChoices):
        BOOKING_CONFIRMED = "booking_confirmed", "Booking Confirmed"
        PAYMENT_VERIFIED = "payment_verified", "Advance / Payment Verified"
        LC_OPENED = "lc_opened", "LC Opened"
        BL_ISSUED = "bl_issued", "BL Issued"
        SHIPPING = "shipping", "Shipping"
        ARRIVAL = "arrival", "Arrival"
        CUSTOMS_CLEARANCE = "customs_clearance", "Customs Clearance"
        READY_FOR_COLLECTION = "ready_for_collection", "Ready for Collection"
        FINALIZED_HANDOVER = "finalized_handover", "Finalized Handover"

    import_order = models.ForeignKey(ImportOrder, on_delete=models.PROTECT, related_name="milestones")
    kind = models.CharField(max_length=32, choices=Kind.choices)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    actor = models.ForeignKey(User, on_delete=models.PROTECT, related_name="import_milestones")
    customer_description = models.CharField(max_length=500)
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, null=True, blank=True, related_name="import_milestones")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImportMilestoneQuerySet.as_manager()

    class Meta:
        ordering = ["occurred_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["import_order", "kind"], name="unique_import_milestone_kind"),
            models.UniqueConstraint(fields=["payment"], condition=models.Q(payment__isnull=False), name="payment_one_import_milestone"),
            models.CheckConstraint(condition=(models.Q(kind="payment_verified", payment__isnull=False) |
                                               (~models.Q(kind="payment_verified") & models.Q(payment__isnull=True))),
                                   name="import_payment_milestone_requires_payment"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Import milestone history is append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Import milestone history is append-only.")


class BLApprovalRequestQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("BL approval history must be processed through its decision workflow.")

    def delete(self):
        raise ValidationError("BL approval request history is retained.")


class BLApprovalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    reference = models.CharField(max_length=24, unique=True, editable=False)
    import_order = models.ForeignKey(ImportOrder, on_delete=models.PROTECT, related_name="bl_requests")
    requested_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="bl_requests_submitted")
    request_note = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    requested_at = models.DateTimeField(auto_now_add=True, db_index=True)
    decided_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="bl_requests_decided")
    decided_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-requested_at"]
        constraints = [models.UniqueConstraint(fields=["import_order"], condition=models.Q(status="pending"), name="one_pending_bl_request_per_import")]

    objects = BLApprovalRequestQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"BLR-{uuid4().hex[:12].upper()}"
        if self._state.adding:
            if self.status != self.Status.PENDING or self.decided_by_id or self.decided_at:
                raise ValidationError("BL requests must be created as pending requests.")
        else:
            old = type(self).objects.get(pk=self.pk)
            if old.status != self.Status.PENDING or self.status not in {self.Status.APPROVED, self.Status.REJECTED}:
                raise ValidationError("Processed BL approval requests cannot be changed again.")
        if self.status in {self.Status.APPROVED, self.Status.REJECTED} and (not self.decided_by_id or not self.decided_at):
            raise ValidationError("BL approval decisions require an actor and timestamp.")
        if self.status == self.Status.REJECTED and not self.rejection_reason.strip():
            raise ValidationError("Rejecting a BL request requires a reason.")
        if self.status == self.Status.APPROVED and self.rejection_reason:
            raise ValidationError("Approved BL requests cannot have a rejection reason.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("BL approval request history is retained.")


class ImportTrackingAccess(models.Model):
    import_order = models.OneToOneField(ImportOrder, on_delete=models.PROTECT, related_name="tracking_access")
    tracking_reference = models.CharField(max_length=32, unique=True, editable=False)
    pin_hash = models.CharField(max_length=128)
    pin_changed_at = models.DateTimeField(default=timezone.now)
    active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.tracking_reference:
            self.tracking_reference = f"TRK-{uuid4().hex[:14].upper()}"
        return super().save(*args, **kwargs)

    def issue_pin(self):
        pin = secrets.token_urlsafe(16)
        self.pin_hash = make_password(pin)
        self.pin_changed_at = timezone.now()
        self.active = True
        return pin

    def check_pin(self, pin):
        return self.active and check_password(pin, self.pin_hash)


class HandoverCompletionEmail(models.Model):
    class Status(models.TextChoices):
        NO_EMAIL = "no_email", "No email address"
        QUEUED = "queued", "Queued"
        SENDING = "sending", "Sending"
        SENT = "sent", "Accepted by mail service"
        FAILED = "failed", "Failed"

    handover = models.OneToOneField(
        Handover,
        on_delete=models.PROTECT,
        related_name="completion_email",
    )
    recipient = models.EmailField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
