# SSP Motor Trading V1 — UI/UX references by page

**59 individually extracted reference images** from **9 original design boards**. The images are exact crops of the approved user-provided boards; they are **visual references**, not finished app screens.

**How to use:** Extract this ZIP into `C:/Users/ndsel/Documents/ssp_v1/docs/designs/` so the `screens/`, `original_boards/` and `SCREEN_INDEX.csv` files are available to Codex.

**Important:** The sample names, amounts, dates, commission rates, roles shown in headers and contact details in the board images are illustrative and must not be hardcoded. Use the actual application role and verified business rules. The uploaded official SSP logo takes precedence over any conceptual logos in the boards.

**Important RBAC rules:** Backend `manager` represents MD; Admin is for account controls; Staff manages inventory/reservations; MD manages sales/reps; CEO reviews and controls shared commission policy; Rep sees only authorized own data. No employee/per-sale commission override; eligibility starts after finalized handover.

## Design reference index

| Board | Section | Specific screen | Extracted UI file | Application route |
|---|---:|---|---|---|
| 01 — Public Website | 1 | Home | `screens/board_01_public-website/01_home.png` | / |
| 01 — Public Website | 2 | Vehicles Catalogue | `screens/board_01_public-website/02_vehicles-catalogue.png` | /cars |
| 01 — Public Website | 3 | Vehicle Detail | `screens/board_01_public-website/03_vehicle-detail.png` | /cars/[reference] |
| 01 — Public Website | 4 | Finance Calculator | `screens/board_01_public-website/04_finance-calculator.png` | /finance |
| 01 — Public Website | 5 | Book Appointment | `screens/board_01_public-website/05_book-appointment.png` | Not confirmed / future screen |
| 01 — Public Website | 6 | Track Vehicle | `screens/board_01_public-website/06_track-vehicle.png` | Not confirmed / future screen |
| 01 — Public Website | 7 | About SSP | `screens/board_01_public-website/07_about-ssp.png` | /about |
| 01 — Public Website | 8 | Request Quote | `screens/board_01_public-website/08_request-quote.png` | Not confirmed / future screen |
| 02 — Admin Workspace | 1 | Admin Dashboard | `screens/board_02_admin-workspace/01_admin-dashboard.png` | /staff (Admin role) |
| 02 — Admin Workspace | 2 | Users Directory | `screens/board_02_admin-workspace/02_users-directory.png` | /staff/accounts |
| 02 — Admin Workspace | 3 | Create User | `screens/board_02_admin-workspace/03_create-user.png` | Not confirmed / future screen |
| 02 — Admin Workspace | 4 | User Profile Edit | `screens/board_02_admin-workspace/04_user-profile-edit.png` | Not confirmed / future screen |
| 02 — Admin Workspace | 5 | Recent Account Activity | `screens/board_02_admin-workspace/05_recent-account-activity.png` | /staff/activity |
| 02 — Admin Workspace | 6 | Audit History | `screens/board_02_admin-workspace/06_audit-history.png` | Not confirmed / future screen |
| 03 — Staff Inventory and Reservations | 1 | Staff Dashboard | `screens/board_03_staff-inventory-and-reservations/01_staff-dashboard.png` | /staff (Staff role) |
| 03 — Staff Inventory and Reservations | 2 | Vehicle Inventory | `screens/board_03_staff-inventory-and-reservations/02_vehicle-inventory.png` | /staff/inventory |
| 03 — Staff Inventory and Reservations | 3 | Add Vehicle | `screens/board_03_staff-inventory-and-reservations/03_add-vehicle.png` | Not confirmed / future screen |
| 03 — Staff Inventory and Reservations | 4 | Edit Vehicle Photos Publication | `screens/board_03_staff-inventory-and-reservations/04_edit-vehicle-photos-publication.png` | /staff/inventory |
| 03 — Staff Inventory and Reservations | 5 | Vehicle Internal Detail | `screens/board_03_staff-inventory-and-reservations/05_vehicle-internal-detail.png` | /staff/inventory |
| 03 — Staff Inventory and Reservations | 6 | Reservations | `screens/board_03_staff-inventory-and-reservations/06_reservations.png` | /staff/reservations |
| 04 — Shared Access Mobile and System States | 1 | Staff Sign In | `screens/board_04_shared-access-mobile-and-system-states/01_staff-sign-in.png` | /staff/login |
| 04 — Shared Access Mobile and System States | 2 | Set Password Invitation | `screens/board_04_shared-access-mobile-and-system-states/02_set-password-invitation.png` | Not confirmed / future screen |
| 04 — Shared Access Mobile and System States | 3 | Forgot Reset Password | `screens/board_04_shared-access-mobile-and-system-states/03_forgot-reset-password.png` | Not confirmed / future screen |
| 04 — Shared Access Mobile and System States | 4 | Profile And Security | `screens/board_04_shared-access-mobile-and-system-states/04_profile-and-security.png` | Not confirmed / future screen |
| 04 — Shared Access Mobile and System States | 5 | Notification Inbox | `screens/board_04_shared-access-mobile-and-system-states/05_notification-inbox.png` | Not confirmed / future screen |
| 04 — Shared Access Mobile and System States | 6 | Access Denied And Not Found | `screens/board_04_shared-access-mobile-and-system-states/06_access-denied-and-not-found.png` | Not confirmed / future screen |
| 04 — Shared Access Mobile and System States | 7 | Mobile Staff Inventory And Edit | `screens/board_04_shared-access-mobile-and-system-states/07_mobile-staff-inventory-and-edit.png` | /staff/inventory (mobile) |
| 04 — Shared Access Mobile and System States | 8 | Mobile Rep Catalogue Tracking | `screens/board_04_shared-access-mobile-and-system-states/08_mobile-rep-catalogue-tracking.png` | Not confirmed / future screen |
| 04 — Shared Access Mobile and System States | Shared | Common UI States | `screens/board_04_shared-access-mobile-and-system-states/09_common-ui-states.png` | Shared pattern / not a separate page |
| 05 — Staff Imports Quotations Enquiries | 1 | Import Tracking Directory | `screens/board_05_staff-imports-quotations-enquiries/01_import-tracking-directory.png` | Not confirmed / future screen |
| 05 — Staff Imports Quotations Enquiries | 2 | Create Import | `screens/board_05_staff-imports-quotations-enquiries/02_create-import.png` | Not confirmed / future screen |
| 05 — Staff Imports Quotations Enquiries | 3 | Import Detail Timeline | `screens/board_05_staff-imports-quotations-enquiries/03_import-detail-timeline.png` | Not confirmed / future screen |
| 05 — Staff Imports Quotations Enquiries | 4 | Quotations List | `screens/board_05_staff-imports-quotations-enquiries/04_quotations-list.png` | Not confirmed / future screen |
| 05 — Staff Imports Quotations Enquiries | 5 | Create Quotation | `screens/board_05_staff-imports-quotations-enquiries/05_create-quotation.png` | Not confirmed / future screen |
| 05 — Staff Imports Quotations Enquiries | 6 | Appointments And Quote Requests Inbox | `screens/board_05_staff-imports-quotations-enquiries/06_appointments-and-quote-requests-inbox.png` | /staff/enquiries |
| 06 — MD Sales and Payments | 1 | MD Dashboard | `screens/board_06_md-sales-and-payments/01_md-dashboard.png` | /staff (MD role) |
| 06 — MD Sales and Payments | 2 | Sales Directory | `screens/board_06_md-sales-and-payments/02_sales-directory.png` | /staff/sales |
| 06 — MD Sales and Payments | 3 | New Sale | `screens/board_06_md-sales-and-payments/03_new-sale.png` | /staff/sales |
| 06 — MD Sales and Payments | 4 | Sale Detail | `screens/board_06_md-sales-and-payments/04_sale-detail.png` | /staff/sales |
| 06 — MD Sales and Payments | 5 | Payments Directory | `screens/board_06_md-sales-and-payments/05_payments-directory.png` | Not confirmed / future screen |
| 06 — MD Sales and Payments | 6 | Record Payment | `screens/board_06_md-sales-and-payments/06_record-payment.png` | Not confirmed / future screen |
| 07 — Representative Portal | 1 | Representative Dashboard | `screens/board_07_representative-portal/01_representative-dashboard.png` | /staff (Rep role) |
| 07 — Representative Portal | 2 | My Sales Directory | `screens/board_07_representative-portal/02_my-sales-directory.png` | Not confirmed / future screen |
| 07 — Representative Portal | 3 | My Sale Detail | `screens/board_07_representative-portal/03_my-sale-detail.png` | Not confirmed / future screen |
| 07 — Representative Portal | 4 | My Commissions Ledger | `screens/board_07_representative-portal/04_my-commissions-ledger.png` | Not confirmed / future screen |
| 07 — Representative Portal | 5 | Representative Leaderboard | `screens/board_07_representative-portal/05_representative-leaderboard.png` | Not confirmed / future screen |
| 08 — MD Representatives and Commission Rules | 1 | Representatives Directory | `screens/board_08_md-representatives-and-commission-rules/01_representatives-directory.png` | /staff/reps |
| 08 — MD Representatives and Commission Rules | 2 | Add Representative | `screens/board_08_md-representatives-and-commission-rules/02_add-representative.png` | /staff/reps |
| 08 — MD Representatives and Commission Rules | 3 | Representative Detail | `screens/board_08_md-representatives-and-commission-rules/03_representative-detail.png` | /staff/reps |
| 08 — MD Representatives and Commission Rules | 4 | Commission Brackets Settings | `screens/board_08_md-representatives-and-commission-rules/04_commission-brackets-settings.png` | Not confirmed / future screen |
| 08 — MD Representatives and Commission Rules | 5 | Commission Ledger | `screens/board_08_md-representatives-and-commission-rules/05_commission-ledger.png` | Not confirmed / future screen |
| 08 — MD Representatives and Commission Rules | 6 | MD Leaderboard | `screens/board_08_md-representatives-and-commission-rules/06_md-leaderboard.png` | Not confirmed / future screen |
| 09 — CEO Executive Workspace | 1 | CEO Overview | `screens/board_09_ceo-executive-workspace/01_ceo-overview.png` | /staff (CEO role) |
| 09 — CEO Executive Workspace | 2 | Sales Executive Overview | `screens/board_09_ceo-executive-workspace/02_sales-executive-overview.png` | Not confirmed / future screen |
| 09 — CEO Executive Workspace | 3 | Sale Detail Readonly | `screens/board_09_ceo-executive-workspace/03_sale-detail-readonly.png` | /staff/sales (CEO read-only) |
| 09 — CEO Executive Workspace | 4 | Commission Overview | `screens/board_09_ceo-executive-workspace/04_commission-overview.png` | Not confirmed / future screen |
| 09 — CEO Executive Workspace | 5 | CEO Leaderboard | `screens/board_09_ceo-executive-workspace/05_ceo-leaderboard.png` | Not confirmed / future screen |
| 09 — CEO Executive Workspace | 6 | BL Requests | `screens/board_09_ceo-executive-workspace/06_bl-requests.png` | Not confirmed / future screen |
| 09 — CEO Executive Workspace | Shared | Commission Business Rules Notes | `screens/board_09_ceo-executive-workspace/07_commission-business-rules-notes.png` | Shared pattern / not a separate page |

