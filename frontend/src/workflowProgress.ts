/**
 * 工作流进度状态机 — 将后端 TaskStatus + ReviewStatus 映射为前端工作流渲染状态。
 *
 * 映射规则：
 * - 每个阶段有四种运行时状态：pending → active → completed | failed。
 * - 当前活跃阶段由 stageForTaskStatus 映射表确定。
 * - 归档（archived）时，所有阶段标记为 completed。
 * - 失败时仅 failed 节点标记为 failed。
 */

import type { ReviewStatus, TaskStatus } from "./types";

/** 工作流节点的运行时状态。 */
export type WorkflowRuntimeState = "pending" | "active" | "completed" | "failed";

/** 工作流阶段 ID 联合类型。 */
export type WorkflowStageId =
  | "validate"
  | "normalize"
  | "recognize"
  | "template-review"
  | "evidence-validation"
  | "manual-action"
  | "failed";

/** 工作流进度 — 当前阶段与各阶段状态。 */
export interface WorkflowProgress {
  currentStageId: WorkflowStageId | null;
  states: Record<WorkflowStageId, WorkflowRuntimeState>;
}

/** 主流程阶段（不含 failed 节点）。 */
const mainStageIds: Exclude<WorkflowStageId, "failed">[] = [
  "validate",
  "normalize",
  "recognize",
  "template-review",
  "evidence-validation",
  "manual-action",
];

/** TaskStatus → WorkflowStageId 映射。 */
const stageForTaskStatus: Record<TaskStatus, WorkflowStageId | null> = {
  idle: null,
  uploading: "validate",
  parsing: "normalize",
  recognizing: "recognize",
  checking: "template-review",
  validating: "evidence-validation",
  completed: "manual-action",
  failed: "failed",
};

/** 各阶段初始状态（全部为 pending）。 */
const initialStates = (): WorkflowProgress["states"] => ({
  validate: "pending",
  normalize: "pending",
  recognize: "pending",
  "template-review": "pending",
  "evidence-validation": "pending",
  "manual-action": "pending",
  failed: "pending",
});

/**
 * 根据后端任务状态计算工作流进度。
 *
 * @param taskStatus   - 后端任务状态。
 * @param reviewStatus - 复核状态（用于判断是否归档）。
 * @returns 包含当前阶段 ID 和各阶段运行时状态的对象。
 */
export const getWorkflowProgress = (taskStatus: TaskStatus, reviewStatus: ReviewStatus): WorkflowProgress => {
  const states = initialStates();

  // 已归档：所有阶段标记为已完成
  if (reviewStatus === "archived") {
    mainStageIds.forEach((stageId) => { states[stageId] = "completed"; });
    return { currentStageId: null, states };
  }

  const currentStageId = stageForTaskStatus[taskStatus];
  // 失败：仅 failed 节点标记为 failed
  if (currentStageId === "failed") {
    states.failed = "failed";
    return { currentStageId, states };
  }
  if (currentStageId === null) return { currentStageId, states };

  // 正常流转：当前阶段之前 → completed，当前阶段 → active，之后 → pending
  const currentIndex = mainStageIds.indexOf(currentStageId);
  mainStageIds.forEach((stageId, index) => {
    states[stageId] = index < currentIndex ? "completed" : index === currentIndex ? "active" : "pending";
  });
  return { currentStageId, states };
};
