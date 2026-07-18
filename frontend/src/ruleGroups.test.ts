import { describe, expect, it } from "vitest";

import { groupRules } from "./ruleGroups";

describe("groupRules", () => {
  it("keeps three-present and four-flow rules in separate ordered groups", () => {
    const groups = groupRules([
      { id: "FLOW-001", group: "四流" },
      { id: "PRESENT-002", group: "三现" },
      { id: "PRESENT-001", group: "三现" },
    ]);

    expect(groups.map((group) => group.name)).toEqual(["三现", "四流"]);
    expect(groups[0].rules.map((rule) => rule.id)).toEqual(["PRESENT-001", "PRESENT-002"]);
    expect(groups[1].rules.map((rule) => rule.id)).toEqual(["FLOW-001"]);
  });
});
