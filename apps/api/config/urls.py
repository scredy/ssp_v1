from django.urls import path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.views import (
    AccountDetailView, AccountListCreateView, CommissionRulesView, CsrfView, CurrentUserView,
    HandoverBoundaryView, LoginView, LogoutView, ManagerOversightView,
    ManagerRepsView, ManagerSalesView, RecentActivityView, RepDashboardView,
    PublicVehicleDetailView, PublicVehicleListView, StaffImportsView, StaffInventoryDetailView,
    StaffInventoryView, StaffReservationsView, StaffVehiclePhotoDetailView, StaffVehiclePhotosView,
    VehiclePhotoView,
)


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response({"status": "ok"})


urlpatterns = [
    path("api/health/", health, name="health"),
    path("api/auth/csrf/", CsrfView.as_view(), name="csrf"),
    path("api/auth/login/", LoginView.as_view(), name="login"),
    path("api/auth/logout/", LogoutView.as_view(), name="logout"),
    path("api/auth/me/", CurrentUserView.as_view(), name="current-user"),
    path("api/accounts/", AccountListCreateView.as_view(), name="accounts"),
    path("api/accounts/<int:account_id>/", AccountDetailView.as_view(), name="account-detail"),
    path("api/activity/recent/", RecentActivityView.as_view(), name="recent-activity"),
    path("api/oversight/managers/", ManagerOversightView.as_view(), name="manager-oversight"),
    path("api/commission-rules/", CommissionRulesView.as_view(), name="commission-rules"),
    path("api/commission-rules/<slug:key>/", CommissionRulesView.as_view(), name="commission-rule"),
    path("api/manager/reps/", ManagerRepsView.as_view(), name="manager-reps"),
    path("api/manager/sales/", ManagerSalesView.as_view(), name="manager-sales"),
    path("api/staff/inventory/", StaffInventoryView.as_view(), name="staff-inventory"),
    path("api/staff/inventory/<str:reference>/", StaffInventoryDetailView.as_view(), name="staff-inventory-detail"),
    path("api/staff/inventory/<str:reference>/photos/", StaffVehiclePhotosView.as_view(), name="staff-inventory-photos"),
    path("api/staff/inventory/<str:reference>/photos/<int:photo_id>/", StaffVehiclePhotoDetailView.as_view(), name="staff-inventory-photo-detail"),
    path("api/cars/", PublicVehicleListView.as_view(), name="public-cars"),
    path("api/cars/<str:reference>/", PublicVehicleDetailView.as_view(), name="public-car-detail"),
    path("api/vehicle-photos/<int:photo_id>/", VehiclePhotoView.as_view(), name="vehicle-photo"),
    path("api/staff/imports/", StaffImportsView.as_view(), name="staff-imports"),
    path("api/staff/reservations/", StaffReservationsView.as_view(), name="staff-reservations"),
    path("api/rep/dashboard/", RepDashboardView.as_view(), name="rep-dashboard"),
    path("api/handovers/", HandoverBoundaryView.as_view(), name="handover-boundary"),
]
