import { describe, expect, it } from "vitest";

import { evidenceAnchorRangesFor, isEvidencePage, isEvidenceParagraph } from "./evidenceSelection";
import type { ParsedDocument, ReviewResult } from "./types";

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

  it("maps stable anchor IDs to exact character ranges and PDF coordinates", () => {
    const document = {
      id: "document-1",
      name: "record.pdf",
      format: "PDF",
      pageCount: 1,
      pages: [{
        page: 1,
        paragraphs: [{
          id: "block-1",
          text: "测试证据",
          sourceType: "native_text",
          confidence: null,
          charStart: 10,
          charEnd: 14,
          bbox: [72, 90, 140, 108],
        }],
      }],
      text: "前文内容\n测试证据",
      sizeLabel: "test",
      warnings: [],
      questionAnswers: [],
    } satisfies ParsedDocument;
    const result = {
      evidenceAnchorIds: ["block-1"],
      evidenceLocation: null,
      evidenceLocations: [],
    } as Pick<ReviewResult, "evidenceAnchorIds" | "evidenceLocation" | "evidenceLocations">;

    expect(evidenceAnchorRangesFor(result, document)).toEqual([{
      blockId: "block-1",
      page: 1,
      paragraph: 1,
      charStart: 10,
      charEnd: 14,
      bbox: [72, 90, 140, 108],
    }]);
  });
});
