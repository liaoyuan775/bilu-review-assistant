import { describe, expect, it } from "vitest";
import { NEW_REVIEW_DESCRIPTION } from "./App";
import apiSource from "./api.ts?raw";
import appSource from "./App.tsx?raw";
import reviewActionSource from "./reviewActionPolicy.ts?raw";
import templateReviewSource from "./TemplateReviewView.tsx?raw";
import templateReviewStateSource from "./templateReviewState.ts?raw";

describe("police-facing product copy", () => {
  it("describes the internal inquiry template as the review authority", () => {
    expect(NEW_REVIEW_DESCRIPTION).toContain("依据内部询问笔录模板检查提问遗漏与回答不完整事项");
    expect(NEW_REVIEW_DESCRIPTION).not.toContain("依据演示规则");
  });

  it("uses outcome-oriented actions in the template review page", () => {
    expect(templateReviewSource).toContain("推荐处理");
    expect(templateReviewSource).toContain("reviewActionPolicy");
    expect(templateReviewSource).toContain("manualDecisionLabel");
    expect(templateReviewSource).not.toContain(">确认问题</button>");
  });

  it("names only the automatic status as rule not applicable", () => {
    expect(templateReviewSource).toContain('not_applicable: { label: "规则不适用"');
    expect(appSource).toContain('not_applicable: { label: "规则不适用"');
    expect(appSource).toContain("<span>规则不适用 <strong>{counts.not_applicable}</strong></span>");
    expect(reviewActionSource).toContain('label: "确认不适用"');
    expect(reviewActionSource).toContain('not_applicable: "人工确认不适用"');
  });

  it("labels review sections, risk levels, and processing state explicitly", () => {
    for (const label of ["待处理问题", "已闭环问题", "高风险", "中风险", "低风险"]) {
      expect(templateReviewSource).toContain(label);
    }
    expect(templateReviewStateSource).toContain("补问中");
  });

  it("exposes guarded demo-only pass actions", () => {
    expect(templateReviewSource).toContain("测试通过");
    expect(templateReviewSource).toContain("一键测试通过");
    expect(templateReviewSource).toContain("task.demoId");
    expect(templateReviewSource).toContain("onDemoPassAll");
    expect(appSource).toContain("passDemoReview");
    expect(apiSource).toContain("/demo-pass");
  });
});
