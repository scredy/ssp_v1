# Additive inventory schema. The initial account migration remains unchanged.
import accounts.models
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="Vehicle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reference", models.CharField(default=accounts.models.vehicle_reference, editable=False, max_length=16, unique=True)),
                ("make", models.CharField(max_length=80)),
                ("model", models.CharField(max_length=100)),
                ("variant", models.CharField(blank=True, max_length=120)),
                ("manufacture_year", models.PositiveSmallIntegerField(validators=[accounts.models.validate_manufacture_year])),
                ("mileage_km", models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(2000000)])),
                ("fuel_type", models.CharField(choices=[("petrol", "Petrol"), ("diesel", "Diesel"), ("hybrid", "Hybrid"), ("electric", "Electric"), ("other", "Other")], max_length=16)),
                ("transmission", models.CharField(choices=[("automatic", "Automatic"), ("manual", "Manual"), ("other", "Other")], max_length=16)),
                ("color", models.CharField(max_length=50)),
                ("condition", models.CharField(choices=[("new", "New"), ("used", "Used"), ("reconditioned", "Reconditioned")], max_length=20)),
                ("internal_identifier", models.CharField(help_text="Private chassis, VIN, or stock identifier", max_length=100, unique=True)),
                ("asking_price_lkr", models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(0.01)])),
                ("description", models.TextField(blank=True)),
                ("visibility", models.CharField(choices=[("draft", "Draft"), ("published", "Published")], db_index=True, default="draft", max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="VehiclePhoto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.FileField(upload_to=accounts.models.vehicle_photo_path)),
                ("content_type", models.CharField(max_length=30)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("vehicle", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="photos", to="accounts.vehicle")),
            ],
            options={"ordering": ["id"]},
        ),
    ]
