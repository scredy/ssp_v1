"""Shared branded rendering for customer transactional email."""
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def customer_email_context(*, title, subtitle, name, message, reference="", info_rows=None,
                           next_title="What happens next?", next_message="Our team will be in touch soon.",
                           notice=""):
    """Build the presentation data used by HTML and plain-text variants."""
    portal_url = getattr(settings, "ACCOUNT_PORTAL_URL", "").rstrip("/")
    return {
        "title": title,
        "subtitle": subtitle,
        "customer_name": name or "there",
        "message": message,
        "reference": reference,
        "info_rows": [(label, value) for label, value in (info_rows or []) if value],
        "next_title": next_title,
        "next_message": next_message,
        "notice": notice,
        "logo_url": f"{portal_url}/branding/ssp-logo-display.png" if portal_url else "",
        "company_location": getattr(settings, "COMPANY_LOCATION", "").strip(),
        "company_phone": getattr(settings, "COMPANY_PHONE", "").strip(),
        "company_email": getattr(settings, "COMPANY_EMAIL", "").strip(),
    }


def customer_email_text(context):
    """Return a readable text fallback using only displayed, approved details."""
    lines = [context["title"], context["subtitle"], "", f"Hello {context['customer_name']},", "", context["message"]]
    if context["reference"]:
        lines.extend(("", "Reference Number:", context["reference"]))
    if context["info_rows"]:
        lines.append("")
        lines.extend(f"{label}: {value}" for label, value in context["info_rows"])
    if context["notice"]:
        lines.extend(("", context["notice"]))
    if context["next_message"]:
        lines.extend(("", context["next_title"], context["next_message"]))
    contact = [value for value in (
        context["company_location"], context["company_phone"], context["company_email"]
    ) if value]
    lines.extend(("", "Best regards,", "SSP Motor Trading Team"))
    if contact:
        lines.extend(("", *contact))
    lines.extend(("", "SSP Motor Trading (Pvt) Ltd."))
    return "\n".join(lines)


def send_customer_email(*, subject, recipient, context, fail_silently=False):
    """Send a customer email with shared branded HTML and a text alternative."""
    text = customer_email_text(context)
    html = render_to_string("accounts/emails/customer.html", context)
    email = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
    )
    email.attach_alternative(html, "text/html")
    return email.send(fail_silently=fail_silently)


def enquiry_received_email(enquiry, recipient):
    """Send the acknowledgement created by a successful public enquiry."""
    is_appointment = enquiry.kind in (enquiry.Kind.APPOINTMENT, enquiry.Kind.TEST_DRIVE)
    if is_appointment:
        title = "Appointment Request Received" if enquiry.kind == enquiry.Kind.APPOINTMENT else "Test Drive Request Received"
        purpose = "showroom appointment" if enquiry.kind == enquiry.Kind.APPOINTMENT else "test drive"
        message = f"We have received your {purpose} request. It is not confirmed yet; our team will contact you to confirm availability."
        subtitle = "Thank you for arranging a visit with SSP Motor Trading."
        next_message = "Our team will review your preferred time and contact you to confirm the booking."
        notice = "This request is not a confirmed booking."
    elif enquiry.kind == enquiry.Kind.QUOTE:
        title, subtitle = "Quotation Request Received", "Thank you for your interest in SSP Motor Trading."
        message = "We have received your quotation request. Our team will review the details and contact you to assist further."
        next_message = "Our team will review your request and get back to you soon."
        notice = ""
    else:
        title, subtitle = "Enquiry Received", "Thank you for getting in touch with SSP Motor Trading."
        message = "We have successfully received your enquiry. Our team will contact you to assist you further."
        next_message = "Our team will review your enquiry and get back to you soon."
        notice = ""
    rows = []
    vehicle = ""
    if enquiry.vehicle_id:
        vehicle = " ".join(filter(None, [str(enquiry.vehicle.manufacture_year), enquiry.vehicle.make,
                                         enquiry.vehicle.model, enquiry.vehicle.variant]))
    elif enquiry.vehicle_description.strip():
        vehicle = enquiry.vehicle_description.strip()
    if vehicle:
        rows.append(("Vehicle", vehicle))
    if is_appointment and enquiry.requested_at:
        from django.utils import timezone
        from zoneinfo import ZoneInfo
        requested = timezone.localtime(enquiry.requested_at, ZoneInfo("Asia/Colombo"))
        rows.append(("Preferred time", requested.strftime("%A, %d %B %Y at %I:%M %p")))
    context = customer_email_context(
        title=title, subtitle=subtitle, name=enquiry.customer.full_name, message=message,
        reference=enquiry.reference, info_rows=rows, next_message=next_message, notice=notice,
    )
    subject = f"{title} ({enquiry.reference})"
    return send_customer_email(subject=subject, recipient=recipient, context=context, fail_silently=True)
