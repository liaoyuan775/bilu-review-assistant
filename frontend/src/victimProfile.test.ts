import { describe, expect, it } from "vitest";

import { getVictimAvatarVariant, getVictimInitial } from "./victimProfile";

describe("victim profile avatar", () => {
  it("uses the first non-space character in the victim name", () => {
    expect(getVictimInitial(" 陈某 ")).toBe("陈");
  });

  it("uses a question mark when no name was extracted", () => {
    expect(getVictimInitial("  ")).toBe("?");
  });

  it("keeps the visual variant stable for the same name", () => {
    expect(getVictimAvatarVariant("陈某")).toBe(getVictimAvatarVariant("陈某"));
    expect(getVictimAvatarVariant("陈某")).toMatch(/^variant-[1-6]$/);
  });
});
