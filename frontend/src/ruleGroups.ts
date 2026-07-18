/**
 * 规则分组工具 — 按服务端提供的模板业务组动态分组。
 */
export interface GroupableRule {
  id: string;
  group: string;
}

/**
 * @returns 包含 name 和 rules 的分组数组；旧分组保持既有顺序，模板组保持服务端顺序。
 */
export const groupRules = <T extends GroupableRule>(rules: T[]) => {
  const names = [...new Set(rules.map((rule) => rule.group))];
  names.sort((left, right) => {
    const legacy = ["三现", "四流"];
    const leftIndex = legacy.indexOf(left);
    const rightIndex = legacy.indexOf(right);
    if (leftIndex >= 0 || rightIndex >= 0) return (leftIndex < 0 ? 99 : leftIndex) - (rightIndex < 0 ? 99 : rightIndex);
    return 0;
  });
  return names.map((name) => ({
    name,
    rules: rules.filter((rule) => rule.group === name).sort((left, right) => left.id.localeCompare(right.id)),
  }));
};
