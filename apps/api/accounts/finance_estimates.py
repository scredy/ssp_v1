from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings

from .models import Quotation

ONE_LAKH_LKR = Decimal("100000.00")
MONTHLY_QUANTUM = Decimal("0.01")


def finance_options():
    rates = settings.FINANCE_ESTIMATE_PER_100K
    return [
        {"id": term, "label": label, "rate_per_100k_lkr": str(rates[term].quantize(MONTHLY_QUANTUM)), "unit_amount_lkr": str(ONE_LAKH_LKR)}
        for term, label in Quotation.FinanceTerm.choices
    ]


def calculate_finance_estimate(term, vehicle_price_lkr, down_payment_lkr):
    rate = settings.FINANCE_ESTIMATE_PER_100K[term]
    financed = vehicle_price_lkr - down_payment_lkr
    monthly = (financed / ONE_LAKH_LKR * rate).quantize(MONTHLY_QUANTUM, rounding=ROUND_HALF_UP)
    label = dict(Quotation.FinanceTerm.choices)[term]
    return {
        "term": term,
        "term_label": label,
        "down_payment_lkr": str(down_payment_lkr),
        "financed_amount_lkr": str(financed),
        "rate_per_100k_lkr": str(rate.quantize(MONTHLY_QUANTUM)),
        "unit_amount_lkr": str(ONE_LAKH_LKR),
        "monthly_estimate_lkr": str(monthly),
    }
