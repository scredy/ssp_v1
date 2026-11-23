import assert from "node:assert/strict";
import test from "node:test";
import { commissionActions, paidLeaderboardRows } from "./commission-ui.mjs";

test("management controls match the payout state machine and hide actions from Reps", () => {
  assert.deepEqual(commissionActions("manager", "pending"), ["approved", "reversed"]);
  assert.deepEqual(commissionActions("ceo", "approved"), ["paid", "reversed"]);
  assert.deepEqual(commissionActions("manager", "paid"), ["reversed"]);
  assert.deepEqual(commissionActions("ceo", "reversed"), []);
  assert.deepEqual(commissionActions("rep", "pending"), []);
});

test("leaderboard presentation excludes pending, approved, and reversed amounts", () => {
  const records = ["pending", "approved", "paid", "reversed"].map((status) => ({ status }));
  assert.deepEqual(paidLeaderboardRows(records), [{ status: "paid" }]);
});
