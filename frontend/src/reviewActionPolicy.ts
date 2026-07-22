import type { ManualStatus, ReviewResult, RuleStatus } from "./types";


export interface ReviewSecondaryAction {
  status: Extract<ManualStatus, "resolved" | "ignored">;
  label: string;
}

export interface ReviewActionPolicy {
  recommendation: string;
  primary: {
    status: "supplemented";
    label: string;
  };
  secondary: ReviewSecondaryAction[];
}


const commonSecondary: ReviewSecondaryAction[] = [
  { status: "resolved", label: "当前回答足够" },
  { status: "ignored", label: "忽略此提示" },
];

const policies: Partial<Record<RuleStatus, ReviewActionPolicy>> = {
  missing: {
    recommendation: "原文未找到明确问答，建议加入线下补问清单。",
    primary: { status: "supplemented", label: "加入补问清单" },
    secondary: commonSecondary,
  },
  incomplete: {
    recommendation: "已询问但关键信息不足，建议加入线下补问清单。",
    primary: { status: "supplemented", label: "加入补问清单" },
    secondary: commonSecondary,
  },
  inconsistent: {
    recommendation: "现有材料存在冲突，建议加入线下补问清单。",
    primary: { status: "supplemented", label: "加入补问清单" },
    secondary: commonSecondary,
  },
  needs_manual_review: {
    recommendation: "系统无法可靠判断适用性，请人工判断是否需要加入补问清单。",
    primary: { status: "supplemented", label: "加入补问清单" },
    secondary: commonSecondary,
  },
};


export const reviewActionPolicy = (status: RuleStatus): ReviewActionPolicy | null =>
  policies[status] ?? null;

export const isManualDecisionClosed = (result: ReviewResult): boolean => {
  const decision = result.manualDecision;
  return ["supplemented", "resolved", "ignored"].includes(decision.status);
};

export const manualDecisionLabel = (result: ReviewResult): string => {
  const labels: Record<ManualStatus, string> = {
    pending: "待人工处置",
    confirmed: "旧版：仅确认，仍需闭环",
    supplemented: "已加入补问清单",
    ignored: "已忽略此提示",
    resolved: "当前回答足够",
    not_applicable: "人工确认不适用",
  };
  return labels[result.manualDecision.status];
};
