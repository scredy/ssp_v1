export function staffRouteRedirect(pathname, role, routeRoles) {
  if (!role || ["/staff", "/staff/login", "/staff/password-reset", "/staff/accept-invitation", "/staff/reset-password"].includes(pathname)) return null;
  const required = routeRoles.find(([route]) => pathname === route || pathname.startsWith(`${route}/`));
  return !required || !required[1].includes(role) ? "/staff" : null;
}
