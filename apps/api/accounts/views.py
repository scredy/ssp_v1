from django.contrib.auth import authenticate, login, logout
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from decimal import Decimal, InvalidOperation
from PIL import Image, UnidentifiedImageError
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .models import AuditEvent, CommissionRule, User, Vehicle, VehiclePhoto
from .permissions import HasCapability, InventoryAccess
from .serializers import (AccountSerializer, AccountUpdateSerializer, CurrentUserSerializer,
                          PublicVehicleSerializer, StaffVehicleSerializer)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"detail": "CSRF cookie set"})


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    @method_decorator(csrf_protect)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request):
        username = request.data.get("username", "")
        password = request.data.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is None or not user.is_active:
            return Response({"detail": "Invalid username or password."}, status=status.HTTP_400_BAD_REQUEST)
        login(request, user)
        AuditEvent.objects.create(actor=user, action="auth.login", subject=user.username)
        return Response({"user": CurrentUserSerializer(user).data})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        AuditEvent.objects.create(actor=request.user, action="auth.logout", subject=request.user.username)
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(CurrentUserSerializer(request.user).data)


class AccountListCreateView(APIView):
    permission_classes = [HasCapability]
    required_capability = "accounts.manage"

    def get(self, request):
        return Response(CurrentUserSerializer(User.objects.order_by("username"), many=True).data)

    def post(self, request):
        serializer = AccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        AuditEvent.objects.create(actor=request.user, action="account.created", subject=user.username,
                                  details={"role": user.role, "account_type": user.account_type})
        return Response(CurrentUserSerializer(user).data, status=status.HTTP_201_CREATED)


