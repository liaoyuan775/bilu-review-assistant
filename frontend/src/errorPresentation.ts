const CONNECTION_ERRORS = new Set([
  "model_not_configured",
  "model_unreachable",
  "model_auth_failed",
]);

const PARSING_ERRORS = new Set([
  "empty_document",
  "file_too_large",
  "parse_failed",
  "unsupported_format",
  "unsupported_legacy_word",
]);

const VALIDATION_ERRORS = new Set([
  "invalid_model_response",
  "incomplete_model_results",
  "invalid_model_results",
  "insufficient_evidence",
]);

export const getReviewErrorTitle = (code?: string) => {
  if (code && CONNECTION_ERRORS.has(code)) return "无法开始审查";
  if (code && PARSING_ERRORS.has(code)) return "文件解析失败";
  if (code && VALIDATION_ERRORS.has(code)) return "审查结果校验未通过";
  return "审查未完成";
};
