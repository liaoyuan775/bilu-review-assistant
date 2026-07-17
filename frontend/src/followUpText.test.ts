import { describe, expect, it } from "vitest";
import { effectiveFollowUpQuestion, formatFollowUpList } from "./followUpText";
import type { ReviewResult } from "./types";

const result = (ruleId: string, ruleName: string, status: "supplemented" | "confirmed", edited = ""): ReviewResult => ({
  ruleId,
  ruleName,
  category: "测试",
  group: "三现",
  status: "incomplete",
  missingFacts: [],
  evidence: "",
  evidenceLocation: null,
  evidenceAnchorIds: [],
  reason: "",
  suggestedQuestion: `${ruleName}的模型建议问法`,
  advisories: [],
  manualDecision: { status, reason: edited },
  source: "working_rule",
  severity: "high",
});

describe("follow-up text", () => {
  it("uses optional edited text before the model suggestion", () => {
    expect(effectiveFollowUpQuestion(result("A", "案发现场", "supplemented", "  人工调整后的问法  ")))
      .toBe("人工调整后的问法");
    expect(effectiveFollowUpQuestion(result("B", "资金流", "supplemented")))
      .toBe("资金流的模型建议问法");
  });

  it("formats only supplemented items with stable numbering", () => {
    const text = formatFollowUpList([
      result("A", "案发现场", "supplemented"),
      result("B", "资金流", "confirmed"),
      result("C", "行为流", "supplemented", "请核对报警时间。"),
    ]);

    expect(text).toBe(
      "1. 【案发现场】\n案发现场的模型建议问法\n\n" +
      "2. 【行为流】\n请核对报警时间。",
    );
  });
});
