from django.db import transaction
from django.utils import timezone

from .models import AuditEvent, Handover, HandoverCompletionEmail
from .appointment_email import SRI_LANKA_TIME, valid_customer_email
from .customer_email import customer_email_context, send_customer_email


def queue_handover_email(handover, actor_id):
    if handover.status != Handover.Status.FINALIZED:
        return

    recipient = valid_customer_email(handover.customer.email)

    record, created = HandoverCompletionEmail.objects.get_or_create(
        handover=handover,
        defaults={
            "recipient": recipient,
            "status": (
                HandoverCompletionEmail.Status.QUEUED
                if recipient
                else HandoverCompletionEmail.Status.NO_EMAIL
            ),
        },
    )

    if created and recipient:
        record_id = record.pk
        transaction.on_commit(
            lambda: send_handover_email(record_id, actor_id),
            robust=True,
        )


def send_handover_email(record_id, actor_id):
    claimed = HandoverCompletionEmail.objects.filter(
        pk=record_id,
        status=HandoverCompletionEmail.Status.QUEUED,
        handover__status=Handover.Status.FINALIZED,
    ).update(
        status=HandoverCompletionEmail.Status.SENDING,
        updated_at=timezone.now(),
    )

    if not claimed:
        return

    record = HandoverCompletionEmail.objects.select_related(
        "handover__customer",
        "handover__vehicle",
    ).get(pk=record_id)

    handover = record.handover
    vehicle = handover.vehicle

    try:
        vehicle_name = " ".join(filter(None, [
            str(vehicle.manufacture_year),
            vehicle.make,
            vehicle.model,
            vehicle.variant,
        ]))

        context = customer_email_context(
            title="Vehicle Handover Completed",
            subtitle="Congratulations on your vehicle!",
            name=handover.customer.full_name,
            message=(
                "We are pleased to confirm that your vehicle "
                "handover has been successfully completed. "
                "Thank you for choosing SSP Motor Trading."
            ),
            reference=handover.reference,
            info_rows=[
                ("Vehicle", vehicle_name),
                ("Vehicle reference", vehicle.reference),
                ("Sale reference", handover.sale.reference),
                (
                    "Handover completed on",
                    timezone.localtime(
                        handover.finalized_at, SRI_LANKA_TIME
                    ).strftime("%d %B %Y")
                    if handover.finalized_at else "",
                ),
            ],
            next_title="We're here for you",
            next_message=(
                "If you need any assistance with your vehicle, "
                "please contact our team. We wish you many "
                "safe and happy journeys ahead."
            ),
            notice="This email confirms vehicle delivery only. It is not a payment receipt.",
        )

        accepted = send_customer_email(
            subject=f"Vehicle Handover Completed ({handover.reference})",
            recipient=record.recipient,
            context=context,
            fail_silently=False,
        )

        status_value = (
            HandoverCompletionEmail.Status.SENT
            if accepted
            else HandoverCompletionEmail.Status.FAILED
        )

        error = (
            "" if accepted
            else "The configured mail service did not accept the message."
        )

    except Exception as exc:
        status_value = HandoverCompletionEmail.Status.FAILED
        error = f"Mail backend error ({type(exc).__name__})."

    with transaction.atomic():
        updated = HandoverCompletionEmail.objects.filter(
            pk=record_id,
            status=HandoverCompletionEmail.Status.SENDING,
        ).update(
            status=status_value,
            sent_at=(
                timezone.now()
                if status_value == HandoverCompletionEmail.Status.SENT
                else None
            ),
            error=error,
            updated_at=timezone.now(),
        )

        if updated:
            AuditEvent.objects.create(
                actor_id=actor_id,
                action="handover.completion_email",
                subject=handover.reference,
                details={"status": status_value},
            )
