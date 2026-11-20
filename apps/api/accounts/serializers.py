from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User, Vehicle, VehiclePhoto


class CurrentUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "role", "account_type")


class AccountSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "role", "account_type", "password", "is_active")
        read_only_fields = ("id",)

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class AccountUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, validators=[validate_password])

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "role", "account_type", "password", "is_active")

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


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
            "reference", "make", "model", "variant", "manufacture_year", "mileage_km",
            "fuel_type", "transmission", "color", "condition", "internal_identifier",
            "asking_price_lkr", "description", "visibility", "created_at", "updated_at", "photos",
        )
        read_only_fields = ("reference", "created_at", "updated_at", "photos")


class PublicVehicleSerializer(serializers.ModelSerializer):
    photos = VehiclePhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Vehicle
        fields = (
            "reference", "make", "model", "variant", "manufacture_year", "mileage_km",
            "fuel_type", "transmission", "color", "condition", "asking_price_lkr",
            "description", "photos",
        )
