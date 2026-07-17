# 执行流程可读性优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留 React Flow 画布和节点详情的前提下，用醒目的五步主进度带让甲方和民警一眼看出当前执行到哪一步，并让执行流程页面不渲染负面终态或异常出口文案。

**Architecture:** 保留现有 `workflowNodes/workflowEdges` 作为可审计的节点详情数据；新增面向用户的五阶段投影，将“文件校验 + 内容标准化”合并为“材料读取”。`WorkflowView` 同时渲染五阶段进度带和过滤后的主链路画布，失败等内部任务状态只用于决定中性展示，不进入该页面文案。

**Tech Stack:** React 18, TypeScript, `@xyflow/react`, Vitest, CSS。

## Global Constraints

- 保留现有 React Flow 画布、节点点击、拖拽、缩放和右侧节点详情面板。
- 执行流程页只展示 `待处理`、`进行中`、`已完成`、`等待开始`、`等待重新处理` 等中性文案，不渲染异常出口、失败图例或红色失败分支。
- 不改变后端 `TaskStatus`、API 路由、审查结果状态、人工分流和 SQLite 契约。
- 不把流程画布当成后端执行器；阶段映射必须继续以 `ReviewTask.status/reviewStatus` 为输入。
- 不重置用户拖动后的节点位置；状态更新只修改节点数据和连线样式。
- 当前工作区已有大量未提交变更，不回滚、重排或提交无关文件。

---

### Task 1: 定义并测试五阶段用户进度投影

**Files:**
- Modify: `frontend/src/workflowProgress.ts`
- Test: `frontend/src/workflowProgress.test.ts`

**Interfaces:**
- Consumes: `TaskStatus`、`ReviewStatus`。
- Produces: `WorkflowDisplayStage[]` 和 `getWorkflowProgress(taskStatus, reviewStatus)` 的现有节点状态；`WorkflowView` 使用五阶段投影而不是重新解释任务状态。

- [ ] **Step 1: Write the failing tests**

Add tests that define the user-facing contract:

```ts
it("projects processing into five readable stages", () => {
  const progress = getWorkflowProgress("checking", "in_review");

  expect(progress.displayStages.map((stage) => stage.id)).toEqual([
    "material",
    "recognition",
    "rule-review",
    "result-check",
    "manual-review",
  ]);
  expect(progress.currentDisplayStageId).toBe("rule-review");
  expect(progress.displayStages[2].state).toBe("active");
});

it("groups parsing into material reading and keeps manual review active after analysis", () => {
  expect(getWorkflowProgress("parsing", "in_review").currentDisplayStageId).toBe("material");
  expect(getWorkflowProgress("completed", "in_review").currentDisplayStageId).toBe("manual-review");
});

it("marks all five stages complete after archive", () => {
  const progress = getWorkflowProgress("completed", "archived");

  expect(progress.currentDisplayStageId).toBeNull();
  expect(progress.displayStages.every((stage) => stage.state === "completed")).toBe(true);
});

it("keeps an unfinished task neutral without exposing an error state", () => {
  const progress = getWorkflowProgress("failed", "in_review");

  expect(progress.currentDisplayStageId).toBeNull();
  expect(progress.displayStages.every((stage) => stage.state === "pending")).toBe(true);
});
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `npm --prefix frontend run test -- src/workflowProgress.test.ts`

Expected: FAIL because `displayStages`, `currentDisplayStageId`, and the five-stage projection do not exist yet.

- [ ] **Step 3: Implement the minimal projection**

In `frontend/src/workflowProgress.ts`, add:

```ts
export type WorkflowDisplayStageId = "material" | "recognition" | "rule-review" | "result-check" | "manual-review";
export type WorkflowDisplayState = "pending" | "active" | "completed";

export interface WorkflowDisplayStage {
  id: WorkflowDisplayStageId;
  label: string;
  hint: string;
  state: WorkflowDisplayState;
}

