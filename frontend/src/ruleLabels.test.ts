import { describe, expect, it } from "vitest";

import {
  displayDomainLabel,
  displayEntityTypeLabel,
  displayFactLabel,
  displayGroupLabel,
  displayReviewReason,
  displayRuleScope,
} from "./ruleLabels";


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

  it("translates repeated entity fields into business-facing Chinese", () => {
    expect(displayFactLabel("cs_002.account")).toBe("第2个后续联系人账号");
    expect(displayFactLabel("transfer_001.transaction_id")).toBe("第1笔转账交易流水号");
    expect(displayFactLabel("transfer_002.transaction_id")).toBe("第2笔转账交易流水号");
    expect(displayFactLabel("transfers.count")).toBe("转账记录数量");
  });

  it("translates machine fields embedded in review reasons", () => {
    expect(displayReviewReason(
      "已询问相关事项，但答案不清或明细不足：cs_002.account、transfer_001.transaction_id、transfer_002.transaction_id。",
    )).toBe(
      "已询问相关事项，但答案不清或明细不足：第2个后续联系人账号、第1笔转账交易流水号、第2笔转账交易流水号。",
    );
  });

  it("translates domain and entity summaries", () => {
    expect(displayDomainLabel("online_money")).toBe("线上资金流");
    expect(displayEntityTypeLabel("contact_switches")).toBe("后续联系人切换");
    expect(displayEntityTypeLabel("transfers")).toBe("转账记录");
  });

  it("translates every conditional fact that can reach review results", () => {
    const paths = [
      "contact.chat_used",
      "contact.phone_used",
      "contact.voice_call",
      "online_money.used",
      "offline.handoff_count",
      "offline.property_source",
      "offline.used",
      "special.ecommerce_logistics_impersonation",
      "special.gambling_related",
    ];
    expect(paths.map(displayFactLabel)).not.toContainEqual(expect.stringMatching(/^[a-z_]+\.[a-z_]+$/));
  });
});
