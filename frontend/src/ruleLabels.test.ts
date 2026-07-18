import { describe, expect, it } from "vitest";

import { displayFactLabel, displayGroupLabel, displayRuleScope } from "./ruleLabels";


describe("rule display labels", () => {
  it("translates template groups without changing their machine keys", () => {
    expect(displayGroupLabel("META")).toBe("笔录与人员信息");
    expect(displayGroupLabel("OFFLINE")).toBe("线下交付");
  });

  it("translates rule scopes", () => {
    expect(displayRuleScope("conditional")).toBe("条件规则");
    expect(displayRuleScope("repeated")).toBe("逐项核对");
  });

  it("translates known fact paths and preserves unknown paths", () => {
    expect(displayFactLabel("record.started_at")).toBe("询问开始时间");
    expect(displayFactLabel("future.new_field")).toBe("future.new_field");
  });
});
