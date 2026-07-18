import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { VictimProfileCard } from "./VictimProfileCard";

describe("victim profile card", () => {
  it("renders the victim information in the review result", () => {
    const html = renderToStaticMarkup(
      <VictimProfileCard
        profile={{
          name: "陈某",
          gender: "女",
          age: 31,
          ethnicity: "汉族",
          idNumber: "430***********1234",
          employer: "某公司",
          address: "长沙市某区",
          contact: "138****0000",
        }}
      />,
    );

    expect(html).toContain("被害人信息");
    expect(html).toContain("陈某");
    expect(html).toContain("身份证号");
    expect(html).toContain("430***********1234");
  });
});