## How Codex should apply these references

1. Match **each existing page or subview** to its specific image above; do not use one generic page pattern for everything.
2. The internal portal must use one persistent, role-aware sidebar and header across internal routes, with stable active menu items.
3. Preserve real APIs, existing forms and security. Do not replace functional components with static mockups or fake records.
4. On existing pages with no exact design reference (for example, a dedicated Customers directory), adapt the nearest approved directory style while keeping the shared shell. Clearly identify these as adaptations.
5. On unimplemented future pages, treat designs as a reference only. Do not make nonfunctional controls look active.
6. Verify page transitions and route-level/backend RBAC, including keyboard and mobile navigation. Backend permissions are the authority.
7. Do not embed the reference images into the live website; they are implementation guidance only.

## Existing-page-to-design pointers

| Existing page | Specific visual reference |
|---|---|
| Staff dashboard `/staff` | Board 03 / Section 01 |
| Staff inventory `/staff/inventory` | Board 03 / Sections 02–05; Board 04 / Section 07 for mobile |
| Reservations `/staff/reservations` | Board 03 / Section 06 |
| Enquiries `/staff/enquiries` | Board 05 / Section 06 |
| Customers `/staff/customers` | No dedicated customer-directory board; adapt Board 02 / Section 02 directory structure + Board 05 / Section 06 detail panel |
| Sales `/staff/sales` | Board 06 / Sections 02–04 |
| CEO overview | Board 09 / Section 01 |
| MD overview | Board 06 / Section 01 |
| MD representative management `/staff/reps` | Board 08 / Sections 01–03 |
| Rep home `/staff` (rep) | Board 07 / Section 01 |
| Admin `/staff` (admin) | Board 02 / Section 01 |
| Accounts `/staff/accounts` | Board 02 / Sections 02–04 |
| Activity `/staff/activity` | Board 02 / Section 05 |
| Staff login `/staff/login` | Board 04 / Section 01 |
| Public home `/` | Board 01 / Section 01 |
| Catalogue `/cars` | Board 01 / Section 02 |
| Car detail `/cars/[reference]` | Board 01 / Section 03 |
| Finance `/finance` | Board 01 / Section 04 |
| About `/about` | Board 01 / Section 07 |

## Separate design-only screens

Import tracking, quotations, payments, handovers, commission ledger, leaderboard, notification inbox, invitation/recovery, shipment tracking and BL requests are presented in the supplied boards but should not be marked functional until their modules are implemented and tested.
