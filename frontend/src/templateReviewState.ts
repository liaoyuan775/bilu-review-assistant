import type { ReviewResult, ReviewTask, RuleStatus } from "./types";
import { isManualDecisionClosed } from "./reviewActionPolicy";


export const actionableStatuses = new Set<RuleStatus>([
  "missing",
  "incomplete",
  "inconsistent",
  "needs_manual_review",
]);

export const summaryStatuses: RuleStatus[] = [
  "missing", "incomplete", "inconsistent", "needs_manual_review", "not_applicable", "covered",
];

const statusPriority: Record<RuleStatus, number> = {
  missing: 0,
  inconsistent: 1,
  incomplete: 2,
  needs_manual_review: 3,
  covered: 4,
  not_applicable: 5,
};

const severityPriority: Record<ReviewResult["severity"], number> = {
  high: 0,
  medium: 1,
  low: 2,
};

export type ReviewResultSectionKey = "open" | "closed" | "not_applicable" | "covered";

export interface ReviewResultSection {
  key: ReviewResultSectionKey;
  groups: ReturnType<typeof groupTemplateResults>;
}

export const groupTemplateResults = (results: ReviewResult[]) => {
  const groups = new Map<string, ReviewResult[]>();
  results.forEach((result) => {
    const items = groups.get(result.group) ?? [];
    items.push(result);
    groups.set(result.group, items);
  });
  return [...groups].map(([name, items]) => ({
    name,
    results: [...items].sort((left, right) => statusPriority[left.status] - statusPriority[right.status]),
  }));
};

const resultSection = (result: ReviewResult): ReviewResultSectionKey => {
  if (result.status === "covered") return "covered";
  if (result.status === "not_applicable") return "not_applicable";
  return isManualDecisionClosed(result) ? "closed" : "open";
};

export const sectionTemplateResults = (results: ReviewResult[]): ReviewResultSection[] => {
  const sectionOrder: ReviewResultSectionKey[] = ["open", "closed", "not_applicable", "covered"];
  return sectionOrder.flatMap((key) => {
    const sorted = results
      .filter((result) => resultSection(result) === key)
      .sort((left, right) =>
        severityPriority[left.severity] - severityPriority[right.severity]
        || statusPriority[left.status] - statusPriority[right.status],
      );
    if (sorted.length === 0) return [];
    return [{ key, groups: groupTemplateResults(sorted) }];
  });
};

export const countTemplateStatuses = (results: ReviewResult[]): Record<RuleStatus, number> => {
  const counts: Record<RuleStatus, number> = {
    covered: 0,
    missing: 0,
    incomplete: 0,
    inconsistent: 0,
    not_applicable: 0,
    needs_manual_review: 0,
  };
  results.forEach((result) => { counts[result.status] += 1; });
  return counts;
};

export const processingLabel = (item: ReviewResult): string | null => {
  if (item.status === "covered") return null;
  if (item.status === "not_applicable") return "自动判定";
  if (isManualDecisionClosed(item)) return "已处理";
  return "待判断";
};

const pending = (result: ReviewResult) =>
  actionableStatuses.has(result.status) && result.manualDecision.status === "pending";

export const nextActionableIssueId = (results: ReviewResult[], currentRuleId: string): string | null => {
  if (results.length === 0) return null;
  const currentIndex = results.findIndex((result) => result.ruleId === currentRuleId);
  for (let offset = 1; offset <= results.length; offset += 1) {
    const candidate = results[(Math.max(currentIndex, 0) + offset) % results.length];
    if (pending(candidate)) return candidate.ruleId;
  }
  return null;
};

export interface ArchiveBlocker {
  code: "failed_domains" | "unresolved_warnings" | "unresolved_issues";
  label: string;
  count: number;
}

export const archiveBlockers = (task: ReviewTask): ArchiveBlocker[] => {
  const blockers: ArchiveBlocker[] = [];
  if (task.failedDomains.length > 0) {
    blockers.push({ code: "failed_domains", label: "抽取失败域", count: task.failedDomains.length });
  }
  const unresolvedWarnings = task.document?.warnings.filter(
    (warning) => !task.acknowledgedWarnings.includes(warning.code),
  ) ?? [];
  if (unresolvedWarnings.length > 0) {
    blockers.push({ code: "unresolved_warnings", label: "未确认解析告警", count: unresolvedWarnings.length });
  }
  const unresolvedIssues = task.results.filter((result) =>
    actionableStatuses.has(result.status) && !isManualDecisionClosed(result),
  );
  if (unresolvedIssues.length > 0) {
    blockers.push({ code: "unresolved_issues", label: "待判断问题", count: unresolvedIssues.length });
  }
  return blockers;
};
