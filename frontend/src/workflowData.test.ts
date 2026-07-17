import { describe, expect, it } from "vitest";

import { displayWorkflowEdges, displayWorkflowNodes, workflowEdges, workflowNodes, workflowStages } from "./workflowData";

describe("workflow data", () => {
  it("defines the complete ordered review pipeline", () => {
    expect(workflowStages).toEqual([
      "validate",
      "normalize",
      "recognize",
      "three-four-review",
      "evidence-validation",
      "manual-action",
    ]);

    const mainEdges = workflowEdges.filter((edge) => edge.data?.kind === "main");
    expect(mainEdges.map((edge) => `${edge.source}->${edge.target}`)).toEqual([
      "validate->normalize",
      "normalize->recognize",
      "recognize->three-four-review",
      "three-four-review->evidence-validation",
      "evidence-validation->manual-action",
    ]);
  });

  it("defines auditable details and failure exits", () => {
    expect(workflowNodes.filter((node) => workflowStages.includes(node.id))).toHaveLength(6);
    expect(workflowEdges.filter((edge) => edge.data?.kind === "failure")).toHaveLength(4);

    expect(workflowNodes.find((node) => node.id === "recognize")?.data.process).toContain("多模态");
    expect(workflowNodes.find((node) => node.id === "three-four-review")?.data.title).toContain("三现四流");
    expect(workflowNodes.find((node) => node.id === "evidence-validation")?.data.process).toContain("补充关注");

    for (const node of workflowNodes) {
      expect(node.data.title).toBeTruthy();
      expect(node.data.summary).toBeTruthy();
      expect(node.data.input).toBeTruthy();
      expect(node.data.process).toBeTruthy();
      expect(node.data.output).toBeTruthy();
      expect(node.data.exception).toBeTruthy();
    }
  });

  it("renders one numbered main path without diagnostic exits", () => {
    expect(displayWorkflowNodes.map((node) => node.id)).toEqual(workflowStages);
    expect(displayWorkflowEdges.map((edge) => `${edge.source}->${edge.target}`)).toEqual([
      "validate->normalize",
      "normalize->recognize",
      "recognize->three-four-review",
      "three-four-review->evidence-validation",
      "evidence-validation->manual-action",
    ]);
    expect(displayWorkflowEdges.every((edge) => edge.data?.kind === "main")).toBe(true);
  });
});
