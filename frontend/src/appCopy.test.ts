import { describe, expect, it } from "vitest";
import { NEW_REVIEW_DESCRIPTION } from "./App";

describe("police-facing product copy", () => {
  it("describes the internal inquiry template as the review authority", () => {
    expect(NEW_REVIEW_DESCRIPTION).toContain("依据内部询问笔录模板检查提问遗漏与回答不完整事项");
    expect(NEW_REVIEW_DESCRIPTION).not.toContain("依据演示规则");
  });
});
