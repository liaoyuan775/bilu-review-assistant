import { describe, expect, it } from "vitest";

import { isEvidencePage, isEvidenceParagraph } from "./evidenceSelection";

const locations = [
  { page: 1, paragraph: 2 },
  { page: 1, paragraph: 4 },
  { page: 3, paragraph: 1 },
];

describe("evidence selection", () => {
  it("marks every page containing selected evidence", () => {
    expect(isEvidencePage(locations, 1)).toBe(true);
    expect(isEvidencePage(locations, 2)).toBe(false);
    expect(isEvidencePage(locations, 3)).toBe(true);
  });

  it("marks only referenced paragraphs", () => {
    expect(isEvidenceParagraph(locations, 1, 2)).toBe(true);
    expect(isEvidenceParagraph(locations, 1, 3)).toBe(false);
    expect(isEvidenceParagraph(locations, 3, 1)).toBe(true);
  });
});
