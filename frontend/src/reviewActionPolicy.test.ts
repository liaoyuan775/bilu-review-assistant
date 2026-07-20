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
    ["missing", "补问并重审", ["not_applicable", "ignored"]],
    ["incomplete", "补问并重审", ["resolved", "not_applicable", "ignored"]],
    ["inconsistent", "核实并重审", ["resolved", "not_applicable", "ignored"]],
    ["needs_manual_review", "确认适用并补问", ["not_applicable", "ignored"]],
  ] as const)("provides status-specific actions for %s", (status, primaryLabel, secondaryStatuses) => {
    const policy = reviewActionPolicy(status);

    expect(policy?.primary.label).toBe(primaryLabel);
    expect(policy?.secondary.map((action) => action.status)).toEqual(secondaryStatuses);
  });

  it("does not offer manual actions for covered or automatically inapplicable results", () => {
    expect(reviewActionPolicy("covered")).toBeNull();
    expect(reviewActionPolicy("not_applicable")).toBeNull();
  });

  it("uses precise resolution labels for incomplete and inconsistent results", () => {
    expect(reviewActionPolicy("incomplete")?.secondary[0].label).toBe("接受现有回答");
    expect(reviewActionPolicy("inconsistent")?.secondary[0].label).toBe("确认以现有材料为准");
    expect(reviewActionPolicy("missing")?.secondary[1].label).toBe("不处理并说明");
  });

  it.each([
    ["pending", "", false],
    ["confirmed", "", false],
    ["supplemented", "请补充说明。", false],
    ["resolved", "人工核对后现有回答足够。", true],
    ["not_applicable", "本案未发生该场景。", true],
    ["ignored", "经负责人确认不再处理。", true],
    ["ignored", "", false],
  ] as const)("evaluates %s closure consistently", (manualStatus, reason, closed) => {
    expect(isManualDecisionClosed(result("incomplete", manualStatus, reason))).toBe(closed);
  });

  it("marks historical confirmation as unfinished", () => {
    expect(manualDecisionLabel(result("missing", "confirmed"))).toBe("旧版：仅确认，仍需闭环");
  });
});
