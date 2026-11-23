from decimal import Decimal

from django.db.models import Q, Sum

from .models import Payment


def sale_payment_summary(sale):
    scope = Q(sale=sale)
    if sale.reservation_id:
        scope |= Q(reservation_id=sale.reservation_id)
    if sale.import_order_id:
        scope |= Q(import_order_id=sale.import_order_id)
    totals = Payment.objects.filter(scope).aggregate(
        verified=Sum("amount_lkr", filter=Q(status=Payment.Status.VERIFIED)),
        pending=Sum("amount_lkr", filter=Q(status=Payment.Status.PENDING)),
    )
    verified = totals["verified"] or Decimal("0.00")
    pending = totals["pending"] or Decimal("0.00")
    required_down_payment = sale.reservation.advance_amount_lkr if sale.reservation_id else Decimal("0.00")
    down_payment_remaining = max(Decimal("0.00"), required_down_payment - verified)
    return {
        "sale_price_lkr": sale.agreed_price_lkr,
        "verified_received_lkr": verified,
        "pending_verification_lkr": pending,
        "outstanding_balance_lkr": max(Decimal("0.00"), sale.agreed_price_lkr - verified),
        "required_down_payment_lkr": required_down_payment,
        "down_payment_verified_lkr": min(verified, required_down_payment),
        "down_payment_remaining_lkr": down_payment_remaining,
        "down_payment_satisfied": down_payment_remaining == 0,
    }