const displayStageForTaskStatus: Record<TaskStatus, WorkflowDisplayStageId | null> = {
  idle: null,
  uploading: "material",
  parsing: "material",
  recognizing: "recognition",
  checking: "rule-review",
  validating: "result-check",
  completed: "manual-review",
  failed: null,
};

const displayStageDefinitions: Array<Pick<WorkflowDisplayStage, "id" | "label" | "hint">> = [
  { id: "material", label: "材料读取", hint: "读取并整理笔录内容" },
  { id: "recognition", label: "内容识别", hint: "识别页面和图片文字" },
  { id: "rule-review", label: "规则审查", hint: "依据三现四流规则逐项检查" },
  { id: "result-check", label: "结果核验", hint: "核对规则、证据和原文位置" },
  { id: "manual-review", label: "人工复核", hint: "确认问题并处理补问事项" },
];
```

Build `displayStages` by comparing each definition index with the current display stage index. For `archived`, mark all stages completed and set the current stage to `null`; for `failed`, keep all display stages pending and set the current stage to `null`. Preserve the existing node-level `states` for the canvas and keep the internal `failed` state type because it is part of the current task contract, but do not expose it as a display-stage state.

- [ ] **Step 4: Run focused tests and the existing workflow data tests**

Run: `npm --prefix frontend run test -- src/workflowProgress.test.ts src/workflowData.test.ts`

Expected: all focused tests pass. The existing six-node data contract remains unchanged.

### Task 2: Add the readable progress header while preserving the canvas

**Files:**
- Modify: `frontend/src/WorkflowView.tsx`
- Modify: `frontend/src/workflowProgress.ts`
- Test: `frontend/src/workflowProgress.test.ts`

**Interfaces:**
- Consumes: `WorkflowProgress.displayStages`, `WorkflowProgress.currentDisplayStageId`, `ReviewTask`.
- Produces: a `workflow-progress-strip` with five stable steps and a neutral summary line; existing `WorkflowNode` and detail panel remain available.

- [ ] **Step 1: Write the failing display-contract test**

Extend the progress tests with the stable labels and hints:

```ts
it("keeps customer-facing labels short and action-oriented", () => {
  const labels = getWorkflowProgress("idle", "in_review").displayStages.map((stage) => stage.label);

  expect(labels).toEqual(["材料读取", "内容识别", "规则审查", "结果核验", "人工复核"]);
  expect(getWorkflowProgress("idle", "in_review").displayStages[0].hint).toContain("笔录");
});
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `npm --prefix frontend run test -- src/workflowProgress.test.ts`

Expected: FAIL until the display-stage definitions and hints are implemented.

- [ ] **Step 3: Render the progress strip above the existing workbench**

In `WorkflowView.tsx`:

1. Read `progress.displayStages` and derive `currentDisplayStage`.
2. Render a `workflow-progress-strip` immediately below the heading.
3. Render each stage with its ordinal, label, and state class. Use `CheckCircle2` for completed, `LoaderCircle` with `spin` for active, and `Circle` for pending.
4. Add a summary block with `当前阶段：${currentDisplayStage.label}` and `第 ${activeIndex + 1} / 5 步`; for idle use `等待开始`, for archived use `审查流程已完成`, and for the internal unfinished state use `等待重新处理`.
5. Keep the React Flow canvas and current detail panel unchanged except for the visibility filtering in Task 3.

The component shape should be equivalent to:

```tsx
<div className="workflow-progress-strip" aria-label="审查执行进度">
  {progress.displayStages.map((stage, index) => {
    const StageIcon = stage.state === "completed" ? CheckCircle2 : stage.state === "active" ? LoaderCircle : Circle;
    return (
      <div className={`workflow-progress-step state-${stage.state}`} key={stage.id}>
        <div className="workflow-progress-marker"><StageIcon size={16} className={stage.state === "active" ? "spin" : ""} /></div>
        <div><strong>{String(index + 1).padStart(2, "0")} {stage.label}</strong><small>{stage.hint}</small></div>
      </div>
    );
  })}
</div>
```

- [ ] **Step 4: Run the full frontend test suite and build**

