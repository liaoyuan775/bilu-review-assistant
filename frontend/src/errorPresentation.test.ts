import { describe, expect, it } from "vitest";

import { getReviewErrorTitle } from "./errorPresentation";

describe("getReviewErrorTitle", () => {
  it.each(["model_not_configured", "model_unreachable", "model_auth_failed"])(
    "labels %s as unable to start",
    (code) => expect(getReviewErrorTitle(code)).toBe("无法开始审查"),
  );

  it.each(["empty_document", "parse_failed", "unsupported_format", "unsupported_legacy_word"])(
    "labels %s as a parsing failure",
    (code) => expect(getReviewErrorTitle(code)).toBe("文件解析失败"),
  );

  it.each(["invalid_model_response", "incomplete_model_results", "invalid_model_results", "insufficient_evidence"])(
    "labels %s as a result validation failure",
    (code) => expect(getReviewErrorTitle(code)).toBe("审查结果校验未通过"),
  );

  it("uses a neutral title for an unknown processing failure", () => {
    expect(getReviewErrorTitle("review_service_failed")).toBe("审查未完成");
  });
});
