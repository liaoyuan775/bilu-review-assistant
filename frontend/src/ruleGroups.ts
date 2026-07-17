/**
 * 规则分组工具 — 按"三现"和"四流"将规则分为两组。
 *
 * 这是前后端约定的固定分组方式，与后端 rules.json 中的 group 字段对应。
 * 分组后用于 UI 中按组展示结果。
 */
export interface GroupableRule {
  id: string;
  group: "三现" | "四流";
}

/**
 * 将规则列表按"三现"、"四流"分组并组内按 ID 排序。
 *
 * @returns 包含 name 和 rules 的分组数组，顺序固定：三现在前，四流在后。
 */
export const groupRules = <T extends GroupableRule>(rules: T[]) => (["三现", "四流"] as const)
  .map((name) => ({
    name,
    rules: rules.filter((rule) => rule.group === name).sort((left, right) => left.id.localeCompare(right.id)),
  }));
