from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import AuditEvent, Enquiry


SRI_LANKA_TIME = ZoneInfo("Asia/Colombo")


def valid_customer_email(value):
    recipient = (value or "").strip()
    if not recipient:
        return ""
    try:
        validate_email(recipient)
    except ValidationError:
        return ""
    return recipient


def queue_confirmation_email(enquiry, actor_id, updated=False):
    recipient = valid_customer_email(enquiry.customer.email)
    enquiry.confirmation_email_schedule = enquiry.scheduled_at
    enquiry.confirmation_email_is_update = updated
    enquiry.confirmation_email_recipient = recipient
    enquiry.confirmation_email_sent_at = None
    enquiry.confirmation_email_error = ""
    enquiry.confirmation_email_status = (
        Enquiry.ConfirmationEmailStatus.QUEUED if recipient
        else Enquiry.ConfirmationEmailStatus.NO_EMAIL
    )
    if not recipient and enquiry.customer.email.strip():
        enquiry.confirmation_email_error = "Customer record has an invalid email address."
    enquiry.save(update_fields=(
        "confirmation_email_schedule", "confirmation_email_recipient",
        "confirmation_email_is_update", "confirmation_email_sent_at", "confirmation_email_error", "confirmation_email_status",
    ))
    if recipient:
        enquiry_id = enquiry.pk
        scheduled_at = enquiry.scheduled_at
        transaction.on_commit(lambda: send_confirmation_email(enquiry_id, scheduled_at, actor_id))


def _confirmation_message(enquiry, updated):
    purpose = "showroom appointment" if enquiry.kind == Enquiry.Kind.APPOINTMENT else "test drive"
    prefix = "Updated " if updated else ""
    when = timezone.localtime(enquiry.scheduled_at, SRI_LANKA_TIME).strftime("%A, %d %B %Y at %I:%M %p")
    subject = f"{prefix.title()}{purpose.title()} confirmation ({enquiry.reference})"
    confirmation_line = (
        f"Your {purpose} has been updated."
        if updated else f"Your {purpose} is confirmed."
    )
    lines = [
        f"Hello {enquiry.customer.full_name},",
        "",
        confirmation_line,
        f"Confirmed date and time: {when} Sri Lanka time (Asia/Colombo).",
    ]
    vehicle = ""
    if enquiry.vehicle:
        vehicle = f"{enquiry.vehicle.manufacture_year} {enquiry.vehicle.make} {enquiry.vehicle.model}".strip()
        if enquiry.vehicle.variant:
            vehicle = f"{vehicle} {enquiry.vehicle.variant}".strip()
    elif enquiry.vehicle_description.strip():
        vehicle = enquiry.vehicle_description.strip()
    if vehicle:
        lines.append(f"Vehicle: {vehicle}")
    lines.extend(("", f"Reference: {enquiry.reference}"))

    location = getattr(settings, "COMPANY_LOCATION", "").strip()
    phone = getattr(settings, "COMPANY_PHONE", "").strip()
    email = getattr(settings, "COMPANY_EMAIL", "").strip()
    contact = []
    if location:
        contact.append(f"Location: {location}")
    if phone:
        contact.append(f"Phone: {phone}")
    if email:
        contact.append(f"Email: {email}")
    if contact:
        lines.extend(("", *contact))
    lines.extend(("", "SSP Motor Trading"))
    return subject, "\n".join(lines)


def send_confirmation_email(enquiry_id, scheduled_at: datetime, actor_id):
    claimed = Enquiry.objects.filter(
        pk=enquiry_id,
        status=Enquiry.Status.SCHEDULED,
        scheduled_at=scheduled_at,
        confirmation_email_schedule=scheduled_at,
        confirmation_email_status=Enquiry.ConfirmationEmailStatus.QUEUED,
    ).update(confirmation_email_status=Enquiry.ConfirmationEmailStatus.SENDING)
    if not claimed:
        return

    enquiry = Enquiry.objects.select_related("customer", "vehicle").get(pk=enquiry_id)
    try:
        subject, message = _confirmation_message(enquiry, updated=enquiry.confirmation_email_is_update)
        accepted = send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [enquiry.confirmation_email_recipient],
            fail_silently=False,
        )
        status_value = (Enquiry.ConfirmationEmailStatus.SENT if accepted
                        else Enquiry.ConfirmationEmailStatus.FAILED)
        error = "" if accepted else "The configured mail service did not accept the message."
    except Exception as exc:
        status_value = Enquiry.ConfirmationEmailStatus.FAILED
        error = f"Mail backend error ({type(exc).__name__}); check the configured email service and server logs."

    with transaction.atomic():
        updated = Enquiry.objects.filter(
            pk=enquiry_id,
            scheduled_at=scheduled_at,
            confirmation_email_schedule=scheduled_at,
            confirmation_email_status=Enquiry.ConfirmationEmailStatus.SENDING,
        ).update(
            confirmation_email_status=status_value,
            confirmation_email_sent_at=timezone.now() if status_value == Enquiry.ConfirmationEmailStatus.SENT else None,
            confirmation_email_error=error,
        )
        if updated:
            AuditEvent.objects.create(
                actor_id=actor_id,
                action="enquiry.confirmation_email",
                subject=enquiry.reference,
                details={"status": status_value, "scheduled_at": scheduled_at.isoformat()},
            )
