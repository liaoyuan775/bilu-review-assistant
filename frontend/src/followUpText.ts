/**
 * 补问文本工具 — 获取有效补问内容和格式化补问清单。
 *
 * 有效补问的优先级：
 * 1. 人工编辑的补问内容（manualDecision.reason）
 * 2. 模型建议的补问内容（suggestedQuestion）
 */
import type { ReviewResult } from "./types";

/** 获取规则的有效补问内容（人工编辑优先，模型建议兜底）。 */
export const effectiveFollowUpQuestion = (result: ReviewResult) =>
  result.manualDecision.reason.trim() || result.suggestedQuestion.trim();

/**
 * 将补问清单格式化为纯文本。
 *
 * 只包含 manualDecision.status === "supplemented" 的规则项。
 * 格式："1. 【规则名】\n补问内容\n\n2. 【规则名】\n补问内容"
 */
export const formatFollowUpList = (results: ReviewResult[]) =>
  results
    .filter((result) => result.manualDecision.status === "supplemented")
    .map((result, index) => `${index + 1}. 【${result.ruleName}】\n${effectiveFollowUpQuestion(result)}`)
    .join("\n\n");
