/**
 * 规则选择切换 — 点击相同规则时取消选中，点击不同规则时切换选中。
 *
 * 实现简单的 toggle 逻辑，供 UI 中展开/收起规则详情使用。
 */

/**
 * 切换规则选中状态。
 *
 * @param currentRuleId  当前选中的规则 ID（可能为 null）。
 * @param clickedRuleId  用户点击的规则 ID。
 * @returns 如果点击的是当前已选中的规则，返回 null（取消选中）；
 *          否则返回 clickedRuleId（切换选中）。
 */
export const toggleSelectedRuleId = (currentRuleId: string | null, clickedRuleId: string) =>
  currentRuleId === clickedRuleId ? null : clickedRuleId;
