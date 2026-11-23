from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.conf import settings
from django.core.mail import send_mail
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from datetime import datetime, time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import date, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from urllib.parse import urlencode
from PIL import Image, UnidentifiedImageError
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.views import APIView

from .models import (AccountActionToken, AuditEvent, BLApprovalRequest, CommissionLedgerEntry, CommissionRule, Customer, Enquiry, ImportMilestone,
                     HANDOVER_CONDITION_CHECKLIST, HANDOVER_KEYS_DOCUMENTS_CHECKLIST, Handover, HandoverDocumentReceipt, ImportOrder,
                     ImportTrackingAccess, Notification, Payment, Quotation, RepresentativeProfile, Reservation, Sale,
                     User, Vehicle, VehiclePhoto)
from .permissions import CommissionLedgerAccess, CustomerAccess, HasCapability, HandoverAccess, ImportAccess, InventoryAccess, PaymentAccess, QuotationAccess, RepresentativeDirectoryAccess, ReservationAccess, SalesAccess
from .serializers import (AccountSerializer, AccountSummarySerializer, AccountUpdateSerializer, CurrentUserSerializer,
                          NotificationReadSerializer, NotificationSerializer, PasswordResetRequestSerializer, PasswordSetupSerializer,
                          PublicVehicleSerializer, StaffVehicleSerializer)
from .serializers import (CustomerCreateSerializer, PublicEnquirySerializer, StaffCustomerSerializer, StaffEnquirySerializer,
                          RepresentativeCreateSerializer, RepresentativeProfileSerializer, RepresentativeUpdateSerializer)
from .serializers import normalize_customer_phone
from .serializers import ReservationCreateSerializer, ReservationReleaseSerializer, ReservationSerializer
from .serializers import SaleCreateSerializer, SaleSerializer
from .serializers import PaymentCreateSerializer, PaymentRejectSerializer, PaymentSerializer
from .serializers import QuotationDraftSerializer, QuotationSerializer
from .serializers import HandoverDocumentReceiptSerializer, HandoverPreparationSerializer, HandoverSerializer
from .quotation_pdf import build_quotation_pdf
from .handover_document_receipt_pdf import build_handover_document_receipt_pdf
from .payment_summaries import sale_payment_summary
from .finance_estimates import calculate_finance_estimate, finance_options
from .serializers import (BLApprovalDecisionSerializer, BLApprovalRequestCreateSerializer, BLApprovalRequestSerializer,
                          ImportMilestoneCreateSerializer, ImportMilestoneSerializer, ImportOrderSerializer)


class PublicEnquiryThrottle(AnonRateThrottle):
    scope = "public_enquiry"


class ImportTrackingThrottle(AnonRateThrottle):
    scope = "import_tracking"



def create_notifications(recipients, event_key, title, message, target_url):
    unique_recipients = {recipient.pk: recipient for recipient in recipients if recipient and recipient.is_active}
    for recipient in unique_recipients.values():
        Notification.objects.get_or_create(
            recipient=recipient,
            deduplication_key=event_key,
            defaults={"title": title, "message": message, "target_url": target_url},
        )


def notify_active_roles(roles, event_key, title, message, target_url, exclude_user_ids=()):
    recipients = User.objects.filter(is_active=True, role__in=roles)
    if exclude_user_ids:
        recipients = recipients.exclude(pk__in=exclude_user_ids)
    create_notifications(recipients, event_key, title, message, target_url)


def latest_handover_submitter(handover):
    submission = AuditEvent.objects.filter(
        action="handover.submitted_for_review", subject=handover.reference,
    ).select_related("actor").order_by("-created_at", "-pk").first()
    return submission.actor if submission and submission.actor_id else handover.prepared_by


def notify_handover_outcome(handover, event_kind, actor, event_id, submitter=None):
    recipients = [submitter or latest_handover_submitter(handover), handover.prepared_by]
    reviewers = User.objects.filter(is_active=True, role__in=(User.Role.CEO, User.Role.MANAGER))
    if actor:
        reviewers = reviewers.exclude(pk=actor.pk)
    recipients.extend(reviewers)
    event_key = f"handover:{handover.pk}:{event_kind}:audit:{event_id}"
    title = "Handover returned" if event_kind == "returned" else "Handover finalized"
    message = (f"Handover {handover.reference} was returned for updates." if event_kind == "returned"
               else f"Handover {handover.reference} was finalized.")
    create_notifications(recipients, event_key, title, message, "/staff/handovers")

class PublicEnquiryView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PublicEnquiryThrottle]

    def post(self, request):
        serializer = PublicEnquirySerializer(data={**request.data, "idempotency_key": request.headers.get("Idempotency-Key", request.data.get("idempotency_key", ""))})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        existing = Enquiry.objects.filter(idempotency_key=data["idempotency_key"]).first()
        if existing:
            return Response({"reference": existing.reference, "status": existing.status}, status=status.HTTP_200_OK)
        phone = data.get("phone", "").strip()
        email = data.get("email", "").strip().lower()
        try:
            with transaction.atomic():
                candidates = list(Customer.objects.filter(Q(phone=phone, phone__gt="") | Q(email__iexact=email, email__gt=""))) if phone or email else []
                if len(candidates) > 1:
                    raise ValidationError("The supplied contact details do not match one customer record. Please contact SSP directly.")
                customer = candidates[0] if candidates else None
                if customer is None:
                    customer = Customer.objects.create(full_name=data["full_name"], email=email, phone=phone,
                                                       preferred_contact=data["preferred_contact"])
                enquiry = Enquiry.objects.create(customer=customer, vehicle=data.get("vehicle"), kind=data["kind"],
                    preferred_contact=data["preferred_contact"], requested_at=data.get("requested_at"),
                    vehicle_description=data.get("vehicle_description", ""),
                    message=data.get("message", ""), idempotency_key=data["idempotency_key"])
                is_appointment = enquiry.kind in (Enquiry.Kind.APPOINTMENT, Enquiry.Kind.TEST_DRIVE)
                event_name = "appointment-requested" if is_appointment else f"{enquiry.kind}-requested"
                title = "Appointment request received" if is_appointment else f"{enquiry.get_kind_display()} received"
                notify_active_roles(
                    (User.Role.STAFF, User.Role.CEO, User.Role.MANAGER),
                    f"enquiry:{enquiry.pk}:{event_name}", title,
                    f"A {enquiry.get_kind_display().lower()} needs review ({enquiry.reference}).",
                    "/staff/enquiries",
                )
        except IntegrityError:
            existing = Enquiry.objects.filter(idempotency_key=data["idempotency_key"]).first()
            if not existing:
                raise
            return Response({"reference": existing.reference, "status": existing.status}, status=status.HTTP_200_OK)
        if email:
            requested = timezone.localtime(enquiry.requested_at).strftime("%A, %d %B %Y at %I:%M %p") if enquiry.requested_at else ""
            purpose = enquiry.get_kind_display().lower()
            requested_line = f"Your preferred time: {requested} Sri Lanka time.\n" if requested else ""
            send_mail(
                f"SSP {purpose} request received ({enquiry.reference})",
                f"Hello {customer.full_name},\n\nWe received your {purpose}. This is a request, not a confirmed booking. "
                f"Our team will contact you to confirm availability.\n{requested_line}\nReference: {enquiry.reference}\n\nSSP Motor Trading",
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=True,
            )
        return Response({"reference": enquiry.reference, "status": enquiry.status}, status=status.HTTP_201_CREATED)


class StaffEnquiryListView(APIView):
    permission_classes = [HasCapability]
    required_capability = "enquiries.manage"

    def get(self, request):
        items = Enquiry.objects.select_related("customer", "vehicle")
        kind = request.query_params.get("kind")
        status_filter = request.query_params.get("status")
        search = request.query_params.get("search", "").strip()
        if kind: items = items.filter(kind=kind)
        if status_filter: items = items.filter(status=status_filter)
        if search: items = items.filter(Q(reference__icontains=search) | Q(customer__full_name__icontains=search) | Q(customer__phone__icontains=search) | Q(customer__email__icontains=search) | Q(vehicle__reference__icontains=search) | Q(vehicle_description__icontains=search))
        return Response(StaffEnquirySerializer(items[:250], many=True).data)


class StaffEnquirySummaryView(APIView):
    permission_classes = [HasCapability]
    required_capability = "enquiries.manage"

    def get(self, request):
        pending = Enquiry.objects.filter(status__in=(Enquiry.Status.NEW, Enquiry.Status.CONTACTED))
        return Response({"pending": pending.count(), "appointments": pending.filter(kind__in=(Enquiry.Kind.APPOINTMENT, Enquiry.Kind.TEST_DRIVE)).count(), "quotes": pending.filter(kind=Enquiry.Kind.QUOTE).count()})


class StaffEnquiryDetailView(APIView):
    permission_classes = [HasCapability]
    required_capability = "enquiries.manage"

    def patch(self, request, enquiry_id):
        enquiry = get_object_or_404(Enquiry.objects.select_related("customer", "vehicle"), pk=enquiry_id)
        old_status = enquiry.status
        serializer = StaffEnquirySerializer(enquiry, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        enquiry = serializer.save()
        AuditEvent.objects.create(actor=request.user, action="enquiry.updated", subject=enquiry.reference,
            details={"status_from": old_status, "status_to": enquiry.status, "notes_changed": "internal_notes" in request.data, "scheduled": "scheduled_at" in request.data})
        return Response(StaffEnquirySerializer(enquiry).data)


class StaffCustomerListView(APIView):
    permission_classes = [CustomerAccess]

    def get(self, request):
        customers = Customer.objects.all()
        search = request.query_params.get("search", "").strip()
        if search: customers = customers.filter(Q(full_name__icontains=search) | Q(email__icontains=search) | Q(phone__icontains=search))
        return Response(StaffCustomerSerializer(customers[:250], many=True).data)

    def post(self, request):
        serializer = CustomerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        phone = data["phone"]
        email = data.get("email", "")
        matches = []
        for existing in Customer.objects.only("id", "full_name", "email", "phone", "preferred_contact", "internal_notes", "created_at", "updated_at").iterator(chunk_size=500):
            try:
                existing_phone = normalize_customer_phone(existing.phone) if existing.phone else ""
            except ValidationError:
                existing_phone = ""
            phone_match = bool(existing_phone and existing_phone == phone)
            email_match = bool(email and existing.email and existing.email.strip().lower() == email)
            if phone_match or email_match:
                matches.append((existing, phone_match, email_match))
        if len(matches) > 1:
            return Response({"detail": "These contact details match more than one customer record. Review the directory before creating another record."},
                            status=status.HTTP_409_CONFLICT)
        if matches:
            existing, phone_match, email_match = matches[0]
            return Response({"created": False, "matched_by": [key for key, matched in (("phone", phone_match), ("email", email_match)) if matched],
                             "customer": StaffCustomerSerializer(existing).data}, status=status.HTTP_200_OK)
        with transaction.atomic():
            customer = Customer.objects.create(**data)
            AuditEvent.objects.create(actor=request.user, action="customer.created", subject=f"customer:{customer.pk}",
                                      details={"source": "manual"})
        return Response({"created": True, "customer": StaffCustomerSerializer(customer).data}, status=status.HTTP_201_CREATED)


class StaffCustomerDetailView(APIView):
    permission_classes = [HasCapability]
    required_capability = "customers.view"

    def get(self, request, customer_id):
        customer = get_object_or_404(Customer.objects.prefetch_related("enquiries__vehicle"), pk=customer_id)
        data = StaffCustomerSerializer(customer).data
        data["enquiries"] = StaffEnquirySerializer(customer.enquiries.select_related("customer", "vehicle"), many=True).data
        return Response(data)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"detail": "CSRF cookie set"})


class AccountEmailDeliveryError(Exception):
    pass


def issue_account_action_token(user, kind, actor=None):
    now = timezone.now()
    AccountActionToken.objects.filter(user=user, kind=kind, used_at__isnull=True).update(used_at=now)
    raw_token = token_urlsafe(32)
    lifetime = timedelta(hours=24) if kind == AccountActionToken.Kind.INVITATION else timedelta(hours=1)
    AccountActionToken.objects.create(user=user, kind=kind, token_hash=sha256(raw_token.encode("utf-8")).hexdigest(),
        expires_at=now + lifetime, created_by=actor)
    route = "staff/accept-invitation" if kind == AccountActionToken.Kind.INVITATION else "staff/reset-password"
    link = f"{settings.ACCOUNT_PORTAL_URL}/{route}?{urlencode({'token': raw_token})}"
    subject = "Set up your SSP Motor Trading account" if kind == AccountActionToken.Kind.INVITATION else "Reset your SSP Motor Trading password"
    expiry = "24 hours" if kind == AccountActionToken.Kind.INVITATION else "1 hour"
    message = (f"Hello {user.first_name or user.username},\n\n"
        f"Use the secure link below to {'set up your account' if kind == AccountActionToken.Kind.INVITATION else 'reset your password'}. "
        f"It expires in {expiry} and can be used once.\n\n{link}\n\nIf you did not expect this message, you can ignore it.")
    try:
        if not send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False):
            raise AccountEmailDeliveryError
    except AccountEmailDeliveryError:
        raise
    except Exception as exc:
        raise AccountEmailDeliveryError from exc
    action = "account.invitation_sent" if kind == AccountActionToken.Kind.INVITATION else "account.password_reset_sent"
    AuditEvent.objects.create(actor=actor, action=action, subject=user.username,
        details={"kind": kind, "expires_at": (now + lifetime).isoformat()})


def valid_account_action_token(raw_token, kind):
    if not raw_token:
        return None
    token_hash = sha256(raw_token.encode("utf-8")).hexdigest()
    return AccountActionToken.objects.select_for_update().select_related("user").filter(
        token_hash=token_hash, kind=kind, used_at__isnull=True, expires_at__gt=timezone.now()).first()


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



class NotificationPagination(LimitOffsetPagination):
    default_limit = 50
    max_limit = 100


class NotificationCollectionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = Notification.objects.filter(recipient=request.user).order_by("-created_at", "-pk")
        unread_count = notifications.filter(read_at__isnull=True).count()
        paginator = NotificationPagination()
        page = paginator.paginate_queryset(notifications, request, view=self)
        response = paginator.get_paginated_response(NotificationSerializer(page, many=True).data)
        response.data["unread_count"] = unread_count
        return response


class NotificationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def patch(self, request, notification_id):
        serializer = NotificationReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notification = get_object_or_404(
            Notification.objects.select_for_update().filter(recipient=request.user), pk=notification_id,
        )
        is_read = serializer.validated_data["is_read"]
        notification.read_at = (notification.read_at or timezone.now()) if is_read else None
        notification.save(update_fields=["read_at"])
        return Response(NotificationSerializer(notification).data)

class AccountListCreateView(APIView):
    permission_classes = [HasCapability]
    required_capability = "accounts.manage"

    def get(self, request):
        return Response(AccountSummarySerializer(User.objects.order_by("username"), many=True).data)

    def post(self, request):
        if "password" in request.data:
            return Response({"password": "Passwords are set through the secure invitation flow."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = AccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                user = serializer.save()
                AuditEvent.objects.create(actor=request.user, action="account.created", subject=user.username,
                    details={"role": user.role, "account_type": user.account_type})
                issue_account_action_token(user, AccountActionToken.Kind.INVITATION, request.user)
        except AccountEmailDeliveryError:
            return Response({"detail": "The invitation email could not be sent. No account was created; check email configuration and try again."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(AccountSummarySerializer(user).data, status=status.HTTP_201_CREATED)


class AccountDetailView(APIView):
    permission_classes = [HasCapability]
    required_capability = "accounts.manage"

    def get_object(self, account_id):
        return User.objects.select_for_update().get(pk=account_id)

    @transaction.atomic
    def patch(self, request, account_id):
        try:
            user = self.get_object(account_id)
        except User.DoesNotExist:
            return Response({"detail": "Account not found."}, status=status.HTTP_404_NOT_FOUND)
        if user.role == User.Role.ADMIN and user.pk != request.user.pk:
            return Response({"detail": "Admin accounts can only be managed by their own account."},
                            status=status.HTTP_403_FORBIDDEN)
        if "password" in request.data:
            return Response({"password": "Passwords can only be changed with a valid invitation or reset link."}, status=status.HTTP_400_BAD_REQUEST)
        if user.role == User.Role.ADMIN and "role" in request.data and request.data["role"] != User.Role.ADMIN:
            return Response({"role": "The Admin role cannot be changed through account management."}, status=status.HTTP_400_BAD_REQUEST)
        if user.pk == request.user.pk and request.data.get("is_active") is False:
            return Response({"detail": "You cannot deactivate your own account."},
                            status=status.HTTP_400_BAD_REQUEST)
        if not user.is_active and request.data.get("is_active") is True and not user.has_usable_password():
            return Response({"is_active": "The user must complete the invitation and set a password before activation."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = AccountUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        old_role, old_active, old_email = user.role, user.is_active, user.email
        if old_active and request.data.get("is_active") is False and old_role == User.Role.ADMIN:
            active_admins = list(User.objects.select_for_update().filter(role=User.Role.ADMIN, is_active=True).values_list("pk", flat=True))
            if len(active_admins) <= 1:
                return Response({"is_active": "The last active Admin account cannot be deactivated."}, status=status.HTTP_400_BAD_REQUEST)
        updated = serializer.save()
        if old_active != updated.is_active or old_email != updated.email:
            AccountActionToken.objects.filter(user=updated, used_at__isnull=True).update(used_at=timezone.now())
        AuditEvent.objects.create(actor=request.user, action="account.updated", subject=updated.username,
                                  details={"role": updated.role, "account_type": updated.account_type})
        if old_active != updated.is_active:
            AuditEvent.objects.create(actor=request.user, action="account.activated" if updated.is_active else "account.deactivated",
                subject=updated.username, details={"is_active": updated.is_active})
        if old_role != updated.role:
            AuditEvent.objects.create(actor=request.user, action="account.role_changed", subject=updated.username,
                details={"role_from": old_role, "role_to": updated.role})
        return Response(AccountSummarySerializer(updated).data)


class AccountAccessLinkView(APIView):
    permission_classes = [HasCapability]
    required_capability = "accounts.manage"

    def post(self, request, account_id):
        try:
            user = User.objects.get(pk=account_id)
        except User.DoesNotExist:
            return Response({"detail": "Account not found."}, status=status.HTTP_404_NOT_FOUND)
        if user.role == User.Role.ADMIN:
            return Response({"detail": "Admin access links are not issued through account management."}, status=status.HTTP_403_FORBIDDEN)
        kind = request.data.get("kind")
        if kind == AccountActionToken.Kind.INVITATION:
            if user.is_active or user.has_usable_password():
                return Response({"detail": "Invitations are only available for accounts that have not completed setup."}, status=status.HTTP_400_BAD_REQUEST)
        elif kind == AccountActionToken.Kind.PASSWORD_RESET:
            if not user.is_active or not user.has_usable_password():
                return Response({"detail": "Activate an onboarded account before sending a password reset."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({"kind": "Choose invitation or password_reset."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                locked_user = User.objects.select_for_update().get(pk=user.pk)
                if kind == AccountActionToken.Kind.INVITATION and (locked_user.is_active or locked_user.has_usable_password()):
                    return Response({"detail": "Invitations are only available for accounts that have not completed setup."}, status=status.HTTP_400_BAD_REQUEST)
                if kind == AccountActionToken.Kind.PASSWORD_RESET and (not locked_user.is_active or not locked_user.has_usable_password()):
                    return Response({"detail": "Activate an onboarded account before sending a password reset."}, status=status.HTTP_400_BAD_REQUEST)
                issue_account_action_token(locked_user, kind, request.user)
        except AccountEmailDeliveryError:
            return Response({"detail": "The email could not be sent. Check email configuration and try again."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        detail = "Invitation email sent." if kind == AccountActionToken.Kind.INVITATION else "Password reset email sent."
        return Response({"detail": detail})


class PasswordResetRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    @method_decorator(csrf_protect)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        matches = User.objects.filter(email__iexact=serializer.validated_data["email"], is_active=True)
        user = matches.first() if matches.count() == 1 else None
        if user and user.has_usable_password():
            try:
                with transaction.atomic():
                    locked_user = User.objects.select_for_update().get(pk=user.pk)
                    if locked_user.is_active and locked_user.has_usable_password():
                        issue_account_action_token(locked_user, AccountActionToken.Kind.PASSWORD_RESET)
                        AuditEvent.objects.create(actor=None, action="account.password_reset_requested", subject=locked_user.username, details={})
            except AccountEmailDeliveryError:
                # Preserve the same public response for known and unknown addresses.
                pass
        return Response({"detail": "If an active account matches that email address, a password reset link has been sent."})


class PasswordSetupView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    @method_decorator(csrf_protect)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request):
        serializer = PasswordSetupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                token_value = serializer.validated_data["token"]
                token = valid_account_action_token(token_value, AccountActionToken.Kind.INVITATION)
                if token is None:
                    token = valid_account_action_token(token_value, AccountActionToken.Kind.PASSWORD_RESET)
                if token is None:
                    return Response({"token": "This link is invalid, expired, or has already been used."}, status=status.HTTP_400_BAD_REQUEST)
                user = User.objects.select_for_update().get(pk=token.user_id)
                if token.kind == AccountActionToken.Kind.PASSWORD_RESET and not user.is_active:
                    return Response({"token": "This link is invalid, expired, or has already been used."}, status=status.HTTP_400_BAD_REQUEST)
                try:
                    validate_password(serializer.validated_data["password"], user=user)
                except DjangoValidationError as exc:
                    return Response({"password": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
                now = timezone.now()
                token.used_at = now
                token.save(update_fields=["used_at"])
                AccountActionToken.objects.filter(user=user, used_at__isnull=True).exclude(pk=token.pk).update(used_at=now)
                was_active = user.is_active
                user.set_password(serializer.validated_data["password"])
                if token.kind == AccountActionToken.Kind.INVITATION:
                    user.is_active = True
                user.save(update_fields=["password", "is_active"])
                if not was_active and user.is_active:
                    AuditEvent.objects.create(actor=user, action="account.activated", subject=user.username,
                        details={"activation_method": "invitation"})
                    AuditEvent.objects.create(actor=user, action="account.invitation_accepted", subject=user.username, details={})
                else:
                    AuditEvent.objects.create(actor=user, action="account.password_reset_completed", subject=user.username, details={})
        except AccountActionToken.DoesNotExist:
            return Response({"token": "This link is invalid, expired, or has already been used."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Password set successfully. You can now sign in."})


class AuditHistoryPagination(LimitOffsetPagination):
    default_limit = 25
    max_limit = 100


AUDIT_SAFE_DETAIL_FIELDS = {
    "account.created": ("role", "account_type"),
    "account.updated": ("role", "account_type"),
    "account.invitation_sent": ("kind", "expires_at"),
    "account.password_reset_sent": ("kind", "expires_at"),
    "account.activated": ("is_active", "activation_method"),
    "account.deactivated": ("is_active",),
    "account.role_changed": ("role_from", "role_to"),
    "enquiry.updated": ("status_from", "status_to", "notes_changed", "scheduled"),
    "commission.approved": ("previous_status", "status"),
    "commission.paid": ("previous_status", "status", "payout_date", "payout_amount_lkr"),
    "commission.reversed": ("previous_status", "status"),
    "commission.pending_created": ("handover_reference", "rate_status", "amount_lkr"),
    "commission_brackets.updated": ("previous", "current"),
    "representative.linked": ("business_status",),
    "representative.updated": ("business_status_from", "business_status_to"),
    "sale.created": ("vehicle_reference", "status", "sale_type"),
    "sale.confirmed": ("vehicle_reference", "reservation_reference"),
    "handover.prepared": ("sale_reference", "vehicle_reference"),
    "handover.updated": ("returned_to_preparing",),
    "handover.submitted_for_review": ("sale_reference",),
    "handover.finalized": ("sale_reference", "vehicle_reference", "outstanding_balance_lkr", "balance_review_required"),
    "payment.recorded": ("status", "method", "sale_reference", "reservation_reference", "import_reference", "evidence_attached"),
    "payment.verified": ("sale_reference", "reservation_reference", "import_reference"),
    "quotation.created": ("status",),
    "quotation.issued": ("issue_date",),
    "inventory.vehicle.created": ("status", "visibility"),
    "inventory.vehicle.status_changed": ("from", "to"),
    "inventory.photos.uploaded": ("count",),
    "import.milestone.recorded": ("milestone",),
    "import.bl_approval_requested": ("import_reference",),
    "import.bl_approval_approved": ("import_reference",),
    "import.bl_approval_rejected": ("import_reference",),
    "reservation.created": ("vehicle_reference", "status", "advance_status"),
    "reservation.released": ("vehicle_reference", "status"),
}


def safe_audit_details(event):
    safe = {}
    for key in AUDIT_SAFE_DETAIL_FIELDS.get(event.action, ()):
        value = (event.details or {}).get(key)
        if isinstance(value, (bool, int, float)):
            safe[key] = value
        elif isinstance(value, str):
            safe[key] = value[:200]
        elif event.action == "commission_brackets.updated" and key in {"previous", "current"} and isinstance(value, list):
            rows = []
            for row in value[:50]:
                if not isinstance(row, dict):
                    continue
                safe_row = {}
                for field in ("minimum_lkr", "maximum_lkr", "percentage", "effective_date", "active"):
                    item = row.get(field)
                    if item is None or isinstance(item, (str, bool, int, float)):
                        safe_row[field] = item
                rows.append(safe_row)
            safe[key] = rows
    return safe


def serialize_audit_event(event):
    actor = event.actor
    return {
        "actor": actor.username if actor else None,
        "actor_role": actor.role if actor else None,
        "action": event.action,
        "subject": event.subject,
        "created_at": event.created_at,
        "details": safe_audit_details(event),
    }


class AuditHistoryView(APIView):
    permission_classes = [HasCapability]

    def respond_with_events(self, request, events):
        params = request.query_params
        search = params.get("search", "").strip()
        action = params.get("action", "").strip()
        actor = params.get("actor", "").strip()
        role = params.get("role", "").strip().lower()
        if len(search) > 120 or len(action) > 80 or len(actor) > 150:
            raise ValidationError({"detail": "Search and filter values exceed the supported length."})
        if search:
            events = events.filter(Q(action__icontains=search) | Q(subject__icontains=search) | Q(actor__username__icontains=search))
        if action:
            events = events.filter(action=action)
        if actor:
            events = events.filter(actor__username__icontains=actor)
        if role:
            valid_roles = set(User.Role.values) | {"system"}
            if role not in valid_roles:
                raise ValidationError({"role": "Choose a valid account role or system."})
            events = events.filter(actor__isnull=True) if role == "system" else events.filter(actor__role=role)
        date_from_value = params.get("date_from", "").strip()
        date_to_value = params.get("date_to", "").strip()
        try:
            date_from = parse_date(date_from_value) if date_from_value else None
            date_to = parse_date(date_to_value) if date_to_value else None
        except (TypeError, ValueError):
            date_from = date_to = None
        if date_from_value and date_from is None:
            raise ValidationError({"date_from": "Use the YYYY-MM-DD date format."})
        if date_to_value and date_to is None:
            raise ValidationError({"date_to": "Use the YYYY-MM-DD date format."})
        if date_from and date_to and date_from > date_to:
            raise ValidationError({"date_to": "The end date must be on or after the start date."})
        current_timezone = timezone.get_current_timezone()
        if date_from:
            start_at = timezone.make_aware(datetime.combine(date_from, time.min), current_timezone)
            events = events.filter(created_at__gte=start_at)
        if date_to:
            end_at = timezone.make_aware(datetime.combine(date_to + timedelta(days=1), time.min), current_timezone)
            events = events.filter(created_at__lt=end_at)

        paginator = AuditHistoryPagination()
        page = paginator.paginate_queryset(events.order_by("-created_at", "-pk"), request, view=self)
        return paginator.get_paginated_response([serialize_audit_event(event) for event in page])


class RecentActivityView(AuditHistoryView):
    required_capability = "activity.view"

    def get(self, request):
        events = AuditEvent.objects.select_related("actor")
        return self.respond_with_events(request, events)


class ManagerOversightView(AuditHistoryView):
    required_capability = "manager_oversight.view"

    def get(self, request):
        events = AuditEvent.objects.filter(actor__role=User.Role.MANAGER).select_related("actor")
        return self.respond_with_events(request, events)


class CommissionRulesView(APIView):
    permission_classes = [HasCapability]

    def get_permissions(self):
        self.required_capability = "commission_rules.manage" if self.request.method in {"PUT", "POST", "PATCH", "DELETE"} else "commission_rules.view"
        return super().get_permissions()

    def get(self, request):
        if request.query_params.get("history") == "1":
            events = AuditEvent.objects.filter(action="commission_brackets.updated", subject="brackets").select_related("actor")[:100]
            return Response([{"actor": event.actor.username if event.actor else None,
                "created_at": event.created_at, "previous": event.details.get("previous"),
                "current": event.details.get("current", [])} for event in events])
        return Response(list(CommissionRule.objects.values("key", "value", "updated_at")))

    def put(self, request, key):
        if key != "brackets" or not isinstance(request.data, list):
            return Response({"detail": "Submit the complete bracket schedule as a list at key 'brackets'."}, status=status.HTTP_400_BAD_REQUEST)
        brackets = request.data
        seen = set()
        normalized = []
        try:
            for row in brackets:
                if not isinstance(row, dict) or set(row) != {"minimum_lkr", "maximum_lkr", "percentage", "effective_date", "active"}:
                    raise ValueError("Each bracket needs minimum_lkr, maximum_lkr, percentage, effective_date and active.")
                low = Decimal(str(row["minimum_lkr"]))
                high = None if row["maximum_lkr"] is None else Decimal(str(row["maximum_lkr"]))
                rate = Decimal(str(row["percentage"]))
                effective = row["effective_date"]
                from datetime import date
                effective = date.fromisoformat(effective).isoformat()
                if low < 0 or (high is not None and high <= low) or rate <= 0 or rate > 100 or not isinstance(row["active"], bool):
                    raise ValueError("Values must be non-negative, maximum must exceed minimum, percentage must be above 0 and at most 100, and active must be boolean.")
                low_q = low.quantize(Decimal("0.01"))
                high_q = high.quantize(Decimal("0.01")) if high is not None else None
                rate_q = rate.quantize(Decimal("0.001"))
                if low != low_q or (high is not None and high != high_q) or rate != rate_q or low_q > Decimal("999999999999.99") or (high_q is not None and high_q > Decimal("999999999999.99")):
                    raise ValueError("Selling-value boundaries must fit LKR precision of two decimals and commission rates up to three decimals.")
                normalized.append({"minimum_lkr": str(low_q), "maximum_lkr": str(high_q) if high_q is not None else None,
                    "percentage": str(rate_q), "effective_date": effective, "active": row["active"]})
            for i, first in enumerate(normalized):
                if not first["active"]: continue
                a0, a1 = Decimal(first["minimum_lkr"]), Decimal(first["maximum_lkr"]) if first["maximum_lkr"] else None
                for second in normalized[i + 1:]:
                    if not second["active"] or first["effective_date"] != second["effective_date"]: continue
                    b0, b1 = Decimal(second["minimum_lkr"]), Decimal(second["maximum_lkr"]) if second["maximum_lkr"] else None
                    if (a1 is None or b0 < a1) and (b1 is None or a0 < b1):
                        raise ValueError("Active selling-value brackets cannot overlap for the same effective date.")
        except (ValueError, TypeError, InvalidOperation) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        prior = CommissionRule.objects.filter(key=key).values_list("value", flat=True).first()
        rule, _ = CommissionRule.objects.update_or_create(key=key, defaults={"value": normalized, "updated_by": request.user})
        AuditEvent.objects.create(actor=request.user, action="commission_brackets.updated", subject=key,
            details={"previous": prior, "current": normalized})
        return Response({"key": rule.key, "value": rule.value, "updated_at": rule.updated_at})


class CommissionLedgerView(APIView):
    permission_classes = [CommissionLedgerAccess]

    def get(self, request):
        if request.query_params.get("view") == "leaderboard":
            return Response(commission_leaderboard(CommissionLedgerEntry.objects.filter(status="paid", recipient__role=User.Role.REP)))
        entries = CommissionLedgerEntry.objects.select_related("sale__vehicle", "handover", "recipient", "created_by")
        search = request.query_params.get("search", "").strip()
        if search:
            entries = entries.filter(Q(sale__reference__icontains=search) | Q(handover__reference__icontains=search) |
                Q(sale__vehicle__reference__icontains=search) | Q(recipient__username__icontains=search) |
                Q(recipient__first_name__icontains=search) | Q(recipient__last_name__icontains=search))
        return Response([{"id": entry.pk, "sale_reference": entry.sale.reference,
            "handover_reference": entry.handover.reference, "vehicle_reference": entry.sale.vehicle.reference,
            "recipient_name": (" ".join(part for part in (entry.recipient.first_name, entry.recipient.last_name) if part)
                               or entry.recipient.username) if entry.recipient_id else None,
            "sale_price_lkr": entry.sale_price_lkr, "commission_rate_percent": entry.commission_rate_percent,
            "commission_amount_lkr": entry.commission_amount_lkr, "policy_snapshot": entry.policy_snapshot,
            "status": entry.status, "created_at": entry.created_at, "created_by": entry.created_by.username,
            "approved_by": entry.approved_by.username if entry.approved_by_id else None, "approved_at": entry.approved_at,
            "payout_reference": entry.payout_reference, "payout_date": entry.payout_date,
            "payout_amount_lkr": entry.payout_amount_lkr, "paid_by": entry.paid_by.username if entry.paid_by_id else None,
            "paid_at": entry.paid_at, "reversal_reason": entry.reversal_reason,
            "reversed_by": entry.reversed_by.username if entry.reversed_by_id else None, "reversed_at": entry.reversed_at}
            for entry in entries[:250]])


def commission_leaderboard(entries):
    rows = (entries.values("recipient__first_name", "recipient__last_name", "recipient__username")
        .annotate(paid_entries=Count("pk"), paid_total_lkr=Sum("payout_amount_lkr"))
        .order_by("-paid_total_lkr", "recipient__username")[:100])
    return [{"rep_name": " ".join(part for part in (row["recipient__first_name"], row["recipient__last_name"]) if part)
             or row["recipient__username"], "paid_entries": row["paid_entries"], "paid_total_lkr": row["paid_total_lkr"]}
            for row in rows]


class CommissionLedgerTransitionView(APIView):
    permission_classes = [CommissionLedgerAccess]
    allow_payout_transition = True

    @staticmethod
    def data(entry):
        return {"id": entry.pk, "status": entry.status, "approved_by": entry.approved_by.username if entry.approved_by_id else None,
            "approved_at": entry.approved_at, "payout_reference": entry.payout_reference, "payout_date": entry.payout_date,
            "payout_amount_lkr": entry.payout_amount_lkr, "paid_by": entry.paid_by.username if entry.paid_by_id else None,
            "paid_at": entry.paid_at, "reversal_reason": entry.reversal_reason,
            "reversed_by": entry.reversed_by.username if entry.reversed_by_id else None, "reversed_at": entry.reversed_at}

    def post(self, request, entry_id):
        requested = request.data.get("status")
        try:
            with transaction.atomic():
                entry = CommissionLedgerEntry.objects.select_for_update(of=("self",)).select_related("recipient", "sale").get(pk=entry_id)
                if requested == entry.status:
                    if requested == "paid":
                        try:
                            same = (str(request.data.get("payout_reference", "")).strip() == entry.payout_reference and
                                    date.fromisoformat(request.data.get("payout_date", "")) == entry.payout_date and
                                    Decimal(str(request.data.get("payout_amount_lkr", ""))) == entry.payout_amount_lkr)
                        except (ValueError, TypeError, InvalidOperation):
                            same = False
                        if not same: return Response({"detail": "This entry already has a different recorded payout."}, status=status.HTTP_409_CONFLICT)
                    if requested == "reversed" and str(request.data.get("reason", "")).strip() != entry.reversal_reason:
                        return Response({"detail": "This entry has already been reversed for a different reason."}, status=status.HTTP_409_CONFLICT)
                    return Response(self.data(entry))

                now = timezone.now()
                previous_status = entry.status
                if requested == "approved":
                    if entry.status != "pending": return Response({"detail": "Only pending commissions can be approved."}, status=status.HTTP_409_CONFLICT)
                    if not entry.recipient_id or entry.commission_amount_lkr is None:
                        return Response({"detail": "A commission must have an assigned Rep and a calculated rate and amount before approval."}, status=status.HTTP_400_BAD_REQUEST)
                    entry.status = "approved"; entry.approved_by = request.user; entry.approved_at = now
                    action = "approved"
                elif requested == "paid":
                    if entry.status != "approved": return Response({"detail": "Approve this commission before recording payment."}, status=status.HTTP_409_CONFLICT)
                    reference = str(request.data.get("payout_reference", "")).strip()
                    raw_date = request.data.get("payout_date", "")
                    raw_amount = request.data.get("payout_amount_lkr", "")
                    if not reference or len(reference) > 100 or not raw_date or not raw_amount:
                        return Response({"detail": "Payout reference, payout date, and payout amount are required."}, status=status.HTTP_400_BAD_REQUEST)
                    try:
                        payout_date = date.fromisoformat(raw_date)
                        payout_amount = Decimal(str(raw_amount))
                    except (ValueError, TypeError, InvalidOperation):
                        return Response({"detail": "Enter a valid payout date and amount."}, status=status.HTTP_400_BAD_REQUEST)
                    if payout_date > timezone.localdate():
                        return Response({"detail": "Payout date cannot be in the future for a payment recorded as paid."}, status=status.HTTP_400_BAD_REQUEST)
                    if not payout_amount.is_finite() or payout_amount <= 0 or payout_amount.quantize(Decimal("0.01")) != payout_amount:
                        return Response({"detail": "Payout amount must be positive and use no more than two decimal places."}, status=status.HTTP_400_BAD_REQUEST)
                    if payout_amount != entry.commission_amount_lkr:
                        return Response({"detail": "Payout amount must equal the immutable commission amount."}, status=status.HTTP_400_BAD_REQUEST)
                    entry.status = "paid"; entry.payout_reference = reference; entry.payout_date = payout_date
                    entry.payout_amount_lkr = payout_amount; entry.paid_by = request.user; entry.paid_at = now
                    action = "paid"
                elif requested == "reversed":
                    if entry.status not in {"pending", "approved", "paid"}:
                        return Response({"detail": "This commission cannot be reversed from its current state."}, status=status.HTTP_409_CONFLICT)
                    reason = str(request.data.get("reason", "")).strip()
                    if not reason: return Response({"detail": "A reason is required to reverse a commission."}, status=status.HTTP_400_BAD_REQUEST)
                    entry.status = "reversed"; entry.reversal_reason = reason; entry.reversed_by = request.user; entry.reversed_at = now
                    action = "reversed"
                else:
                    return Response({"detail": "Choose approved, paid, or reversed as the target status."}, status=status.HTTP_400_BAD_REQUEST)

                entry.save()
                AuditEvent.objects.create(actor=request.user, action=f"commission.{action}", subject=entry.sale.reference,
                    details={"commission_entry_id": entry.pk, "previous_status": previous_status,
                        "status": entry.status, "payout_reference": entry.payout_reference or None,
                        "payout_date": entry.payout_date.isoformat() if entry.payout_date else None,
                        "payout_amount_lkr": str(entry.payout_amount_lkr) if entry.payout_amount_lkr is not None else None,
                        "reason": entry.reversal_reason or None})
                return Response(self.data(entry))
        except CommissionLedgerEntry.DoesNotExist:
            return Response({"detail": "Commission entry not found."}, status=status.HTTP_404_NOT_FOUND)
        except IntegrityError:
            return Response({"detail": "That payout reference has already been used."}, status=status.HTTP_409_CONFLICT)


class HandoverEligibleSalesView(APIView):
    permission_classes = [HandoverAccess]
    handover_action = "eligible_sales"

    def get(self, request):
        sales = Sale.objects.filter(status=Sale.Status.CONFIRMED, vehicle__status=Vehicle.Status.SOLD).exclude(handover__isnull=False).select_related("customer", "vehicle")
        search = request.query_params.get("search", "").strip()
        if search:
            sales = sales.filter(Q(reference__icontains=search) | Q(customer__full_name__icontains=search) |
                Q(vehicle__reference__icontains=search) | Q(vehicle__make__icontains=search) | Q(vehicle__model__icontains=search))
        return Response([{"reference": sale.reference, "vehicle_reference": sale.vehicle.reference,
            "vehicle_name": f"{sale.vehicle.manufacture_year} {sale.vehicle.make} {sale.vehicle.model} {sale.vehicle.variant}".strip(),
            "customer_name": sale.customer.full_name, "agreed_price_lkr": sale.agreed_price_lkr}
            for sale in sales.order_by("reference")[:100]])


class ProtectedPlaceholderView(APIView):
    """Access-control examples for workflows deliberately not implemented in this slice."""

    required_capability = None

    def get(self, request):
        return Response({"detail": "Workflow is outside this authentication foundation."}, status=501)


class ManagerRepsView(APIView):
    permission_classes = [RepresentativeDirectoryAccess]

    def get(self, request):
        profiles = RepresentativeProfile.objects.select_related("user")
        search = request.query_params.get("search", "").strip()
        business_status = request.query_params.get("status", "").strip()
        if business_status in RepresentativeProfile.BusinessStatus.values:
            profiles = profiles.filter(business_status=business_status)
        if search:
            profiles = profiles.filter(Q(reference__icontains=search) | Q(user__username__icontains=search) |
                Q(user__first_name__icontains=search) | Q(user__last_name__icontains=search) |
                Q(user__email__icontains=search) | Q(user__phone__icontains=search))
        return Response(RepresentativeProfileSerializer(profiles[:250], many=True).data)

    def post(self, request):
        serializer = RepresentativeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save(created_by=request.user)
        AuditEvent.objects.create(actor=request.user, action="representative.linked", subject=profile.reference,
                                  details={"user_id": profile.user_id, "business_status": profile.business_status})
        return Response(RepresentativeProfileSerializer(profile).data, status=status.HTTP_201_CREATED)


class ManagerRepAccountsView(APIView):
    permission_classes = [HasCapability]
    required_capability = "reps.manage"

    def get(self, request):
        accounts = User.objects.filter(role=User.Role.REP).exclude(representative_profile__isnull=False).order_by("first_name", "last_name", "username")
        return Response([{"id": user.pk, "username": user.username,
            "full_name": " ".join(part for part in (user.first_name, user.last_name) if part) or user.username,
            "email": user.email, "phone": user.phone, "is_active": user.is_active} for user in accounts[:250]])


class ManagerRepDetailView(APIView):
    permission_classes = [RepresentativeDirectoryAccess]

    def get_profile(self, profile_id):
        return get_object_or_404(RepresentativeProfile.objects.select_related("user"), pk=profile_id)

    def get(self, request, profile_id):
        return Response(RepresentativeProfileSerializer(self.get_profile(profile_id)).data)

    def patch(self, request, profile_id):
        profile = self.get_profile(profile_id)
        old_status = profile.business_status
        serializer = RepresentativeUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()
        AuditEvent.objects.create(actor=request.user, action="representative.updated", subject=profile.reference,
            details={"business_status_from": old_status, "business_status_to": profile.business_status,
                     "profile_fields": sorted(set(request.data.keys()) - {"business_status"})})
        return Response(RepresentativeProfileSerializer(profile).data)


class RepSelfProfileView(APIView):
    permission_classes = [HasCapability]
    required_capability = "reps.self"

    def get(self, request):
        profile = RepresentativeProfile.objects.select_related("user").filter(user=request.user).first()
        return Response({"profile": RepresentativeProfileSerializer(profile).data if profile else None})


class ManagerSalesView(APIView):
    permission_classes = [SalesAccess]

    def get_queryset(self):
        return Sale.objects.select_related("vehicle", "customer", "representative__user", "reservation", "import_order", "created_by")

    def get(self, request):
        sales = self.get_queryset()
        query = request.query_params.get("search", "").strip()
        status_filter = request.query_params.get("status", "")
        sale_type = request.query_params.get("sale_type", "")
        if status_filter in Sale.Status.values:
            sales = sales.filter(status=status_filter)
        if sale_type in Sale.SaleType.values:
            sales = sales.filter(sale_type=sale_type)
        if query:
            sales = sales.filter(Q(reference__icontains=query) | Q(vehicle__reference__icontains=query) |
                Q(vehicle__make__icontains=query) | Q(vehicle__model__icontains=query) |
                Q(customer__full_name__icontains=query) | Q(representative__reference__icontains=query) |
                Q(representative__user__first_name__icontains=query) | Q(representative__user__last_name__icontains=query))
        return Response(SaleSerializer(sales[:250], many=True).data)

    def post(self, request):
        serializer = SaleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            with transaction.atomic():
                reservation = None
                import_order = None
                if data["sale_type"] == Sale.SaleType.IMPORT:
                    import_order = ImportOrder.objects.select_for_update().select_related("customer").get(reference=data["import_reference"])
                    if import_order.status != ImportOrder.Status.READY_FOR_COLLECTION or not import_order.vehicle_id:
                        return Response({"import_reference": "Only ready imports linked to a registered vehicle can be sold."}, status=status.HTTP_409_CONFLICT)
                    if Sale.objects.filter(import_order=import_order).exists():
                        return Response({"import_reference": "This import already has a sale."}, status=status.HTTP_409_CONFLICT)
                    vehicle = Vehicle.objects.select_for_update().get(pk=import_order.vehicle_id)
                    if vehicle.status != Vehicle.Status.AVAILABLE:
                        return Response({"import_reference": "The import vehicle is no longer available."}, status=status.HTTP_409_CONFLICT)
                    already_paid = Payment.objects.filter(import_order=import_order, status=Payment.Status.VERIFIED).aggregate(total=Sum("amount_lkr"))["total"] or Decimal("0.00")
                    if already_paid > data["agreed_price_lkr"]:
                        return Response({"agreed_price_lkr": "Verified import payments already exceed this sale price."}, status=status.HTTP_400_BAD_REQUEST)
                    customer = import_order.customer
                else:
                    ref = data.get("reservation_reference")
                    if ref:
                        reservation = Reservation.objects.select_for_update().get(reference=ref)
                        vehicle = Vehicle.objects.select_for_update().get(pk=reservation.vehicle_id)
                        customer = reservation.customer
                        if ((data.get("vehicle_reference") and data["vehicle_reference"] != vehicle.reference)
                                or (data.get("customer") and reservation.customer_id != data["customer"].pk)
                                or reservation.status != Reservation.Status.ACTIVE or vehicle.status != Vehicle.Status.RESERVED):
                            return Response({"reservation_reference": "Select the active reservation matching this reserved vehicle."}, status=status.HTTP_400_BAD_REQUEST)
                        if Sale.objects.filter(reservation=reservation).exists():
                            return Response({"reservation_reference": "This reservation already has a sale record."}, status=status.HTTP_409_CONFLICT)
                    else:
                        customer = data["customer"]
                        vehicle = Vehicle.objects.select_for_update().get(reference=data["vehicle_reference"])
                        if vehicle.status != Vehicle.Status.AVAILABLE:
                            return Response({"vehicle_reference": "Only available vehicles can be sold directly; reserved vehicles require their active reservation."}, status=status.HTTP_409_CONFLICT)
                sale = Sale.objects.create(vehicle=vehicle, customer=customer, representative=data.get("representative"),
                    reservation=reservation, import_order=import_order, sale_type=data["sale_type"], agreed_price_lkr=data["agreed_price_lkr"],
                    sale_date=data["sale_date"], created_by=request.user)
                AuditEvent.objects.create(actor=request.user, action="sale.created", subject=sale.reference,
                    details={"vehicle_reference": vehicle.reference, "status": sale.status, "sale_type": sale.sale_type,
                             "import_reference": import_order.reference if import_order else None})
                if sale.representative_id:
                    rep_user = sale.representative.user
                    create_notifications([rep_user], f"sale:{sale.pk}:rep-assigned:{rep_user.pk}", "A sale was assigned to you",
                        f"Sale {sale.reference} is available in My sales.", "/staff/my-sales")
        except Vehicle.DoesNotExist:
            return Response({"vehicle_reference": "Vehicle not found."}, status=status.HTTP_404_NOT_FOUND)
        except Reservation.DoesNotExist:
            return Response({"reservation_reference": "Reservation not found."}, status=status.HTTP_404_NOT_FOUND)
        except ImportOrder.DoesNotExist:
            return Response({"import_reference": "Import order not found."}, status=status.HTTP_404_NOT_FOUND)
        except IntegrityError:
            return Response({"detail": "This vehicle, reservation, or import order is already linked to a sale."}, status=status.HTTP_409_CONFLICT)
        return Response(SaleSerializer(sale).data, status=status.HTTP_201_CREATED)


class SaleSummaryView(APIView):
    permission_classes = [SalesAccess]
    summary_only = True

    def get(self, request):
        sales = Sale.objects.all()
        return Response({"draft_count": sales.filter(status=Sale.Status.DRAFT).count(),
                         "confirmed_count": sales.filter(status=Sale.Status.CONFIRMED).count()})


class SaleOptionsView(APIView):
    permission_classes = [SalesAccess]
    options_only = True

    def get(self, request):
        customers = Customer.objects.all().order_by("full_name")[:500]
        vehicles = Vehicle.objects.filter(status=Vehicle.Status.AVAILABLE).order_by("make", "model")[:500]
        reservations = Reservation.objects.filter(status=Reservation.Status.ACTIVE, vehicle__status=Vehicle.Status.RESERVED).select_related("vehicle", "customer").order_by("-created_at")[:500]
        import_orders = ImportOrder.objects.filter(status=ImportOrder.Status.READY_FOR_COLLECTION, vehicle__status=Vehicle.Status.AVAILABLE).exclude(sales__isnull=False).select_related("vehicle", "customer").order_by("-updated_at")[:250]
        reps = RepresentativeProfile.objects.filter(business_status=RepresentativeProfile.BusinessStatus.ACTIVE).select_related("user")[:250]
        return Response({"customers": [{"id": x.pk, "full_name": x.full_name} for x in customers],
            "vehicles": [{"reference": x.reference, "name": f"{x.manufacture_year} {x.make} {x.model}", "asking_price_lkr": x.asking_price_lkr} for x in vehicles],
            "reservations": [{"reference": x.reference, "vehicle_reference": x.vehicle.reference, "customer_id": x.customer_id,
                "agreed_price_lkr": x.agreed_price_lkr, "customer_name": x.customer.full_name,
                "vehicle_name": f"{x.vehicle.manufacture_year} {x.vehicle.make} {x.vehicle.model}"} for x in reservations],
            "imports": [{"reference": x.reference, "vehicle_reference": x.vehicle.reference, "customer_name": x.customer.full_name, "vehicle_name": f"{x.vehicle.manufacture_year} {x.vehicle.make} {x.vehicle.model}"} for x in import_orders],
            "representatives": [{"id": x.pk, "reference": x.reference, "name": " ".join(p for p in (x.user.first_name, x.user.last_name) if p) or x.user.username} for x in reps]})


class SaleDetailView(APIView):
    permission_classes = [SalesAccess]

    def get(self, request, reference):
        sale = get_object_or_404(ManagerSalesView().get_queryset(), reference=reference)
        return Response(SaleSerializer(sale).data)


class SaleConfirmView(APIView):
    permission_classes = [SalesAccess]

    def post(self, request, reference):
        try:
            with transaction.atomic():
                sale = Sale.objects.select_for_update().get(reference=reference)
                if sale.status != Sale.Status.DRAFT:
                    return Response({"detail": "Only draft sales can be confirmed."}, status=status.HTTP_409_CONFLICT)
                reservation = None
                import_order = None
                if sale.reservation_id:
                    reservation = Reservation.objects.select_for_update().get(pk=sale.reservation_id)
                if sale.import_order_id:
                    import_order = ImportOrder.objects.select_for_update().get(pk=sale.import_order_id)
                    if (import_order.status != ImportOrder.Status.READY_FOR_COLLECTION or import_order.customer_id != sale.customer_id
                            or import_order.vehicle_id != sale.vehicle_id or import_order.vehicle_id is None):
                        return Response({"detail": "The linked import is no longer eligible for sale confirmation."}, status=status.HTTP_409_CONFLICT)
                vehicle = Vehicle.objects.select_for_update().get(pk=sale.vehicle_id)
                if reservation:
                    if reservation.vehicle_id != vehicle.pk or reservation.customer_id != sale.customer_id or reservation.status != Reservation.Status.ACTIVE or vehicle.status != Vehicle.Status.RESERVED:
                        return Response({"detail": "The linked reservation or vehicle is no longer eligible for confirmation."}, status=status.HTTP_409_CONFLICT)
                elif vehicle.status != Vehicle.Status.AVAILABLE:
                    return Response({"detail": "Only available vehicles can be confirmed without a matching active reservation."}, status=status.HTTP_409_CONFLICT)
                verified_scope = Q(sale=sale)
                if reservation:
                    verified_scope |= Q(reservation=reservation)
                if import_order:
                    verified_scope |= Q(import_order=import_order)
                verified_total = Payment.objects.filter(status=Payment.Status.VERIFIED).filter(verified_scope).aggregate(total=Sum("amount_lkr"))["total"] or Decimal("0.00")
                if verified_total > sale.agreed_price_lkr:
                    return Response({"detail": "Verified payments exceed the agreed sale price; the sale cannot be confirmed."}, status=status.HTTP_409_CONFLICT)
                vehicle.status = Vehicle.Status.SOLD
                vehicle.save(update_fields=["status", "updated_at"])
                if reservation:
                    reservation.status = Reservation.Status.CONVERTED
                    reservation.save(update_fields=["status", "updated_at"])
                sale.status = Sale.Status.CONFIRMED
                sale.confirmed_at = timezone.now()
                sale.save(update_fields=["status", "confirmed_at", "updated_at"])
                AuditEvent.objects.create(actor=request.user, action="sale.confirmed", subject=sale.reference,
                    details={"vehicle_reference": vehicle.reference, "reservation_reference": reservation.reference if reservation else None})
        except Sale.DoesNotExist:
            return Response({"detail": "Sale not found."}, status=status.HTTP_404_NOT_FOUND)
        except IntegrityError:
            return Response({"detail": "This vehicle already has a confirmed sale."}, status=status.HTTP_409_CONFLICT)
        return Response(SaleSerializer(sale).data)


def _handover_readiness_errors(handover):
    errors = {}
    for field, required in (("vehicle_condition_checklist", HANDOVER_CONDITION_CHECKLIST),
                            ("keys_documents_checklist", HANDOVER_KEYS_DOCUMENTS_CHECKLIST)):
        checklist = getattr(handover, field) or {}
        incomplete = [item for item in required if checklist.get(item) is not True]
        if incomplete:
            errors[field] = {"incomplete": incomplete}
    if not handover.delivery_date:
        errors["delivery_date"] = "A delivery date is required before review or finalization."
    if not handover.customer_acknowledgement.strip() or not handover.customer_acknowledged_at:
        errors["customer_acknowledgement"] = "Customer acknowledgement is required before review or finalization."
    return errors


class HandoverCollectionView(APIView):
    permission_classes = [HandoverAccess]
    handover_action = "collection"

    def get(self, request):
        handovers = Handover.objects.select_related("sale__reservation", "customer", "vehicle", "prepared_by", "finalized_by")
        search = request.query_params.get("search", "").strip()
        state = request.query_params.get("status", "")
        if state in Handover.Status.values:
            handovers = handovers.filter(status=state)
        if search:
            handovers = handovers.filter(Q(reference__icontains=search) | Q(sale__reference__icontains=search) |
                Q(customer__full_name__icontains=search) | Q(vehicle__reference__icontains=search) |
                Q(vehicle__make__icontains=search) | Q(vehicle__model__icontains=search))
        return Response(HandoverSerializer(handovers[:250], many=True).data)

    def post(self, request):
        serializer = HandoverPreparationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        sale_reference = data.pop("sale_reference", "").strip()
        evidence = data.get("supporting_evidence")
        if evidence:
            data["evidence_content_type"] = evidence.content_type
        if data.get("customer_acknowledgement", "").strip():
            data["customer_acknowledged_at"] = timezone.now()
        if not sale_reference:
            return Response({"sale_reference": "Select a confirmed sale."}, status=status.HTTP_400_BAD_REQUEST)
        handover = None
        try:
            with transaction.atomic():
                try:
                    sale = Sale.objects.select_for_update().select_related("customer", "vehicle").get(reference=sale_reference)
                except Sale.DoesNotExist:
                    return Response({"sale_reference": "Sale not found."}, status=status.HTTP_404_NOT_FOUND)
                if sale.status != Sale.Status.CONFIRMED:
                    return Response({"sale_reference": "Only confirmed sales can enter the handover workflow."}, status=status.HTTP_409_CONFLICT)
                vehicle = Vehicle.objects.select_for_update().get(pk=sale.vehicle_id)
                if vehicle.status != Vehicle.Status.SOLD:
                    return Response({"sale_reference": "The sale vehicle is not in the sold state required for preparation."}, status=status.HTTP_409_CONFLICT)
                handover = Handover.objects.create(sale=sale, customer=sale.customer, vehicle=vehicle,
                    prepared_by=request.user, **data)
                AuditEvent.objects.create(actor=request.user, action="handover.prepared", subject=handover.reference,
                    details={"sale_reference": sale.reference, "vehicle_reference": vehicle.reference})
        except IntegrityError:
            if evidence and handover and handover.supporting_evidence:
                handover.supporting_evidence.storage.delete(handover.supporting_evidence.name)
            return Response({"detail": "This sale already has a handover record."}, status=status.HTTP_409_CONFLICT)
        return Response(HandoverSerializer(handover).data, status=status.HTTP_201_CREATED)


class HandoverDetailView(APIView):
    permission_classes = [HandoverAccess]
    handover_action = "detail"

    def get(self, request, reference):
        handover = get_object_or_404(Handover.objects.select_related("sale__reservation", "customer", "vehicle", "prepared_by", "finalized_by"), reference=reference)
        return Response(HandoverSerializer(handover).data)

    def patch(self, request, reference):
        try:
            with transaction.atomic():
                handover = get_object_or_404(Handover.objects.select_for_update().select_related("sale"), reference=reference)
                returning_from_review = handover.status == Handover.Status.READY_FOR_REVIEW
                submitting_user = latest_handover_submitter(handover) if returning_from_review else None
                if handover.status == Handover.Status.FINALIZED:
                    return Response({"detail": "Finalized handovers are immutable."}, status=status.HTTP_409_CONFLICT)
                serializer = HandoverPreparationSerializer(data=request.data, partial=True)
                serializer.is_valid(raise_exception=True)
                data = dict(serializer.validated_data)
                data.pop("sale_reference", None)
                evidence = data.get("supporting_evidence")
                if evidence:
                    data["evidence_content_type"] = evidence.content_type
                acknowledgement = data.get("customer_acknowledgement")
                if acknowledgement and (acknowledgement != handover.customer_acknowledgement or not handover.customer_acknowledged_at):
                    handover.customer_acknowledged_at = timezone.now()
                for field, value in data.items():
                    setattr(handover, field, value)
                if handover.status == Handover.Status.READY_FOR_REVIEW:
                    handover.status = Handover.Status.PREPARING
                handover.save()
                event = AuditEvent.objects.create(actor=request.user, action="handover.updated", subject=handover.reference,
                    details={"fields": sorted(key for key in data if key != "supporting_evidence"), "returned_to_preparing": True})
                if returning_from_review:
                    notify_handover_outcome(handover, "returned", request.user, event.pk, submitter=submitting_user)
        except Handover.DoesNotExist:
            return Response({"detail": "Handover not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(HandoverSerializer(handover).data)


class HandoverSubmitView(APIView):
    permission_classes = [HandoverAccess]
    handover_action = "submit"

    def post(self, request, reference):
        try:
            with transaction.atomic():
                handover = get_object_or_404(Handover.objects.select_for_update(), reference=reference)
                if handover.status != Handover.Status.PREPARING:
                    return Response({"detail": "Only preparing handovers can be submitted for review."}, status=status.HTTP_409_CONFLICT)
                errors = _handover_readiness_errors(handover)
                if errors:
                    return Response(errors, status=status.HTTP_400_BAD_REQUEST)
                handover.status = Handover.Status.READY_FOR_REVIEW
                handover.save()
                event = AuditEvent.objects.create(actor=request.user, action="handover.submitted_for_review", subject=handover.reference,
                    details={"sale_reference": handover.sale.reference})
                notify_active_roles((User.Role.CEO, User.Role.MANAGER),
                    f"handover:{handover.pk}:submitted:audit:{event.pk}",
                    "Handover needs review", f"Handover {handover.reference} is ready for review.",
                    "/staff/handovers", exclude_user_ids=(request.user.pk,))
        except Handover.DoesNotExist:
            return Response({"detail": "Handover not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(HandoverSerializer(handover).data)


class HandoverFinalizeView(APIView):
    permission_classes = [HandoverAccess]
    handover_action = "finalize"

    def post(self, request, reference):
        try:
            with transaction.atomic():
                handover = get_object_or_404(Handover.objects.select_for_update(), reference=reference)
                if handover.status != Handover.Status.READY_FOR_REVIEW:
                    return Response({"detail": "Only handovers ready for review can be finalized."}, status=status.HTTP_409_CONFLICT)
                errors = _handover_readiness_errors(handover)
                if errors:
                    return Response(errors, status=status.HTTP_400_BAD_REQUEST)
                sale = Sale.objects.select_for_update().get(pk=handover.sale_id)
                vehicle = Vehicle.objects.select_for_update().get(pk=handover.vehicle_id)
                if sale.status != Sale.Status.CONFIRMED or sale.vehicle_id != vehicle.pk or vehicle.status != Vehicle.Status.SOLD:
                    return Response({"detail": "The confirmed sale and sold vehicle state must still match before finalization."}, status=status.HTTP_409_CONFLICT)
                payment_summary = sale_payment_summary(sale)
                if not payment_summary["down_payment_satisfied"]:
                    return Response({"detail": "The declared reservation down payment must be received and verified before vehicle release."},
                                    status=status.HTTP_409_CONFLICT)
                handover.status = Handover.Status.FINALIZED
                handover.finalized_by = request.user
                handover.finalized_at = timezone.now()
                handover.save()
                vehicle.status = Vehicle.Status.HANDED_OVER
                vehicle.save(update_fields=["status", "updated_at"])
                if sale.import_order_id:
                    import_order = ImportOrder.objects.select_for_update().get(pk=sale.import_order_id)
                    if import_order.status != ImportOrder.Status.READY_FOR_COLLECTION:
                        return Response({"detail": "The linked import is no longer ready for handover."}, status=status.HTTP_409_CONFLICT)
                    import_order.status = ImportOrder.Status.HANDED_OVER
                    import_order.save(update_fields=["status", "updated_at"])
                    ImportMilestone.objects.create(import_order=import_order, kind=ImportMilestone.Kind.FINALIZED_HANDOVER,
                        actor=request.user, customer_description="Vehicle handover completed by SSP.")
                policy = CommissionRule.objects.filter(key="brackets").first()
                effective_day = timezone.localtime(handover.finalized_at).date().isoformat()
                schedule = policy.value if policy and isinstance(policy.value, list) else []
                effective_dates = sorted({b.get("effective_date") for b in schedule if b.get("active") and b.get("effective_date") <= effective_day})
                policy_snapshot = {"policy_key": "brackets", "effective_date": effective_dates[-1] if effective_dates else None,
                                   "sale_price_lkr": str(sale.agreed_price_lkr), "rate_status": "no_matching_rate"}
                rate = None
                if effective_dates:
                    for bracket in schedule:
                        if not bracket.get("active") or bracket.get("effective_date") != effective_dates[-1]: continue
                        low = Decimal(bracket["minimum_lkr"])
                        high = Decimal(bracket["maximum_lkr"]) if bracket.get("maximum_lkr") is not None else None
                        if sale.agreed_price_lkr >= low and (high is None or sale.agreed_price_lkr < high):
                            rate = Decimal(bracket["percentage"])
                            policy_snapshot = {**bracket, "policy_key": "brackets", "rate_status": "matched",
                                               "sale_price_lkr": str(sale.agreed_price_lkr)}
                            break
                recipient_id = getattr(getattr(sale, "representative", None), "user_id", None)
                amount = (sale.agreed_price_lkr * rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if rate is not None else None
                ledger, created = CommissionLedgerEntry.objects.get_or_create(sale=sale, defaults={
                    "handover": handover, "recipient_id": recipient_id, "sale_price_lkr": sale.agreed_price_lkr,
                    "commission_rate_percent": rate, "commission_amount_lkr": amount,
                    "policy_snapshot": policy_snapshot, "created_by": request.user})
                if created:
                    AuditEvent.objects.create(actor=request.user, action="commission.pending_created", subject=sale.reference,
                        details={"handover_reference": handover.reference, "recipient_id": recipient_id,
                                 "rate_status": policy_snapshot["rate_status"], "amount_lkr": str(amount) if amount is not None else None})
                financial_summary = HandoverSerializer(handover).data["financial_summary"]
                event = AuditEvent.objects.create(actor=request.user, action="handover.finalized", subject=handover.reference,
                    details={"sale_reference": sale.reference, "vehicle_reference": vehicle.reference,
                             "outstanding_balance_lkr": str(financial_summary["outstanding_balance_lkr"]),
                             "balance_review_required": financial_summary["balance_review_required"]})
                notify_handover_outcome(handover, "finalized", request.user, event.pk)
        except Handover.DoesNotExist:
            return Response({"detail": "Handover not found."}, status=status.HTTP_404_NOT_FOUND)
        except (Sale.DoesNotExist, Vehicle.DoesNotExist):
            return Response({"detail": "The linked sale or vehicle record was not found."}, status=status.HTTP_409_CONFLICT)
        return Response(HandoverSerializer(handover).data)


class HandoverEvidenceView(APIView):
    permission_classes = [HandoverAccess]
    handover_action = "evidence"

    def get(self, request, reference):
        handover = get_object_or_404(Handover, reference=reference)
        if not handover.supporting_evidence:
            return Response({"detail": "No supporting evidence is attached."}, status=status.HTTP_404_NOT_FOUND)
        response = FileResponse(handover.supporting_evidence.open("rb"),
            content_type=handover.evidence_content_type or "application/octet-stream")
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Disposition"] = f'attachment; filename="handover-evidence-{handover.reference}.bin"'
        response["Cache-Control"] = "private, no-store"
        return response


class HandoverDocumentReceiptView(APIView):
    permission_classes = [HandoverAccess]
    handover_action = "document_receipt"

    def post(self, request, reference):
        with transaction.atomic():
            # Lock the handover row only. ``sale__reservation`` is nullable, so
            # select_related adds an outer join; PostgreSQL rejects a default
            # FOR UPDATE that also tries to lock the nullable joined row.
            handover = get_object_or_404(Handover.objects.select_for_update(of=("self",)).select_related(
                "sale__reservation", "customer", "vehicle"), reference=reference)
            if handover.status != Handover.Status.FINALIZED:
                return Response({"detail": "A customer document receipt can only be issued after an authorized handover is finalized."},
                                status=status.HTTP_409_CONFLICT)
            payment_summary = sale_payment_summary(handover.sale)
            if not payment_summary["down_payment_satisfied"]:
                return Response({"detail": "The required reservation down payment is not fully verified."},
                                status=status.HTTP_409_CONFLICT)
            receipt = HandoverDocumentReceipt.objects.filter(handover=handover).select_related("issued_by").first()
            created = receipt is None
            if created:
                labels = {
                    "keys": "Keys",
                    "registration_documents": "Registration documents",
                    "insurance_documents": "Insurance documents",
                    "service_documents": "Service documents",
                }
                items = [{"key": key, "label": label} for key, label in labels.items()
                         if (handover.keys_documents_checklist or {}).get(key) is True]
                receipt = HandoverDocumentReceipt.objects.create(
                    handover=handover, sale_reference=handover.sale.reference,
                    customer_name=handover.customer.full_name, vehicle_reference=handover.vehicle.reference,
                    vehicle_name=f"{handover.vehicle.manufacture_year} {handover.vehicle.make} {handover.vehicle.model} {handover.vehicle.variant}".strip(),
                    delivery_date=handover.delivery_date, items_handed_over=items,
                    customer_acknowledgement=handover.customer_acknowledgement, issued_by=request.user,
                )
        return Response(HandoverDocumentReceiptSerializer(receipt).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def get(self, request, reference, receipt_reference):
        receipt = get_object_or_404(HandoverDocumentReceipt.objects.select_related("handover", "issued_by"),
            reference=receipt_reference, handover__reference=reference)
        response = HttpResponse(build_handover_document_receipt_pdf(receipt), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{receipt.reference}.pdf"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class PaymentCollectionView(APIView):
    permission_classes = [PaymentAccess]
    payment_action = "collection"

    def get(self, request):
        payments = Payment.objects.select_related("sale__customer", "reservation__customer", "import_order__customer", "recorded_by", "verified_by", "rejected_by")
        status_filter = request.query_params.get("status", "")
        method_filter = request.query_params.get("method", "")
        search = request.query_params.get("search", "").strip()
        if status_filter in Payment.Status.values:
            payments = payments.filter(status=status_filter)
        if method_filter in Payment.Method.values:
            payments = payments.filter(method=method_filter)
        if search:
            payments = payments.filter(Q(reference__icontains=search) | Q(transaction_reference__icontains=search) |
                Q(sale__reference__icontains=search) | Q(reservation__reference__icontains=search) |
                Q(import_order__reference__icontains=search) | Q(sale__customer__full_name__icontains=search) |
                Q(reservation__customer__full_name__icontains=search) | Q(import_order__customer__full_name__icontains=search))
        return Response(PaymentSerializer(payments[:250], many=True).data)

    def post(self, request):
        serializer = PaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        sale_reference = data.pop("sale_reference", "")
        reservation_reference = data.pop("reservation_reference", "")
        import_reference = data.pop("import_reference", "")
        evidence = data.get("evidence")
        if evidence:
            data["evidence_content_type"] = evidence.content_type
        payment = None
        evidence_name = None
        try:
            with transaction.atomic():
                sale = None
                reservation = None
                import_order = None
                if sale_reference:
                    try:
                        sale = Sale.objects.select_for_update().get(reference=sale_reference)
                    except Sale.DoesNotExist:
                        return Response({"sale_reference": "Sale not found."}, status=status.HTTP_404_NOT_FOUND)
                    if sale.reservation_id:
                        reservation = Reservation.objects.select_for_update().get(pk=sale.reservation_id)
                elif reservation_reference:
                    try:
                        reservation_id = Reservation.objects.only("pk").get(reference=reservation_reference).pk
                    except Reservation.DoesNotExist:
                        return Response({"reservation_reference": "Reservation not found."}, status=status.HTTP_404_NOT_FOUND)
                    linked_sale_id = Sale.objects.filter(reservation_id=reservation_id).values_list("pk", flat=True).first()
                    if linked_sale_id:
                        sale = Sale.objects.select_for_update().get(pk=linked_sale_id)
                    reservation = Reservation.objects.select_for_update().get(pk=reservation_id)
                    if reservation.status != Reservation.Status.ACTIVE:
                        return Response({"reservation_reference": "Payments can only be recorded against an active reservation."}, status=status.HTTP_409_CONFLICT)
                else:
                    try:
                        import_order = ImportOrder.objects.select_for_update().get(reference=import_reference)
                    except ImportOrder.DoesNotExist:
                        return Response({"import_reference": "Import order not found."}, status=status.HTTP_404_NOT_FOUND)
                payment = Payment(sale=sale, reservation=reservation if reservation_reference else None,
                    import_order=import_order,
                    recorded_by=request.user, **data)
                payment.save()
                evidence_name = payment.evidence.name if payment.evidence else None
                AuditEvent.objects.create(actor=request.user, action="payment.recorded", subject=payment.reference,
                    details={"status": payment.status, "method": payment.method,
                             "sale_reference": sale.reference if sale else None,
                             "reservation_reference": reservation.reference if reservation_reference else None,
                             "import_reference": import_order.reference if import_order else None,
                             "evidence_attached": bool(payment.evidence)})
                notify_active_roles((User.Role.CEO, User.Role.MANAGER), f"payment:{payment.pk}:review-requested",
                    "Payment needs review", f"Payment {payment.reference} is waiting for verification.",
                    "/staff/payments", exclude_user_ids=(request.user.pk,))
        except IntegrityError:
            if evidence_name:
                payment.evidence.storage.delete(evidence_name)
            elif payment and payment.evidence and payment.evidence.name:
                payment.evidence.storage.delete(payment.evidence.name)
            return Response({"detail": "This transaction reference has already been recorded."}, status=status.HTTP_409_CONFLICT)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class PaymentDashboardSummaryView(APIView):
    permission_classes = [PaymentAccess]

    def get(self, request):
        totals = Payment.objects.aggregate(
            pending_count=Count("id", filter=Q(status=Payment.Status.PENDING)),
            verified_count=Count("id", filter=Q(status=Payment.Status.VERIFIED)),
            rejected_count=Count("id", filter=Q(status=Payment.Status.REJECTED)),
            pending_amount_lkr=Sum("amount_lkr", filter=Q(status=Payment.Status.PENDING)),
            verified_amount_lkr=Sum("amount_lkr", filter=Q(status=Payment.Status.VERIFIED)),
        )
        totals["pending_amount_lkr"] = totals["pending_amount_lkr"] or Decimal("0.00")
        totals["verified_amount_lkr"] = totals["verified_amount_lkr"] or Decimal("0.00")
        return Response(totals)


class PaymentDetailView(APIView):
    permission_classes = [PaymentAccess]

    def get(self, request, reference):
        payment = get_object_or_404(Payment.objects.select_related("sale__customer", "reservation__customer", "import_order__customer", "recorded_by", "verified_by", "rejected_by"), reference=reference)
        return Response(PaymentSerializer(payment).data)


class PaymentEvidenceView(APIView):
    permission_classes = [PaymentAccess]

    def get(self, request, reference):
        payment = get_object_or_404(Payment, reference=reference)
        if not payment.evidence:
            return Response({"detail": "No payment evidence is attached."}, status=status.HTTP_404_NOT_FOUND)
        response = FileResponse(payment.evidence.open("rb"), content_type=payment.evidence_content_type or "application/octet-stream")
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Disposition"] = f'attachment; filename="payment-evidence-{payment.reference}.bin"'
        response["Cache-Control"] = "private, no-store"
        return response


class PaymentVerifyView(APIView):
    permission_classes = [PaymentAccess]
    payment_action = "verify"

    def post(self, request, reference):
        try:
            with transaction.atomic():
                payment = Payment.objects.select_for_update().get(reference=reference)
                if payment.status != Payment.Status.PENDING:
                    return Response({"detail": "Only pending payments can be verified."}, status=status.HTTP_409_CONFLICT)
                if payment.recorded_by_id == request.user.pk:
                    return Response({"detail": "You cannot verify a payment you recorded."}, status=status.HTTP_403_FORBIDDEN)

                reservation = None
                sale = None
                import_order = None
                ceiling = None
                if payment.sale_id:
                    sale = Sale.objects.select_for_update().get(pk=payment.sale_id)
                    if sale.reservation_id:
                        reservation = Reservation.objects.select_for_update().get(pk=sale.reservation_id)
                    amount_scope = Q(sale=sale) | Q(reservation=reservation) if reservation else Q(sale=sale)
                    ceiling = sale.agreed_price_lkr
                elif payment.reservation_id:
                    linked_sale_id = Sale.objects.filter(reservation_id=payment.reservation_id).values_list("pk", flat=True).first()
                    if linked_sale_id:
                        sale = Sale.objects.select_for_update().get(pk=linked_sale_id)
                        reservation = Reservation.objects.select_for_update().get(pk=payment.reservation_id)
                    else:
                        reservation = Reservation.objects.select_for_update().get(pk=payment.reservation_id)
                        # A sale draft can be linked after the initial lookup. The reservation row lock
                        # prevents its payment verifications from passing while this balance is checked.
                        linked_sale_id = Sale.objects.filter(reservation_id=reservation.pk).values_list("pk", flat=True).first()
                        if linked_sale_id:
                            sale = Sale.objects.get(pk=linked_sale_id)
                    if reservation.status == Reservation.Status.RELEASED:
                        return Response({"detail": "Payments on released reservations cannot be verified."}, status=status.HTTP_409_CONFLICT)
                    amount_scope = Q(reservation=reservation) | Q(sale=sale) if sale else Q(reservation=reservation)
                    ceiling = sale.agreed_price_lkr if sale else reservation.agreed_price_lkr
                else:
                    import_order = ImportOrder.objects.select_for_update().get(pk=payment.import_order_id)
                    amount_scope = Q(import_order=import_order)
                    sale = Sale.objects.filter(import_order=import_order).first()
                    if sale:
                        amount_scope |= Q(sale=sale)
                        ceiling = sale.agreed_price_lkr

                verified_total = Payment.objects.filter(status=Payment.Status.VERIFIED).filter(amount_scope).aggregate(total=Sum("amount_lkr"))["total"] or Decimal("0.00")
                if ceiling is not None and verified_total + payment.amount_lkr > ceiling:
                    return Response({"detail": "Verifying this payment would exceed the agreed transaction price."}, status=status.HTTP_409_CONFLICT)
                payment.status = Payment.Status.VERIFIED
                payment.verified_by = request.user
                payment.verified_at = timezone.now()
                payment.save(update_fields=["status", "verified_by", "verified_at"])
                AuditEvent.objects.create(actor=request.user, action="payment.verified", subject=payment.reference,
                    details={"sale_reference": sale.reference if sale else None,
                             "reservation_reference": reservation.reference if reservation else None,
                             "import_reference": import_order.reference if import_order else None})
                create_notifications([payment.recorded_by], f"payment:{payment.pk}:decision:verified",
                    "Payment verified", f"Payment {payment.reference} was verified.", "/staff/payments")
        except Payment.DoesNotExist:
            return Response({"detail": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(PaymentSerializer(payment).data)


class PaymentRejectView(APIView):
    permission_classes = [PaymentAccess]
    payment_action = "reject"

    def post(self, request, reference):
        serializer = PaymentRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                payment = Payment.objects.select_for_update().get(reference=reference)
                if payment.status != Payment.Status.PENDING:
                    return Response({"detail": "Only pending payments can be rejected."}, status=status.HTTP_409_CONFLICT)
                payment.status = Payment.Status.REJECTED
                payment.rejected_by = request.user
                payment.rejected_at = timezone.now()
                payment.rejection_reason = serializer.validated_data["rejection_reason"]
                payment.save(update_fields=["status", "rejected_by", "rejected_at", "rejection_reason"])
                AuditEvent.objects.create(actor=request.user, action="payment.rejected", subject=payment.reference,
                    details={"rejection_reason": payment.rejection_reason})
                create_notifications([payment.recorded_by], f"payment:{payment.pk}:decision:rejected",
                    "Payment rejected", f"Payment {payment.reference} was rejected.", "/staff/payments")
        except Payment.DoesNotExist:
            return Response({"detail": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(PaymentSerializer(payment).data)


class SalePaymentSummaryView(APIView):
    permission_classes = [PaymentAccess]

    def get(self, request, reference):
        sale = get_object_or_404(Sale.objects.select_related("reservation", "import_order"), reference=reference)
        scope = Q(sale=sale)
        if sale.reservation_id:
            scope |= Q(reservation_id=sale.reservation_id)
        if sale.import_order_id:
            scope |= Q(import_order_id=sale.import_order_id)
        totals = Payment.objects.filter(scope).aggregate(
            verified=Sum("amount_lkr", filter=Q(status=Payment.Status.VERIFIED)),
            pending=Sum("amount_lkr", filter=Q(status=Payment.Status.PENDING)))
        received = totals["verified"] or Decimal("0.00")
        return Response({"sale_reference": sale.reference, "sale_price_lkr": sale.agreed_price_lkr,
            "verified_received_lkr": received, "pending_verification_lkr": totals["pending"] or Decimal("0.00"),
            "outstanding_balance_lkr": max(Decimal("0.00"), sale.agreed_price_lkr - received)})


class ReservationPaymentSummaryView(APIView):
    permission_classes = [ReservationAccess]

    def get(self, request, reference):
        reservation = get_object_or_404(Reservation, reference=reference)
        sale = Sale.objects.filter(reservation=reservation).first()
        scope = Q(reservation=reservation) | Q(sale=sale) if sale else Q(reservation=reservation)
        totals = Payment.objects.filter(scope).aggregate(
            verified=Sum("amount_lkr", filter=Q(status=Payment.Status.VERIFIED)),
            pending=Sum("amount_lkr", filter=Q(status=Payment.Status.PENDING)))
        received = totals["verified"] or Decimal("0.00")
        agreed = sale.agreed_price_lkr if sale else reservation.agreed_price_lkr
        return Response({"reservation_reference": reservation.reference,
            "advance_declared_unverified_lkr": reservation.advance_amount_lkr,
            "verified_received_lkr": received, "pending_verification_lkr": totals["pending"] or Decimal("0.00"),
            "outstanding_balance_lkr": max(Decimal("0.00"), agreed - received),
            "linked_sale_reference": sale.reference if sale else None})


def _expire_due_quotations(queryset):
    due = list(queryset.filter(status=Quotation.Status.ISSUED, expiry_date__lt=timezone.localdate()).values_list("pk", "reference"))
    if not due:
        return
    with transaction.atomic():
        ids = [pk for pk, _ in due]
        changed = set(Quotation.objects.filter(pk__in=ids, status=Quotation.Status.ISSUED,
            expiry_date__lt=timezone.localdate()).values_list("reference", flat=True))
        Quotation.objects.filter(reference__in=changed, status=Quotation.Status.ISSUED).update(status=Quotation.Status.EXPIRED)
        AuditEvent.objects.bulk_create([AuditEvent(action="quotation.expired", subject=ref, details={}) for ref in changed])


def _quotation_snapshot(quotation):
    selected_terms = quotation.finance_terms or ([quotation.finance_term] if quotation.finance_term else [])
    finance_estimates = [calculate_finance_estimate(term, quotation.vehicle_selling_price_lkr,
        quotation.finance_down_payment_lkr) for term in selected_terms]
    return {"reference": quotation.reference, "issue_date": quotation.issue_date.isoformat(),
            "expiry_date": quotation.expiry_date.isoformat(),
            "customer": {"full_name": quotation.customer.full_name, "email": quotation.customer.email, "phone": quotation.customer.phone},
            "vehicle_description": quotation.vehicle_description,
            "vehicle_specifications": quotation.vehicle_specifications,
            "vehicle_selling_price_lkr": str(quotation.vehicle_selling_price_lkr),
            "additional_charges_lkr": str(quotation.additional_charges_lkr),
            "discount_lkr": str(quotation.discount_lkr), "quotation_total_lkr": str(quotation.quotation_total_lkr),
            "customer_terms": quotation.customer_terms, "finance_estimates": finance_estimates,
            "finance_estimate": finance_estimates[0] if finance_estimates else None}


class QuotationFinanceOptionsView(APIView):
    permission_classes = [QuotationAccess]

    def get(self, request):
        return Response(finance_options())


class QuotationCollectionView(APIView):
    permission_classes = [QuotationAccess]
    quotation_action = "collection"

    def get(self, request):
        queryset = Quotation.objects.select_related("customer", "vehicle", "import_order", "responsible_staff")
        _expire_due_quotations(queryset)
        query = request.query_params.get("search", "").strip()
        state = request.query_params.get("status", "")
        if state in Quotation.Status.values:
            queryset = queryset.filter(status=state)
        if query:
            queryset = queryset.filter(Q(reference__icontains=query) | Q(customer__full_name__icontains=query) |
                Q(vehicle_description__icontains=query) | Q(vehicle__reference__icontains=query) |
                Q(import_order__reference__icontains=query))
        return Response(QuotationSerializer(queryset[:250], many=True).data)

    def post(self, request):
        serializer = QuotationDraftSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quotation = serializer.save(responsible_staff=request.user)
        AuditEvent.objects.create(actor=request.user, action="quotation.created", subject=quotation.reference,
                                  details={"status": quotation.status, "quotation_total_lkr": str(quotation.quotation_total_lkr)})
        return Response(QuotationSerializer(quotation).data, status=status.HTTP_201_CREATED)


class QuotationDetailView(APIView):
    permission_classes = [QuotationAccess]
    quotation_action = "write"

    def get_object(self, reference):
        quotation = get_object_or_404(Quotation.objects.select_related("customer", "vehicle", "import_order", "responsible_staff", "voided_by"), reference=reference)
        _expire_due_quotations(Quotation.objects.filter(pk=quotation.pk))
        quotation.refresh_from_db()
        return quotation

    def get(self, request, reference):
        return Response(QuotationSerializer(self.get_object(reference)).data)

    def patch(self, request, reference):
        try:
            with transaction.atomic():
                quotation = get_object_or_404(Quotation.objects.select_for_update(), reference=reference)
                if quotation.status != Quotation.Status.DRAFT:
                    return Response({"detail": "Only draft quotations can be edited."}, status=status.HTTP_409_CONFLICT)
                serializer = QuotationDraftSerializer(quotation, data=request.data, partial=True)
                serializer.is_valid(raise_exception=True)
                quotation = serializer.save()
                AuditEvent.objects.create(actor=request.user, action="quotation.draft_updated", subject=quotation.reference,
                                          details={"quotation_total_lkr": str(quotation.quotation_total_lkr)})
        except Quotation.DoesNotExist:
            return Response({"detail": "Quotation not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(QuotationSerializer(quotation).data)


class QuotationIssueView(APIView):
    permission_classes = [QuotationAccess]
    quotation_action = "issue"

    def post(self, request, reference):
        try:
            with transaction.atomic():
                quotation = get_object_or_404(Quotation.objects.select_for_update().select_related("customer"), reference=reference)
                if quotation.status != Quotation.Status.DRAFT:
                    return Response({"detail": "Only draft quotations can be issued."}, status=status.HTTP_409_CONFLICT)
                if quotation.expiry_date < timezone.localdate():
                    return Response({"expiry_date": "An expired draft cannot be issued."}, status=status.HTTP_400_BAD_REQUEST)
                quotation.status = Quotation.Status.ISSUED
                quotation.issued_at = timezone.now()
                quotation.issued_snapshot = _quotation_snapshot(quotation)
                quotation.save()
                AuditEvent.objects.create(actor=request.user, action="quotation.issued", subject=quotation.reference,
                    details={"quotation_total_lkr": str(quotation.quotation_total_lkr), "issue_date": quotation.issue_date.isoformat()})
        except Quotation.DoesNotExist:
            return Response({"detail": "Quotation not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(QuotationSerializer(quotation).data)


class QuotationVoidView(APIView):
    permission_classes = [QuotationAccess]
    quotation_action = "void"

    def post(self, request, reference):
        reason = request.data.get("reason", "").strip() if isinstance(request.data.get("reason", ""), str) else ""
        if not reason:
            return Response({"reason": "A void reason is required."}, status=status.HTTP_400_BAD_REQUEST)
        if len(reason) > 1000:
            return Response({"reason": "Reason must be 1000 characters or fewer."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                quotation = get_object_or_404(Quotation.objects.select_for_update(), reference=reference)
                if quotation.status not in (Quotation.Status.ISSUED, Quotation.Status.EXPIRED):
                    return Response({"detail": "Only issued or expired quotations can be voided."}, status=status.HTTP_409_CONFLICT)
                quotation.status = Quotation.Status.VOIDED
                quotation.voided_by = request.user
                quotation.voided_at = timezone.now()
                quotation.void_reason = reason
                quotation.save()
                AuditEvent.objects.create(actor=request.user, action="quotation.voided", subject=quotation.reference,
                    details={"reason": reason})
        except Quotation.DoesNotExist:
            return Response({"detail": "Quotation not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(QuotationSerializer(quotation).data)


class QuotationPDFView(APIView):
    permission_classes = [QuotationAccess]

    def get(self, request, reference):
        quotation = get_object_or_404(Quotation.objects.select_related("customer"), reference=reference)
        _expire_due_quotations(Quotation.objects.filter(pk=quotation.pk))
        quotation.refresh_from_db()
        if not quotation.issued_snapshot:
            return Response({"detail": "Only issued quotations have a downloadable PDF."}, status=status.HTTP_409_CONFLICT)
        response = HttpResponse(build_quotation_pdf(quotation.issued_snapshot), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{quotation.reference}.pdf"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class ImportPaymentSummaryView(APIView):
    permission_classes = [PaymentAccess]

    def get(self, request, reference):
        order = get_object_or_404(ImportOrder, reference=reference)
        totals = Payment.objects.filter(import_order=order).aggregate(
            verified=Sum("amount_lkr", filter=Q(status=Payment.Status.VERIFIED)),
            pending=Sum("amount_lkr", filter=Q(status=Payment.Status.PENDING)),
            rejected=Sum("amount_lkr", filter=Q(status=Payment.Status.REJECTED)),
            verified_count=Count("id", filter=Q(status=Payment.Status.VERIFIED)),
            pending_count=Count("id", filter=Q(status=Payment.Status.PENDING)),
            rejected_count=Count("id", filter=Q(status=Payment.Status.REJECTED)),
        )
        return Response({"import_reference": order.reference,
            "verified_amount_lkr": totals["verified"] or Decimal("0.00"),
            "pending_amount_lkr": totals["pending"] or Decimal("0.00"),
            "rejected_amount_lkr": totals["rejected"] or Decimal("0.00"),
            "verified_count": totals["verified_count"], "pending_count": totals["pending_count"],
            "rejected_count": totals["rejected_count"]})


class StaffInventoryView(APIView):
    permission_classes = [InventoryAccess]

    def get(self, request):
        vehicles = Vehicle.objects.prefetch_related("photos").all()
        return Response(StaffVehicleSerializer(vehicles, many=True, context={"request": request}).data)

    def post(self, request):
        serializer = StaffVehicleSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        vehicle = serializer.save()
        AuditEvent.objects.create(actor=request.user, action="inventory.vehicle.created", subject=vehicle.reference,
                                  details={"status": vehicle.status, "visibility": vehicle.visibility})
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
        old_status = vehicle.status
        serializer = StaffVehicleSerializer(vehicle, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        vehicle = serializer.save()
        AuditEvent.objects.create(actor=request.user, action="inventory.vehicle.updated", subject=vehicle.reference)
        if vehicle.status != old_status:
            AuditEvent.objects.create(actor=request.user, action="inventory.vehicle.status_changed", subject=vehicle.reference,
                                      details={"from": old_status, "to": vehicle.status})
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
        vehicles = Vehicle.objects.filter(visibility=Vehicle.Visibility.PUBLISHED,
                                           status=Vehicle.Status.AVAILABLE).prefetch_related("photos")
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
                                    reference=reference, visibility=Vehicle.Visibility.PUBLISHED,
                                    status=Vehicle.Status.AVAILABLE)
        return Response(PublicVehicleSerializer(vehicle, context={"request": request}).data)


class VehiclePhotoView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, photo_id):
        photo = get_object_or_404(VehiclePhoto.objects.select_related("vehicle"), pk=photo_id)
        if photo.vehicle.visibility != Vehicle.Visibility.PUBLISHED or photo.vehicle.status != Vehicle.Status.AVAILABLE:
            if not request.user.is_authenticated or request.user.role not in {"staff", "ceo", "manager"}:
                from rest_framework.exceptions import NotFound
                raise NotFound()
        response = FileResponse(photo.image.open("rb"), content_type=photo.content_type)
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Disposition"] = f'inline; filename="vehicle-photo-{photo.pk}"'
        # Do not let a formerly published image remain cached after unpublishing.
        response["Cache-Control"] = "private, no-store"
        return response


class StaffImportsView(APIView):
    permission_classes = [ImportAccess]

    def get(self, request, reference=None):
        qs = ImportOrder.objects.select_related("customer", "vehicle", "responsible_staff").prefetch_related(
            "milestones", Prefetch("bl_requests", queryset=BLApprovalRequest.objects.select_related("requested_by", "decided_by")))
        status_filter = request.query_params.get("status", "")
        search = request.query_params.get("search", "").strip()
        if reference:
            order = get_object_or_404(qs, reference=reference)
            data = ImportOrderSerializer(order, context={"request": request}).data
            data["milestones"] = ImportMilestoneSerializer(order.milestones.select_related("actor"), many=True).data
            data["bl_requests"] = BLApprovalRequestSerializer(order.bl_requests.all(), many=True).data
            return Response(data)
        if status_filter in ImportOrder.Status.values:
            qs = qs.filter(status=status_filter)
        if search:
            qs = qs.filter(Q(reference__icontains=search) | Q(customer__full_name__icontains=search) |
                Q(vehicle_description__icontains=search) | Q(vehicle__reference__icontains=search))
        orders = list(qs[:250])
        data = ImportOrderSerializer(orders, many=True, context={"request": request}).data
        for record, order in zip(data, orders):
            record["bl_requests"] = BLApprovalRequestSerializer(order.bl_requests.all(), many=True).data
        return Response(data)

    def post(self, request):
        serializer = ImportOrderSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        order = serializer.save(responsible_staff=request.user)
        AuditEvent.objects.create(actor=request.user, action="import.created", subject=order.reference,
                                  details={"customer_id": order.customer_id, "vehicle_id": order.vehicle_id})
        return Response(ImportOrderSerializer(order, context={"request": request}).data, status=status.HTTP_201_CREATED)

    def patch(self, request, reference=None):
        if not reference:
            return Response({"detail": "An import reference is required."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
        with transaction.atomic():
            order = get_object_or_404(ImportOrder.objects.select_for_update(of=("self",)).select_related("customer", "vehicle", "responsible_staff"), reference=reference)
            serializer = ImportOrderSerializer(order, data=request.data, partial=True, context={"request": request})
            serializer.is_valid(raise_exception=True)
            order = serializer.save()
            AuditEvent.objects.create(actor=request.user, action="import.updated", subject=order.reference,
                                      details={"updated_fields": sorted(request.data.keys())})
        return Response(ImportOrderSerializer(order, context={"request": request}).data)


class ImportSummaryView(APIView):
    permission_classes = [ImportAccess]

    def get(self, request):
        counts = {row["status"]: row["count"] for row in ImportOrder.objects.values("status").annotate(count=Count("id"))}
        return Response({"total_count": sum(counts.values()), "status_counts": counts,
                         "pending_bl_approval_count": BLApprovalRequest.objects.filter(status=BLApprovalRequest.Status.PENDING).count()})


class ImportMilestoneCollectionView(APIView):
    permission_classes = [ImportAccess]

    def get(self, request, reference):
        order = get_object_or_404(ImportOrder, reference=reference)
        return Response(ImportMilestoneSerializer(order.milestones.select_related("actor"), many=True).data)

    def post(self, request, reference):
        serializer = ImportMilestoneCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        kind = data.pop("kind")
        payment_reference = data.pop("payment_reference", "")
        if kind == ImportMilestone.Kind.FINALIZED_HANDOVER:
            return Response({"detail": "Finalized handover is reserved for the handover workflow."}, status=status.HTTP_501_NOT_IMPLEMENTED)
        status_for_kind = {
            ImportMilestone.Kind.BOOKING_CONFIRMED: ImportOrder.Status.BOOKING_CONFIRMED,
            ImportMilestone.Kind.LC_OPENED: ImportOrder.Status.LC_OPENED,
            ImportMilestone.Kind.BL_ISSUED: ImportOrder.Status.BL_ISSUED,
            ImportMilestone.Kind.SHIPPING: ImportOrder.Status.SHIPPING,
            ImportMilestone.Kind.ARRIVAL: ImportOrder.Status.ARRIVED,
            ImportMilestone.Kind.CUSTOMS_CLEARANCE: ImportOrder.Status.CUSTOMS_CLEARANCE,
            ImportMilestone.Kind.READY_FOR_COLLECTION: ImportOrder.Status.READY_FOR_COLLECTION,
        }
        prerequisites = {
            ImportMilestone.Kind.LC_OPENED: ImportMilestone.Kind.BOOKING_CONFIRMED,
            ImportMilestone.Kind.BL_ISSUED: ImportMilestone.Kind.LC_OPENED,
            ImportMilestone.Kind.SHIPPING: ImportMilestone.Kind.BL_ISSUED,
            ImportMilestone.Kind.ARRIVAL: ImportMilestone.Kind.SHIPPING,
            ImportMilestone.Kind.CUSTOMS_CLEARANCE: ImportMilestone.Kind.ARRIVAL,
            ImportMilestone.Kind.READY_FOR_COLLECTION: ImportMilestone.Kind.CUSTOMS_CLEARANCE,
        }
        try:
            with transaction.atomic():
                order = get_object_or_404(ImportOrder.objects.select_for_update(of=("self",)).select_related("customer", "vehicle"), reference=reference)
                if order.milestones.filter(kind=kind).exists():
                    return Response({"detail": "This milestone has already been recorded."}, status=status.HTTP_409_CONFLICT)
                prerequisite = prerequisites.get(kind)
                if prerequisite and not order.milestones.filter(kind=prerequisite).exists():
                    return Response({"detail": "The preceding operational milestone must be recorded first."}, status=status.HTTP_409_CONFLICT)
                payment = None
                if kind == ImportMilestone.Kind.PAYMENT_VERIFIED:
                    payment = get_object_or_404(Payment.objects.select_for_update(of=("self",)).select_related("import_order"), reference=payment_reference)
                    if payment.status != Payment.Status.VERIFIED or payment.import_order_id != order.pk:
                        return Response({"detail": "The payment must already be verified and linked to this import order."}, status=status.HTTP_409_CONFLICT)
                if kind == ImportMilestone.Kind.BL_ISSUED and not order.bl_requests.filter(status=BLApprovalRequest.Status.APPROVED).exists():
                    return Response({"detail": "CEO approval is required before a BL can be recorded as issued."}, status=status.HTTP_409_CONFLICT)
                milestone = ImportMilestone.objects.create(import_order=order, kind=kind, actor=request.user, payment=payment, **data)
                new_status = status_for_kind.get(kind)
                if new_status:
                    order.status = new_status
                    order.save(update_fields=["status", "updated_at"])
                AuditEvent.objects.create(actor=request.user, action="import.milestone.recorded", subject=order.reference,
                    details={"milestone": kind, "payment_reference": payment.reference if payment else None})
        except IntegrityError:
            return Response({"detail": "This milestone has already been recorded."}, status=status.HTTP_409_CONFLICT)
        return Response(ImportMilestoneSerializer(milestone).data, status=status.HTTP_201_CREATED)


class ImportBLRequestCollectionView(APIView):
    permission_classes = [ImportAccess]
    bl_collection = True

    def get(self, request, reference):
        order = get_object_or_404(ImportOrder, reference=reference)
        return Response(BLApprovalRequestSerializer(order.bl_requests.select_related("requested_by", "decided_by"), many=True).data)

    def post(self, request, reference):
        serializer = BLApprovalRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                order = get_object_or_404(ImportOrder.objects.select_for_update(), reference=reference)
                approval = BLApprovalRequest.objects.create(import_order=order, requested_by=request.user, **serializer.validated_data)
                AuditEvent.objects.create(actor=request.user, action="import.bl_approval_requested", subject=approval.reference,
                                          details={"import_reference": order.reference})
                notify_active_roles((User.Role.CEO,), f"bl-request:{approval.pk}:requested",
                    "BL approval requested", f"BL approval {approval.reference} is waiting for review.",
                    "/staff/bl-requests", exclude_user_ids=(request.user.pk,))
        except IntegrityError:
            return Response({"detail": "A BL approval request is already pending for this import."}, status=status.HTTP_409_CONFLICT)
        return Response(BLApprovalRequestSerializer(approval).data, status=status.HTTP_201_CREATED)


class ImportBLRequestDecisionView(APIView):
    permission_classes = [ImportAccess]
    bl_decision = True

    def post(self, request, request_id):
        serializer = BLApprovalDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            approval = get_object_or_404(BLApprovalRequest.objects.select_for_update().select_related("import_order"), pk=request_id)
            if approval.status != BLApprovalRequest.Status.PENDING:
                return Response({"detail": "This BL approval request has already been processed."}, status=status.HTTP_409_CONFLICT)
            approval.status = serializer.validated_data["decision"]
            approval.rejection_reason = serializer.validated_data.get("rejection_reason", "")
            approval.decided_by = request.user
            approval.decided_at = timezone.now()
            approval.save(update_fields=["status", "rejection_reason", "decided_by", "decided_at"])
            AuditEvent.objects.create(actor=request.user, action=f"import.bl_approval_{approval.status}", subject=approval.reference,
                details={"import_reference": approval.import_order.reference, "rejection_reason": approval.rejection_reason})
            decision = "approved" if approval.status == BLApprovalRequest.Status.APPROVED else "rejected"
            create_notifications([approval.requested_by], f"bl-request:{approval.pk}:decision:{approval.status}",
                f"BL approval {decision}", f"BL approval {approval.reference} was {decision}.", "/staff/imports")
        return Response(BLApprovalRequestSerializer(approval).data)


class ImportTrackingAccessView(APIView):
    permission_classes = [ImportAccess]

    def post(self, request, reference):
        with transaction.atomic():
            order = get_object_or_404(ImportOrder.objects.select_for_update(), reference=reference)
            try:
                access = ImportTrackingAccess.objects.select_for_update().get(import_order=order)
                action = "import.tracking_access_rotated"
            except ImportTrackingAccess.DoesNotExist:
                access = ImportTrackingAccess(import_order=order, pin_hash="")
                action = "import.tracking_access_issued"
            pin = access.issue_pin()
            access.save()
            AuditEvent.objects.create(actor=request.user, action=action, subject=order.reference,
                                      details={"tracking_reference": access.tracking_reference})
        return Response({"tracking_reference": access.tracking_reference, "pin": pin, "issued_at": access.pin_changed_at})


class PublicImportTrackingView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ImportTrackingThrottle]

    def post(self, request):
        tracking_reference = str(request.data.get("tracking_reference", "")).strip()
        pin = str(request.data.get("pin", ""))
        if len(tracking_reference) > 32 or len(pin) > 128:
            return Response({"detail": "Invalid tracking reference or PIN."}, status=status.HTTP_404_NOT_FOUND)
        access = ImportTrackingAccess.objects.select_related("import_order").filter(tracking_reference=tracking_reference).first()
        if not access or not pin or not access.check_pin(pin):
            return Response({"detail": "Invalid tracking reference or PIN."}, status=status.HTTP_404_NOT_FOUND)
        order = access.import_order
        milestones = order.milestones.order_by("occurred_at", "id")
        return Response({"tracking_reference": access.tracking_reference, "import_reference": order.reference,
            "status": order.status, "estimated_arrival": order.estimated_arrival,
            "customer_updates": order.customer_updates,
            "milestones": [{"kind": item.kind, "occurred_at": item.occurred_at,
                            "description": item.customer_description} for item in milestones]})


class StaffReservationsView(APIView):
    permission_classes = [ReservationAccess]

    def get(self, request):
        reservations = Reservation.objects.select_related("customer", "vehicle", "representative__user", "responsible_staff", "released_by")
        status_filter = request.query_params.get("status", "")
        search = request.query_params.get("search", "").strip()
        if status_filter in Reservation.Status.values:
            reservations = reservations.filter(status=status_filter)
        if search:
            reservations = reservations.filter(Q(reference__icontains=search) | Q(customer__full_name__icontains=search) |
                Q(customer__phone__icontains=search) | Q(customer__email__icontains=search) |
                Q(vehicle__reference__icontains=search) | Q(vehicle__make__icontains=search) | Q(vehicle__model__icontains=search) |
                Q(representative__user__first_name__icontains=search) | Q(representative__user__last_name__icontains=search))
        return Response(ReservationSerializer(reservations[:250], many=True).data)

    def post(self, request):
        serializer = ReservationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            with transaction.atomic():
                vehicle = Vehicle.objects.select_for_update().get(reference=data["vehicle_reference"])
                if vehicle.status != Vehicle.Status.AVAILABLE:
                    return Response({"detail": "This vehicle is no longer available to reserve."}, status=status.HTTP_409_CONFLICT)
                vehicle.status = Vehicle.Status.RESERVED
                vehicle.save(update_fields=["status", "updated_at"])
                reservation = Reservation.objects.create(vehicle=vehicle, customer=data["customer"],
                    representative=data.get("representative"), responsible_staff=request.user,
                    agreed_price_lkr=data["agreed_price_lkr"], advance_amount_lkr=data["advance_amount_lkr"],
                    notes=data.get("notes", ""))
                AuditEvent.objects.create(actor=request.user, action="reservation.created", subject=reservation.reference,
                    details={"vehicle_reference": vehicle.reference, "status": reservation.status,
                             "advance_status": "unverified" if reservation.advance_amount_lkr else "not_recorded"})
        except Vehicle.DoesNotExist:
            return Response({"vehicle_reference": "Vehicle not found."}, status=status.HTTP_404_NOT_FOUND)
        except IntegrityError:
            return Response({"detail": "An active reservation already exists for this vehicle."}, status=status.HTTP_409_CONFLICT)
        return Response(ReservationSerializer(reservation).data, status=status.HTTP_201_CREATED)


class StaffReservationSummaryView(APIView):
    permission_classes = [ReservationAccess]

    def get(self, request):
        active = Reservation.objects.filter(status=Reservation.Status.ACTIVE)
        released = Reservation.objects.filter(status=Reservation.Status.RELEASED)
        return Response({"active_count": active.count(), "released_count": released.count(),
                         "advance_unverified_total_lkr": active.filter(advance_amount_lkr__gt=0).aggregate(total=Sum("advance_amount_lkr"))["total"] or Decimal("0.00")})


class StaffReservationOptionsView(APIView):
    permission_classes = [ReservationAccess]

    def get(self, request):
        customers = Customer.objects.all().order_by("full_name")[:500]
        vehicles = Vehicle.objects.filter(status=Vehicle.Status.AVAILABLE).order_by("make", "model")[:500]
        representatives = RepresentativeProfile.objects.filter(business_status=RepresentativeProfile.BusinessStatus.ACTIVE).select_related("user")
        return Response({
            "customers": [{"id": c.pk, "full_name": c.full_name, "phone": c.phone, "email": c.email} for c in customers],
            "vehicles": [{"reference": v.reference, "name": f"{v.manufacture_year} {v.make} {v.model}", "asking_price_lkr": v.asking_price_lkr} for v in vehicles],
            "representatives": [{"id": p.pk, "reference": p.reference,
                "name": " ".join(part for part in (p.user.first_name, p.user.last_name) if part) or p.user.username} for p in representatives[:250]],
        })


class StaffReservationDetailView(APIView):
    permission_classes = [ReservationAccess]

    def get(self, request, reference):
        reservation = get_object_or_404(Reservation.objects.select_related("customer", "vehicle", "representative__user", "responsible_staff", "released_by"), reference=reference)
        return Response(ReservationSerializer(reservation).data)


class StaffReservationReleaseView(APIView):
    permission_classes = [ReservationAccess]

    def post(self, request, reference):
        serializer = ReservationReleaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                reservation = Reservation.objects.select_for_update().select_related("vehicle").get(reference=reference)
                if reservation.status != Reservation.Status.ACTIVE:
                    return Response({"detail": "Only an active reservation can be released."}, status=status.HTTP_409_CONFLICT)
                vehicle = Vehicle.objects.select_for_update().get(pk=reservation.vehicle_id)
                if vehicle.status != Vehicle.Status.RESERVED:
                    return Response({"detail": "Vehicle status is inconsistent; reservation cannot be released safely."}, status=status.HTTP_409_CONFLICT)
                vehicle.status = Vehicle.Status.AVAILABLE
                vehicle.save(update_fields=["status", "updated_at"])
                reservation.status = Reservation.Status.RELEASED
                reservation.release_reason = serializer.validated_data["release_reason"]
                reservation.released_by = request.user
                reservation.released_at = timezone.now()
                reservation.save(update_fields=["status", "release_reason", "released_by", "released_at", "updated_at"])
                AuditEvent.objects.create(actor=request.user, action="reservation.released", subject=reservation.reference,
                    details={"vehicle_reference": vehicle.reference, "status": reservation.status,
                             "release_reason": reservation.release_reason})
        except Reservation.DoesNotExist:
            return Response({"detail": "Reservation not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ReservationSerializer(reservation).data)


class RepDashboardView(APIView):
    permission_classes = [HasCapability]
    required_capability = "sales.own"

    def get(self, request):
        sales = Sale.objects.filter(representative__user=request.user)
        entries = CommissionLedgerEntry.objects.filter(recipient=request.user)
        pending_total = entries.filter(status__in=["pending", "approved"]).aggregate(total=Sum("commission_amount_lkr"))["total"] or Decimal("0.00")
        paid_total = entries.filter(status="paid").aggregate(total=Sum("payout_amount_lkr"))["total"] or Decimal("0.00")
        return Response({
            "profile_linked": RepresentativeProfile.objects.filter(user=request.user).exists(),
            "draft_sales": sales.filter(status=Sale.Status.DRAFT).count(),
            "confirmed_sales": sales.filter(status=Sale.Status.CONFIRMED).count(),
            "handed_over_sales": sales.filter(handover__status=Handover.Status.FINALIZED).count(),
            "pending_commissions": entries.filter(status__in=["pending", "approved"]).count(),
            "pending_commission_lkr": pending_total,
            "paid_commissions": entries.filter(status="paid").count(),
            "paid_commission_lkr": paid_total,
            "unrated_commissions": entries.filter(status="pending", commission_rate_percent__isnull=True).count(),
        })


class RepSalesView(APIView):
    permission_classes = [HasCapability]
    required_capability = "sales.own"

    def get(self, request, reference=None):
        sales = Sale.objects.filter(representative__user=request.user)
        if reference:
            sale = sales.filter(reference=reference).values(
                "reference", "vehicle__reference", "vehicle__manufacture_year", "vehicle__make", "vehicle__model",
                "customer__full_name", "sale_type", "agreed_price_lkr", "sale_date", "status", "confirmed_at",
                "handover__status", "handover__finalized_at").first()
            if not sale:
                return Response({"detail": "Sale not found."}, status=status.HTTP_404_NOT_FOUND)
            rows = [sale]
        else:
            search = request.query_params.get("search", "").strip()
            state = request.query_params.get("status", "")
            if state in Sale.Status.values:
                sales = sales.filter(status=state)
            if search:
                sales = sales.filter(Q(reference__icontains=search) | Q(vehicle__reference__icontains=search) |
                    Q(vehicle__make__icontains=search) | Q(vehicle__model__icontains=search) |
                    Q(customer__full_name__icontains=search))
            rows = list(sales.order_by("-created_at").values(
                "reference", "vehicle__reference", "vehicle__manufacture_year", "vehicle__make", "vehicle__model",
                "customer__full_name", "sale_type", "agreed_price_lkr", "sale_date", "status", "confirmed_at",
                "handover__status", "handover__finalized_at")[:250])
        return Response([{
            "reference": row["reference"], "vehicle_reference": row["vehicle__reference"],
            "vehicle_name": f"{row['vehicle__manufacture_year']} {row['vehicle__make']} {row['vehicle__model']}",
            "customer_name": row["customer__full_name"], "sale_type": row["sale_type"],
            "agreed_price_lkr": row["agreed_price_lkr"], "sale_date": row["sale_date"],
            "status": row["status"], "confirmed_at": row["confirmed_at"],
            "handover_status": row["handover__status"], "handover_finalized_at": row["handover__finalized_at"],
        } for row in rows]) if not reference else Response({
            "reference": rows[0]["reference"], "vehicle_reference": rows[0]["vehicle__reference"],
            "vehicle_name": f"{rows[0]['vehicle__manufacture_year']} {rows[0]['vehicle__make']} {rows[0]['vehicle__model']}",
            "customer_name": rows[0]["customer__full_name"], "sale_type": rows[0]["sale_type"],
            "agreed_price_lkr": rows[0]["agreed_price_lkr"], "sale_date": rows[0]["sale_date"],
            "status": rows[0]["status"], "confirmed_at": rows[0]["confirmed_at"],
            "handover_status": rows[0]["handover__status"], "handover_finalized_at": rows[0]["handover__finalized_at"],
        })


class RepCommissionLedgerView(APIView):
    permission_classes = [HasCapability]
    required_capability = "commission.own"

    def get(self, request):
        entries = CommissionLedgerEntry.objects.filter(recipient=request.user).select_related("sale__vehicle", "handover")
        if request.query_params.get("view") == "leaderboard":
            return Response(commission_leaderboard(entries.filter(status="paid", recipient__role=User.Role.REP)))
        search = request.query_params.get("search", "").strip()
        if search:
            entries = entries.filter(Q(sale__reference__icontains=search) | Q(handover__reference__icontains=search) |
                Q(sale__vehicle__reference__icontains=search) | Q(sale__vehicle__make__icontains=search) |
                Q(sale__vehicle__model__icontains=search))
        return Response([{
            "sale_reference": entry.sale.reference, "vehicle_reference": entry.sale.vehicle.reference,
            "handover_reference": entry.handover.reference, "finalized_at": entry.handover.finalized_at,
            "sale_price_lkr": entry.sale_price_lkr, "commission_rate_percent": entry.commission_rate_percent,
            "commission_amount_lkr": entry.commission_amount_lkr, "status": entry.status,
            "created_at": entry.created_at, "payout_reference": entry.payout_reference or None,
            "payout_date": entry.payout_date, "payout_amount_lkr": entry.payout_amount_lkr,
        } for entry in entries.order_by("-created_at")[:250]])
