import { describe, expect, it } from "vitest";

import { formatModelReviewDuration } from "./reviewTiming";

describe("formatModelReviewDuration", () => {
  it("omits timing text for historical tasks without timings", () => {
    expect(formatModelReviewDuration(undefined)).toBe("");
  });

  it("formats recorded model review milliseconds", () => {
    expect(formatModelReviewDuration({ modelReviewMs: 2840 })).toBe("模型审查 2.84 秒");
  });
});
