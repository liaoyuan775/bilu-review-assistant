import { describe, expect, it } from "vitest";

import { toggleSelectedRuleId } from "./resultSelection";

describe("toggleSelectedRuleId", () => {
  it("opens a collapsed result", () => {
    expect(toggleSelectedRuleId(null, "PRESENT-001")).toBe("PRESENT-001");
  });

  it("collapses the currently open result", () => {
    expect(toggleSelectedRuleId("PRESENT-001", "PRESENT-001")).toBeNull();
  });

  it("switches directly to another result", () => {
    expect(toggleSelectedRuleId("PRESENT-001", "FLOW-001")).toBe("FLOW-001");
  });
});
