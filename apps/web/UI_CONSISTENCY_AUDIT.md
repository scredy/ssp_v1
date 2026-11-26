# SSP UI consistency audit

## Scope inspected before the shared UI pass

The app uses the Next.js App Router under `app/`, with public pages rendered outside the staff layout. `/staff/layout.tsx` wraps operational routes in `StaffShell`; the shell obtains the authenticated user, applies the existing role route guard, and renders role-specific navigation. The Admin dashboard has a legacy local shell that is visually hidden under the shared staff shell. Most operational pages still contain local page headers, forms, tables, detail panels, and feedback states. `BrandLogo` is reused by both public and internal layouts.

## Implemented route inventory

| Area | Routes |
| --- | --- |
| Public website | `/`, `/about`, `/cars`, `/cars/[reference]`, `/finance`, `/contact`, `/book-appointment`, `/request-quote`, `/track` |
| Authentication | `/staff/login`, `/staff/password-reset`, `/staff/accept-invitation`, `/staff/reset-password` |
| Admin | `/staff`, `/staff/accounts`, `/staff/activity` |
| CEO | `/staff`, `/staff/sales`, `/staff/sales-summary`, `/staff/payments`, `/staff/handovers`, `/staff/commission-rules`, `/staff/commissions`, `/staff/quotations`, `/staff/imports`, `/staff/bl-requests`, `/staff/inventory`, `/staff/reservations`, `/staff/reps`, `/staff/enquiries`, `/staff/customers`, `/staff/oversight/managers`, `/staff/notifications` |
| MD / Manager | `/staff`, `/staff/sales`, `/staff/sales-summary`, `/staff/payments`, `/staff/handovers`, `/staff/commission-rules`, `/staff/commissions`, `/staff/quotations`, `/staff/imports`, `/staff/inventory`, `/staff/reservations`, `/staff/reps`, `/staff/enquiries`, `/staff/customers`, `/staff/notifications` |
| Staff | `/staff`, `/staff/inventory`, `/staff/reservations`, `/staff/handovers`, `/staff/imports`, `/staff/payments`, `/staff/quotations`, `/staff/enquiries`, `/staff/customers`, `/staff/sales-summary`, `/staff/notifications` |
| Representative | `/staff`, `/staff/my-sales`, `/staff/my-commissions`, `/staff/notifications` |

The route list describes rendered pages; access remains controlled by the existing role-aware shell and backend permissions.

## Inconsistencies observed

- Internal pages had several independently composed local headers and legacy shell markup, while navigation and session controls already lived in one shared shell.
- Common cards, table headings, controls, borders, status colors, and focus treatments varied between reservations, handovers, sales, imports, quotations, payments, commissions, representatives, audit, and notification pages.
- Responsive behavior was implemented in page-specific groups, so dense tables and forms did not share one consistent overflow and stacking policy.
- The shared header provided a title and role context but no consistent breadcrumb context.
- Public pages already had a separate customer-facing layout and should remain outside the internal shell.

This audit records the existing presentation structure only. It does not change routes, business rules, APIs, roles, or permissions.

## Shared UI consistency checklist

- Reuse the role-aware `StaffShell` and `BrandLogo`; keep public pages outside the staff shell.
- Use the SSP black, racing red, white, light-grey, silver, green, and amber tokens from `globals.css`.
- Keep one clear page title, role and breadcrumb context, a short description, and a visible primary action where the current role is authorized to use one.
- Reuse the existing card, toolbar, table, form, status, feedback, and dialog class patterns before adding page-specific styles.
- Keep tables readable with local horizontal scrolling; do not allow the whole page to scroll sideways.
- Preserve labeled controls, keyboard focus visibility, disabled states, and touch-friendly actions.
- Check layouts at 390 × 844, 768 × 1024, 1366 × 768, and 1920 × 1080.
- Render real API values and existing empty, loading, error, and success states; do not add sample production metrics.
- Preserve role navigation, API permissions, business rules, history, and audit behavior when making visual changes.
