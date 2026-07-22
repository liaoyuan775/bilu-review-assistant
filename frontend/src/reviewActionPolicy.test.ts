import { describe, expect, it } from "vitest";

import {
  isManualDecisionClosed,
  manualDecisionLabel,
  reviewActionPolicy,
} from "./reviewActionPolicy";
import type { ManualStatus, ReviewResult, RuleStatus } from "./types";


const result = (
  status: RuleStatus,
  manualStatus: ManualStatus,
  reason = "",
): ReviewResult => ({
  ruleId: "RULE-001",
  ruleName: "测试规则",
  category: "CASE",
  group: "CASE",
  status,
  missingFacts: [],
  evidence: "",
  evidenceLocation: null,
  evidenceLocations: [],
  evidenceAnchorIds: [],
  reason: "",
  suggestedQuestion: "请补充说明。",
  advisories: [],
  manualDecision: { status: manualStatus, reason },
  source: "内部模板",
  severity: "medium",
});


describe("review action policy", () => {
  it.each([
    ["missing", "加入补问清单", ["resolved", "ignored"]],
    ["incomplete", "加入补问清单", ["resolved", "ignored"]],
    ["inconsistent", "加入补问清单", ["resolved", "ignored"]],
    ["needs_manual_review", "加入补问清单", ["resolved", "ignored"]],
  ] as const)("provides status-specific actions for %s", (status, primaryLabel, secondaryStatuses) => {
    const policy = reviewActionPolicy(status);

    expect(policy?.primary.label).toBe(primaryLabel);
    expect(policy?.secondary.map((action) => action.status)).toEqual(secondaryStatuses);
  });

  it("does not offer manual actions for covered or automatically inapplicable results", () => {
    expect(reviewActionPolicy("covered")).toBeNull();
    expect(reviewActionPolicy("not_applicable")).toBeNull();
  });

  it("uses plain-language labels for secondary review decisions", () => {
    expect(reviewActionPolicy("incomplete")?.secondary[0].label).toBe("当前回答足够");
    expect(reviewActionPolicy("missing")?.secondary[1].label).toBe("忽略此提示");
  });

  it.each([
    ["pending", "", false],
    ["confirmed", "", false],
    ["supplemented", "", true],
    ["resolved", "", true],
    ["ignored", "", true],
  ] as const)("evaluates %s closure consistently", (manualStatus, reason, closed) => {
    expect(isManualDecisionClosed(result("incomplete", manualStatus, reason))).toBe(closed);
  });

  it("marks historical confirmation as unfinished", () => {
    expect(manualDecisionLabel(result("missing", "confirmed"))).toBe("旧版：仅确认，仍需闭环");
  });
});
