/**
 * 错误展示工具 — 按错误码分类，返回面向用户的错误标题。
 *
 * 错误分类：
 * - CONNECTION_ERRORS: Qwen 模型连接相关（不可达、鉴权、未配置）。
 * - PARSING_ERRORS: 文档解析相关（格式不支持、文件过大、解析失败）。
 * - VALIDATION_ERRORS: 模型结果校验相关（格式无效、结果不完整、证据不足）。
 * - 其他: 兜底为"审查未完成"。
 */

/** Qwen 模型连接错误码集合。 */
const CONNECTION_ERRORS = new Set([
  "model_not_configured",
  "model_unreachable",
  "model_auth_failed",
]);

/** 文档解析错误码集合。 */
const PARSING_ERRORS = new Set([
  "empty_document",
  "file_too_large",
  "parse_failed",
  "unsupported_format",
  "unsupported_legacy_word",
]);

/** 模型结果校验错误码集合。 */
const VALIDATION_ERRORS = new Set([
  "invalid_model_response",
  "incomplete_model_results",
  "invalid_model_results",
  "insufficient_evidence",
]);

/**
 * 根据错误码返回面向用户的错误标题。
 *
 * @param code 后端返回的 errorCode。
 * @returns 如 "无法开始审查"、"文件解析失败"、"审查结果校验未通过" 等。
 */
export const getReviewErrorTitle = (code?: string) => {
  if (code && CONNECTION_ERRORS.has(code)) return "无法开始审查";
  if (code && PARSING_ERRORS.has(code)) return "文件解析失败";
  if (code && VALIDATION_ERRORS.has(code)) return "审查结果校验未通过";
  return "审查未完成";
};
