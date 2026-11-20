from rest_framework.permissions import BasePermission


CAPABILITIES = {
    "accounts.manage": {"admin"},
    "activity.view": {"admin"},
    "manager_oversight.view": {"ceo"},
    "commission_rules.manage": {"ceo", "manager"},
    "reps.manage": {"manager"},
    "sales.oversight": {"manager"},
    "inventory.workflows": {"staff"},
    "inventory.review": {"staff", "ceo", "manager"},
    "imports.workflows": {"staff"},
    "reservations.workflows": {"staff"},
    "sales.own": {"rep"},
    "commission.own": {"rep"},
    # Handover work is intentionally future scope and always stays with leadership.
    "handovers.route": {"ceo", "manager"},
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
