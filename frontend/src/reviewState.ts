/**
 * 审查状态辅助函数 — 用于 UI 判断待处置项、可归档性以及下一个待处理规则。
 *
 * 核心业务规则：
 * - 只有 status 为 "missing" 或 "incomplete" 的规则需要人工分流。
 * - 当全部待处置项完成后（pendingCount === 0），才允许归档。
 * - nextPendingRuleId 实现了"从当前规则往下找"的循环遍历逻辑。
 */

import type { ReviewResult } from "./types";

/** 判断某条规则是否需要人工分流。 */
const needsDecision = (result: ReviewResult) => result.status === "missing" || result.status === "incomplete";

/** 统计待处置的规则数量（missing/incomplete 且 manual 为 pending）。 */
export const pendingDecisionCount = (results: ReviewResult[]) =>
  results.filter((result) => needsDecision(result) && result.manualDecision.status === "pending").length;

/** 判断是否可完成复核（有结果且无待处置项）。 */
export const canCompleteReview = (results: ReviewResult[]) =>
  results.length > 0 && pendingDecisionCount(results) === 0;

/**
 * 获取当前规则之后的下一个待处置规则 ID。
 *
 * 从 currentRuleId 的下一条开始查找，找到规则列表尾部时回到头部继续查找。
 * 这样设计是为了在 UI 中提供"跳转到下一待处置项"的自然交互。
 *
 * @returns 下一个待处置规则的 ruleId，如果没有则返回 null。
 */
export const nextPendingRuleId = (results: ReviewResult[], currentRuleId: string): string | null => {
  const currentIndex = results.findIndex((result) => result.ruleId === currentRuleId);
  const orderedResults = currentIndex < 0
    ? results
    : [...results.slice(currentIndex + 1), ...results.slice(0, currentIndex + 1)];
  return orderedResults.find((result) => needsDecision(result) && result.manualDecision.status === "pending")?.ruleId ?? null;
};
