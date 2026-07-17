import { describe, expect, it } from "vitest";
import { canCompleteReview, nextPendingRuleId, pendingDecisionCount } from "./reviewState";
import type { ManualStatus, ReviewResult, RuleStatus } from "./types";

const result = (status: RuleStatus, manualStatus: ManualStatus): ReviewResult => ({
  ruleId: `${status}-${manualStatus}`,
  ruleName: "测试规则",
  category: "测试",
  group: "三现",
  status,
  missingFacts: [],
  evidence: "",
  evidenceLocation: null,
  reason: "",
  suggestedQuestion: "建议补问",
  advisories: [],
  manualDecision: { status: manualStatus, reason: "" },
  source: "working_rule",
});

describe("review completion", () => {
  it("requires decisions only for missing and incomplete results", () => {
    const results = [
      result("covered", "pending"),
      result("not_applicable", "pending"),
      result("missing", "confirmed"),
      result("incomplete", "supplemented"),
    ];

    expect(pendingDecisionCount(results)).toBe(0);
    expect(canCompleteReview(results)).toBe(true);
  });

  it("accepts ignore without requiring typed text", () => {
    expect(canCompleteReview([result("missing", "ignored")])).toBe(true);
    expect(canCompleteReview([result("missing", "pending")])).toBe(false);
  });

  it("selects the next pending result after a decision", () => {
    const results = [
      result("missing", "confirmed"),
      result("incomplete", "pending"),
      result("missing", "pending"),
    ];

    expect(nextPendingRuleId(results, "missing-confirmed")).toBe("incomplete-pending");
  });

  it("wraps to an earlier pending result and stops when none remain", () => {
    const results = [
      result("missing", "pending"),
      result("covered", "pending"),
      result("incomplete", "ignored"),
    ];

    expect(nextPendingRuleId(results, "incomplete-ignored")).toBe("missing-pending");
    expect(nextPendingRuleId([result("missing", "confirmed")], "missing-confirmed")).toBeNull();
  });
});