Run: `npm --prefix frontend run test && npm --prefix frontend run build`

Expected: 7 test files and 30+ tests pass, followed by a successful Vite production build.

### Task 3: Hide negative branches from the visual canvas without deleting audit data

**Files:**
- Modify: `frontend/src/WorkflowView.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/workflowData.test.ts` (only if a pure visibility helper is extracted)

**Interfaces:**
- Consumes: existing `workflowNodes`, `workflowEdges`, and node-level runtime states.
- Produces: the same clickable six-node main canvas, with failure/exception branch data retained but not rendered on this page.

- [ ] **Step 1: Add a pure visibility helper if needed and write its failing test**

If keeping filtering inline would duplicate it, add `visibleWorkflowNodes`/`visibleWorkflowEdges` helpers in `WorkflowView.tsx` or a small `workflowDisplay.ts`. The contract is:

```ts
const visibleNodes = workflowNodes.filter((node) => node.id !== "failed");
const visibleEdges = workflowEdges.filter((edge) => edge.data?.kind !== "failure");
```

The existing `workflowData.test.ts` must continue proving that the source data contains the four audit exits; the new UI helper, if extracted, must prove that neither exit is returned for rendering.

- [ ] **Step 2: Run the focused test to verify the visibility contract**

Run: `npm --prefix frontend run test -- src/workflowData.test.ts`

Expected: the source-data tests still pass; if a new helper test exists, it initially fails before the helper is implemented.

- [ ] **Step 3: Filter only the rendered nodes and edges**

Use the filtered arrays in `nodesWithProgress`, `edgesWithProgress`, `resetView`, and the `ReactFlow` props. Do not remove the `failed` source node or failure edges from `workflowData.ts`; they remain available for audit/data tests and future diagnostics. Remove the workflow footer entry that names a failure state. Keep only `执行中`、`已完成`、`待执行` and `当前任务状态`.

For the neutral unfinished task state, do not render the failure node, red edges, alert label, or an error code in `WorkflowView`. Error details remain available in the existing new-review error banner, outside this progress visualization.

- [ ] **Step 4: Add progress-strip and neutral-summary styles**

In `styles.css`, add styles for `.workflow-progress-strip`, `.workflow-progress-step`, `.workflow-progress-marker`, `.workflow-progress-step.state-active`, `.workflow-progress-step.state-completed`, and responsive wrapping. Keep the existing canvas sizing and detail panel styles. The active step must be visually dominant through blue border/background and a moving icon; completed steps use green accents; pending steps use muted gray. Do not introduce red styling in the execution-flow page.

- [ ] **Step 5: Run the full frontend suite and build**

Run: `npm --prefix frontend run test && npm --prefix frontend run build`

Expected: all frontend tests pass and the production build succeeds without TypeScript errors.

### Task 4: Verify the integrated workflow experience

**Files:**
- Modify: none unless verification exposes a regression in the files above.
- Test: existing frontend and backend suites.

**Interfaces:**
- Consumes: the completed progress projection and visual filtering from Tasks 1-3.
- Produces: verified integrated behavior with no backend contract changes.

- [ ] **Step 1: Run repository tests and build**

Run: `npm test`

Expected: frontend tests pass, backend tests pass.

Run: `npm run build`

Expected: TypeScript/Vite build and Python compileall pass.

- [ ] **Step 2: Check the local UI at the existing dev URL**

Open `http://127.0.0.1:5173/` and inspect the execution-flow page with an in-review task and an archived task.

Expected:

- the five-step strip is visible before the canvas;
- only one active step is visually dominant;
- completed steps use checkmarks and pending steps are muted;
- the canvas remains clickable, draggable, and detailed on the right;
- no failure/exception branch or red failure legend is visible;
- completion presents `审查流程已完成` and an obvious route to results.

- [ ] **Step 3: Run final diff checks**

Run: `git diff --check`

Expected: no whitespace errors. Confirm `git status --short` shows only the intended workflow files plus the pre-existing dirty worktree changes.
