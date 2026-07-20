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
          birthDate: "1993年2月1日",
          ethnicity: "汉族",
          idNumber: "430***********1234",
          occupation: "软件工程师",
          education: "本科",
          employer: "某公司",
          address: "长沙市某区",
          registeredAddress: "长沙市测试县",
          contact: "138****0000",
          isNpcRepresentative: false,
        }}
      />,
    );

    expect(html).toContain("被害人信息");
    expect(html).toContain("陈某");
    expect(html).toContain("身份证号");
    expect(html).toContain("430***********1234");
    expect(html).toContain("出生日期");
    expect(html).toContain("1993年2月1日");
    expect(html).toContain("职业");
    expect(html).toContain("软件工程师");
    expect(html).toContain("文化程度");
    expect(html).toContain("户籍所在地");
    expect(html).toContain("是否人大代表");
    expect(html).toContain(">否<");
  });
});
