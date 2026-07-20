import type { ManualStatus, ReviewResult, RuleStatus } from "./types";


export interface ReviewSecondaryAction {
  status: Extract<ManualStatus, "resolved" | "not_applicable" | "ignored">;
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
  { status: "not_applicable", label: "确认不适用" },
  { status: "ignored", label: "不处理并说明" },
];

const policies: Partial<Record<RuleStatus, ReviewActionPolicy>> = {
  missing: {
    recommendation: "原文未找到明确问答，建议补问并记录实际回答。",
    primary: { status: "supplemented", label: "补问并重审" },
    secondary: commonSecondary,
  },
  incomplete: {
    recommendation: "已询问但关键信息不足，建议补齐缺失内容后重审。",
    primary: { status: "supplemented", label: "补问并重审" },
    secondary: [
      { status: "resolved", label: "接受现有回答" },
      ...commonSecondary,
    ],
  },
  inconsistent: {
    recommendation: "现有材料存在冲突，建议核实准确事实后重审。",
    primary: { status: "supplemented", label: "核实并重审" },
    secondary: [
      { status: "resolved", label: "确认以现有材料为准" },
      ...commonSecondary,
    ],
  },
  needs_manual_review: {
    recommendation: "系统无法可靠判断适用性，请先人工确认；适用时补问，不适用时说明依据。",
    primary: { status: "supplemented", label: "确认适用并补问" },
    secondary: commonSecondary,
  },
};


export const reviewActionPolicy = (status: RuleStatus): ReviewActionPolicy | null =>
  policies[status] ?? null;

export const isManualDecisionClosed = (result: ReviewResult): boolean => {
  const decision = result.manualDecision;
  return ["resolved", "not_applicable", "ignored"].includes(decision.status)
    && Boolean(decision.reason.trim());
};

export const manualDecisionLabel = (result: ReviewResult): string => {
  const labels: Record<ManualStatus, string> = {
    pending: "待人工处置",
    confirmed: "旧版：仅确认，仍需闭环",
    supplemented: "已加入补问，等待记录答案",
    ignored: "已说明不处理",
    resolved: "已闭环",
    not_applicable: "人工确认不适用",
  };
  return labels[result.manualDecision.status];
};