class AccountDetailView(APIView):
    permission_classes = [HasCapability]
    required_capability = "accounts.manage"

    def get_object(self, account_id):
        return User.objects.get(pk=account_id)

    def patch(self, request, account_id):
        try:
            user = self.get_object(account_id)
        except User.DoesNotExist:
            return Response({"detail": "Account not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = AccountUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        AuditEvent.objects.create(actor=request.user, action="account.updated", subject=updated.username,
                                  details={"role": updated.role, "account_type": updated.account_type})
        return Response(CurrentUserSerializer(updated).data)


class RecentActivityView(APIView):
    permission_classes = [HasCapability]
    required_capability = "activity.view"

    def get(self, request):
        events = AuditEvent.objects.select_related("actor")[:50]
        return Response([{"action": e.action, "actor": e.actor.username if e.actor else None,
                          "subject": e.subject, "created_at": e.created_at} for e in events])


class ManagerOversightView(APIView):
    permission_classes = [HasCapability]
    required_capability = "manager_oversight.view"

    def get(self, request):
        events = AuditEvent.objects.filter(actor__role=User.Role.MANAGER).select_related("actor")[:50]
        return Response([{"action": e.action, "actor": e.actor.username if e.actor else None,
                          "subject": e.subject, "created_at": e.created_at} for e in events])


class CommissionRulesView(APIView):
    permission_classes = [HasCapability]
    required_capability = "commission_rules.manage"

    def get(self, request):
        return Response(list(CommissionRule.objects.values("key", "value", "updated_at")))

    def put(self, request, key):
        rule, _ = CommissionRule.objects.update_or_create(
            key=key, defaults={"value": request.data, "updated_by": request.user}
        )
        AuditEvent.objects.create(actor=request.user, action="commission_rule.updated", subject=key)
        return Response({"key": rule.key, "value": rule.value, "updated_at": rule.updated_at})


class ProtectedPlaceholderView(APIView):
    """Access-control examples for workflows deliberately not implemented in this slice."""

    required_capability = None

    def get(self, request):
        return Response({"detail": "Workflow is outside this authentication foundation."}, status=501)


class ManagerRepsView(ProtectedPlaceholderView):
    permission_classes = [HasCapability]
    required_capability = "reps.manage"


class ManagerSalesView(ProtectedPlaceholderView):
    permission_classes = [HasCapability]
    required_capability = "sales.oversight"


class StaffInventoryView(APIView):
    permission_classes = [InventoryAccess]

    def get(self, request):
        vehicles = Vehicle.objects.prefetch_related("photos").all()
        return Response(StaffVehicleSerializer(vehicles, many=True, context={"request": request}).data)

    def post(self, request):
        serializer = StaffVehicleSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        vehicle = serializer.save()
        AuditEvent.objects.create(actor=request.user, action="inventory.vehicle.created", subject=vehicle.reference)
        return Response(StaffVehicleSerializer(vehicle, context={"request": request}).data,
                        status=status.HTTP_201_CREATED)


class StaffInventoryDetailView(APIView):
    permission_classes = [InventoryAccess]

    def get_vehicle(self, reference):
        return get_object_or_404(Vehicle.objects.prefetch_related("photos"), reference=reference)

    def get(self, request, reference):
        return Response(StaffVehicleSerializer(self.get_vehicle(reference), context={"request": request}).data)

    def patch(self, request, reference):
        vehicle = self.get_vehicle(reference)
        serializer = StaffVehicleSerializer(vehicle, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        vehicle = serializer.save()
        AuditEvent.objects.create(actor=request.user, action="inventory.vehicle.updated", subject=vehicle.reference)
        return Response(StaffVehicleSerializer(vehicle, context={"request": request}).data)


class StaffVehiclePhotosView(APIView):
    permission_classes = [InventoryAccess]

    max_photo_bytes = 8 * 1024 * 1024
    max_photos = 10
    formats = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}

    def post(self, request, reference):
        vehicle = get_object_or_404(Vehicle, reference=reference)
        uploads = request.FILES.getlist("photos")
        if not uploads:
            raise ValidationError({"photos": "Select at least one image."})
        if len(uploads) + vehicle.photos.count() > self.max_photos:
            raise ValidationError({"photos": f"A vehicle can have at most {self.max_photos} photos."})
        validated = []
        for upload in uploads:
            if upload.size <= 0 or upload.size > self.max_photo_bytes:
                raise ValidationError({"photos": "Each image must be between 1 byte and 8 MB."})
            try:
                image = Image.open(upload)
                if image.format not in self.formats:
                    raise ValidationError({"photos": "Only JPEG, PNG, and WebP images are accepted."})
                width, height = image.size
                if width < 1 or height < 1 or width > 12000 or height > 12000 or width * height > 50_000_000:
                    raise ValidationError({"photos": "Image dimensions are too large."})
                image.verify()
                upload.seek(0)
                validated.append((upload, self.formats[image.format]))
            except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
                raise ValidationError({"photos": "An uploaded file is not a valid supported image."})
            finally:
                upload.seek(0)
        photos = [VehiclePhoto.objects.create(vehicle=vehicle, image=upload, content_type=content_type)
                  for upload, content_type in validated]
        AuditEvent.objects.create(actor=request.user, action="inventory.photos.uploaded", subject=vehicle.reference,
                                  details={"count": len(photos)})
        return Response(StaffVehicleSerializer(vehicle, context={"request": request}).data,
                        status=status.HTTP_201_CREATED)


class StaffVehiclePhotoDetailView(APIView):
    permission_classes = [InventoryAccess]

    def delete(self, request, reference, photo_id):
        photo = get_object_or_404(VehiclePhoto, vehicle__reference=reference, pk=photo_id)
        vehicle = photo.vehicle
        photo.image.delete(save=False)
        photo.delete()
        AuditEvent.objects.create(actor=request.user, action="inventory.photo.removed", subject=reference)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PublicVehicleListView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        vehicles = Vehicle.objects.filter(visibility=Vehicle.Visibility.PUBLISHED).prefetch_related("photos")
        search = request.query_params.get("search", "").strip()
        if search:
            from django.db.models import Q
            vehicles = vehicles.filter(Q(make__icontains=search) | Q(model__icontains=search))
        for parameter, field in (("year", "manufacture_year"), ("fuel", "fuel_type"),
                                 ("transmission", "transmission")):
            value = request.query_params.get(parameter)
            if value:
                vehicles = vehicles.filter(**{field: value})
        for parameter, lookup in (("min_price", "gte"), ("max_price", "lte")):
            value = request.query_params.get(parameter)
            if value:
                try:
                    amount = Decimal(value)
                    if not amount.is_finite() or amount < 0:
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    raise ValidationError({parameter: "Enter a valid non-negative price."})
                vehicles = vehicles.filter(**{f"asking_price_lkr__{lookup}": amount})
        return Response(PublicVehicleSerializer(vehicles, many=True, context={"request": request}).data)


class PublicVehicleDetailView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, reference):
        vehicle = get_object_or_404(Vehicle.objects.prefetch_related("photos"),
                                    reference=reference, visibility=Vehicle.Visibility.PUBLISHED)
        return Response(PublicVehicleSerializer(vehicle, context={"request": request}).data)


class VehiclePhotoView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, photo_id):
        photo = get_object_or_404(VehiclePhoto.objects.select_related("vehicle"), pk=photo_id)
        if photo.vehicle.visibility != Vehicle.Visibility.PUBLISHED:
            if not request.user.is_authenticated or request.user.role not in {"staff", "ceo", "manager"}:
                from rest_framework.exceptions import NotFound
                raise NotFound()
        response = FileResponse(photo.image.open("rb"), content_type=photo.content_type)
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Disposition"] = f'inline; filename="vehicle-photo-{photo.pk}"'
        # Do not let a formerly published image remain cached after unpublishing.
        response["Cache-Control"] = "private, no-store"
        return response


class StaffImportsView(ProtectedPlaceholderView):
    permission_classes = [HasCapability]
    required_capability = "imports.workflows"


class StaffReservationsView(ProtectedPlaceholderView):
    permission_classes = [HasCapability]
    required_capability = "reservations.workflows"


class RepDashboardView(ProtectedPlaceholderView):
    permission_classes = [HasCapability]
    required_capability = "sales.own"


class HandoverBoundaryView(ProtectedPlaceholderView):
    permission_classes = [HasCapability]
    required_capability = "handovers.route"
