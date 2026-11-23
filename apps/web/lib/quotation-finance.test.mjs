import test from "node:test";
import assert from "node:assert/strict";
import { amountFinanced, isDownPaymentValid, monthlyEstimate } from "./quotation-finance.mjs";

test("down payment is bounded by vehicle price and amount financed uses exact cents", () => {
  assert.equal(isDownPaymentValid("1000000.00", "100000.00"), true);
  assert.equal(isDownPaymentValid("1000000.00", "1000000.01"), false);
  assert.equal(isDownPaymentValid("1000000.00", "-0.01"), false);
  assert.equal(amountFinanced("1000000.00", "100000.00"), "900000.00");
});

test("monthly estimates use each configured per-lakh rate and round half up to cents", () => {
  const financed = amountFinanced("1000000.00", "100000.00");
  assert.deepEqual([
    monthlyEstimate(financed, "3575.84"),
    monthlyEstimate(financed, "2483.00"),
    monthlyEstimate(financed, "2275.00"),
    monthlyEstimate(financed, "1330.00"),
  ], ["32182.56", "22347.00", "20475.00", "11970.00"]);
  assert.equal(monthlyEstimate("10.00", "50.00"), "0.01");
});
