import type { ReviewResult, ReviewTask, RuleStatus } from "./types";


export const actionableStatuses = new Set<RuleStatus>([
  "missing",
  "incomplete",
  "inconsistent",
  "needs_manual_review",
]);

const statusPriority: Record<RuleStatus, number> = {
  missing: 0,
  inconsistent: 1,
  incomplete: 2,
  needs_manual_review: 3,
  covered: 4,
  not_applicable: 5,
};

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
  code: "failed_domains" | "unresolved_warnings" | "missing_artifacts" | "pending_high_risk";
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
  const availableArtifacts = new Set(task.artifacts.map((artifact) => artifact.type));
  const missingArtifacts = task.requiredArtifacts.filter((type) => !availableArtifacts.has(type));
  if (missingArtifacts.length > 0) {
    blockers.push({ code: "missing_artifacts", label: "待生成归档产物", count: missingArtifacts.length });
  }
  const pendingHighRisk = task.results.filter((result) =>
    result.severity === "high"
    && actionableStatuses.has(result.status)
    && !["resolved", "not_applicable"].includes(result.manualDecision.status)
    && !(result.manualDecision.status === "ignored" && Boolean(result.manualDecision.reason.trim())),
  );
  if (pendingHighRisk.length > 0) {
    blockers.push({ code: "pending_high_risk", label: "未闭环高风险问题", count: pendingHighRisk.length });
  }
  return blockers;
};

