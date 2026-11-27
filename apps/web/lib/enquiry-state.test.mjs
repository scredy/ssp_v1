import test from "node:test";
import assert from "node:assert/strict";
import { syncSavedEnquiry, supportsScheduling, enquiryStatuses } from "./enquiry-state.mjs";

test("a confirmed enquiry save synchronizes selected detail, list row, notes, and time from API response", () => {
  const original = { id: 4, status: "new", internal_notes: "Draft", scheduled_at: null };
  const saved = { ...original, status: "scheduled", internal_notes: "Called and confirmed.", scheduled_at: "2027-02-10T06:30:00Z" };
  const result = syncSavedEnquiry([original, { id: 5, status: "new", internal_notes: "", scheduled_at: null }], saved);

  assert.deepEqual(result.selected, saved);
  assert.deepEqual(result.items[0], saved);
  assert.equal(result.items[1].id, 5);
  assert.equal(result.note, saved.internal_notes);
  assert.equal(result.scheduledAt, saved.scheduled_at);
});

test("only appointments and test drives support scheduling", () => {
  for (const kind of ["general", "quote"]) {
    assert.equal(supportsScheduling(kind), false);
    assert.equal(enquiryStatuses(kind).includes("scheduled"), false);
    assert.equal(enquiryStatuses(kind).includes("contacted"), true);
  }

  for (const kind of ["appointment", "test_drive"]) {
    assert.equal(supportsScheduling(kind), true);
    assert.equal(enquiryStatuses(kind).includes("scheduled"), true);
  }
});
