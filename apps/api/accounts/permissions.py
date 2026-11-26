from rest_framework.permissions import BasePermission


CAPABILITIES = {
    "accounts.manage": {"admin"},
    "activity.view": {"admin"},
    "manager_oversight.view": {"ceo"},
    "commission_rules.view": {"ceo", "manager"},
    "commission_rules.manage": {"ceo"},
    "reps.manage": {"manager"},
    "reps.view": {"manager", "ceo"},
    "reps.self": {"rep"},
    "sales.oversight": {"manager"},
    "inventory.workflows": {"staff"},
    "inventory.review": {"staff", "ceo", "manager"},
    "imports.workflows": {"staff"},
    "reservations.workflows": {"staff"},
    "sales.own": {"rep"},
    "commission.own": {"rep"},
    "enquiries.manage": {"staff", "ceo", "manager"},
    "customers.view": {"staff", "ceo", "manager"},
}


class HasCapability(BasePermission):
    """Views must name a known capability; missing/unknown capabilities deny by default."""

    def has_permission(self, request, view):
        capability = getattr(view, "required_capability", None)
        allowed_roles = CAPABILITIES.get(capability)
        return bool(
            request.user
            and request.user.is_authenticated
            and allowed_roles
            and request.user.role in allowed_roles
        )


class InventoryAccess(BasePermission):
    """Staff manage stock; CEO and MD/Manager can only review it."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return request.user.role in CAPABILITIES["inventory.review"]
        return request.user.role == "staff"


class RepresentativeDirectoryAccess(BasePermission):
    """Manager owns representative changes; CEO can only review profiles."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return request.user.role in CAPABILITIES["reps.view"]
        return request.user.role == "manager"


class ReservationAccess(BasePermission):
    """Staff write reservations; CEO and MD/Manager can review them."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return request.user.role in {"staff", "ceo", "manager"}
        return request.user.role == "staff"


class CustomerAccess(BasePermission):
    """Staff may create customer records; customer reads retain their existing audience."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return request.user.role in CAPABILITIES["customers.view"]
        return request.method == "POST" and request.user.role == "staff"


class SalesAccess(BasePermission):
    """Managers manage sales; CEO reviews them; staff receive summary-only access."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        role = request.user.role
        if getattr(view, "options_only", False):
            return role == "manager"
        if getattr(view, "summary_only", False):
            return role in {"staff", "manager", "ceo"}
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return role in {"manager", "ceo"}
        return role == "manager"


class PaymentAccess(BasePermission):
    """Only CEO and MD/Manager can manage financial transactions."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        role = request.user.role
        action = getattr(view, "payment_action", "")
        if action == "settlement_summary":
            return request.method in {"GET", "HEAD", "OPTIONS"} and role in {"staff", "ceo", "manager"}
        if action == "record":
            return request.method == "POST" and role in {"ceo", "manager"}
        if action == "collection":
            return role in {"ceo", "manager"} and request.method in {"GET", "POST"}
        if action in {"verify", "reject", "reverse"}:
            return request.method == "POST" and role in {"ceo", "manager"}
        return request.method in {"GET", "HEAD", "OPTIONS"} and role in {"ceo", "manager"}


class HandoverAccess(BasePermission):
    """Staff prepare; MD and CEO perform their assigned approval stages; MD finalizes."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        role = request.user.role
        action = getattr(view, "handover_action", "")
        if action == "eligible_sales":
            return request.method in {"GET", "HEAD", "OPTIONS"} and role == "staff"
        if action == "document_receipt":
            if request.method in {"GET", "HEAD", "OPTIONS"}:
                return role in {"staff", "manager", "ceo"}
            return request.method == "POST" and role in {"staff", "manager"}
        if action in {"collection", "detail", "evidence"}:
            if request.method in {"GET", "HEAD", "OPTIONS"}:
                return role in {"staff", "manager", "ceo"}
            if action == "collection":
                return request.method == "POST" and role == "staff"
            if action == "detail":
                return request.method == "PATCH" and role == "staff"
            return False
        if action == "submit":
            return request.method == "POST" and role == "staff"
        if action == "approve_md":
            return request.method == "POST" and role == "manager"
        if action == "approve_ceo":
            return request.method == "POST" and role == "ceo"
        if action == "return":
            return request.method == "POST" and role in {"manager", "ceo"}
        if action == "finalize":
            return request.method == "POST" and role == "manager"
        return False


class QuotationAccess(BasePermission):
    """Staff and MD manage quotations; CEO can read; Admin and Rep are excluded."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        role = request.user.role
        action = getattr(view, "quotation_action", "")
        if action in {"issue", "void"}:
            return request.method in {"POST", "PATCH"} and role in {"staff", "manager"}
        if action == "write" and request.method in {"POST", "PATCH"}:
            return role in {"staff", "manager"}
        if action == "collection":
            return ((request.method == "GET" and role in {"staff", "ceo", "manager"}) or
                    (request.method == "POST" and role in {"staff", "manager"}))
        return request.method in {"GET", "HEAD", "OPTIONS"} and role in {"staff", "ceo", "manager"}


class ImportAccess(BasePermission):
    """Staff manage imports; CEO and MD/Manager receive read-only progress access."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(view, "bl_decision", False):
            return request.method == "POST" and request.user.role == "ceo"
        if getattr(view, "bl_collection", False):
            if request.method in {"GET", "HEAD", "OPTIONS"}:
                return request.user.role in {"staff", "ceo", "manager"}
            return request.method == "POST" and request.user.role == "staff"
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return request.user.role in {"staff", "ceo", "manager"}
        return request.user.role == "staff" and request.method in {"POST", "PATCH"}


class CommissionLedgerAccess(BasePermission):
    """Only CEO and MD/Manager can review and record commission payout states."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated or request.user.role not in {"ceo", "manager"}:
            return False
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return True
        return request.method == "POST" and bool(getattr(view, "allow_payout_transition", False))
