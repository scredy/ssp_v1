from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import AuditEvent, Enquiry
from .customer_email import customer_email_context, send_customer_email


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


def _confirmation_email(enquiry, updated):
    purpose = "showroom appointment" if enquiry.kind == Enquiry.Kind.APPOINTMENT else "test drive"
    prefix = "Updated " if updated else ""
    when = timezone.localtime(enquiry.scheduled_at, SRI_LANKA_TIME).strftime("%A, %d %B %Y at %I:%M %p")
    subject = f"{prefix.title()}{purpose.title()} confirmation ({enquiry.reference})"
    confirmation_line = (
        f"Your {purpose} has been updated."
        if updated else f"Your {purpose} is confirmed."
    )
    rows = [("Confirmed date and time", f"{when} Sri Lanka time (Asia/Colombo)")]
    vehicle = ""
    if enquiry.vehicle:
        vehicle = f"{enquiry.vehicle.manufacture_year} {enquiry.vehicle.make} {enquiry.vehicle.model}".strip()
        if enquiry.vehicle.variant:
            vehicle = f"{vehicle} {enquiry.vehicle.variant}".strip()
    elif enquiry.vehicle_description.strip():
        vehicle = enquiry.vehicle_description.strip()
    if vehicle:
        rows.append(("Vehicle", vehicle))

    location = getattr(settings, "COMPANY_LOCATION", "").strip()
    phone = getattr(settings, "COMPANY_PHONE", "").strip()
    email = getattr(settings, "COMPANY_EMAIL", "").strip()
    if location:
        rows.append(("Showroom", location))
    if phone:
        rows.append(("Phone", phone))
    if email:
        rows.append(("Email", email))
    context = customer_email_context(
        title=f"{prefix}{purpose.title()} Confirmed",
        subtitle="Thank you for arranging your visit with SSP Motor Trading.",
        name=enquiry.customer.full_name,
        message=confirmation_line,
        reference=enquiry.reference,
        info_rows=rows,
        next_title="We look forward to seeing you",
        next_message="Please contact us if you need to change your appointment.",
    )
    return subject, context


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
        subject, context = _confirmation_email(enquiry, updated=enquiry.confirmation_email_is_update)
        accepted = send_customer_email(
            subject=subject,
            context=context,
            recipient=enquiry.confirmation_email_recipient,
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
