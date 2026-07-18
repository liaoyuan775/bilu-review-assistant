import { describe, expect, it } from "vitest";

import { getWorkflowProgress } from "./workflowProgress";

describe("workflow progress", () => {
  it("marks the current processing stage and every previous stage", () => {
    expect(getWorkflowProgress("checking", "in_review")).toEqual({
      currentStageId: "template-review",
      states: {
        validate: "completed",
        normalize: "completed",
        recognize: "completed",
        "template-review": "active",
        "evidence-validation": "pending",
        "manual-action": "pending",
        failed: "pending",
      },
    });
  });

  it("moves completed automatic reviews into manual review", () => {
    expect(getWorkflowProgress("completed", "in_review").currentStageId).toBe("manual-action");
    expect(getWorkflowProgress("completed", "in_review").states["manual-action"]).toBe("active");
  });

  it("marks the whole main path complete after archiving", () => {
    const progress = getWorkflowProgress("completed", "archived");

    expect(progress.currentStageId).toBeNull();
    expect(Object.entries(progress.states).filter(([id]) => id !== "failed").every(([, state]) => state === "completed")).toBe(true);
  });

  it("activates the failure exit when processing fails", () => {
    const progress = getWorkflowProgress("failed", "in_review");

    expect(progress.currentStageId).toBe("failed");
    expect(progress.states.failed).toBe("failed");
  });
});
