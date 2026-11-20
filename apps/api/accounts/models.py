from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone
from uuid import uuid4


def vehicle_reference():
    return f"SSP-{uuid4().hex[:12].upper()}"


def validate_manufacture_year(value):
    if value < 1886 or value > timezone.localdate().year + 1:
        raise ValidationError("Enter a valid manufacture year.")


def vehicle_photo_path(instance, filename):
    # Never use an uploaded filename as a path component.
    extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[instance.content_type]
    return f"vehicles/{instance.vehicle.reference}/{uuid4().hex}.{extension}"


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


class AuditEvent(models.Model):
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="audit_events")
    action = models.CharField(max_length=80)
    subject = models.CharField(max_length=150, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class VehiclePhoto(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="photos")
    image = models.FileField(upload_to=vehicle_photo_path)
    content_type = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
