import assert from "node:assert/strict";
import test from "node:test";
import { staffRouteRedirect } from "./staff-route-guard.mjs";

const routeRoles = [["/staff/accounts", ["admin"]], ["/staff/sales", ["manager", "ceo"]]];

test("a stale authenticated user stays on the staff login route", () => {
  assert.equal(staffRouteRedirect("/staff/login", "manager", routeRoles), null);
});

test("a signed-out user is left for the authentication guard on the dashboard", () => {
  assert.equal(staffRouteRedirect("/staff", undefined, routeRoles), null);
});

test("role restrictions still return unauthorized staff routes to the dashboard", () => {
  assert.equal(staffRouteRedirect("/staff/accounts", "staff", routeRoles), "/staff");
  assert.equal(staffRouteRedirect("/staff/sales", "manager", routeRoles), null);
});
