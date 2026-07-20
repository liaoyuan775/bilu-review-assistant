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

  it("expands one QA evidence block to every source paragraph", () => {
    const document = {
      id: "document-2",
      name: "record.docx",
      format: "DOCX",
      pageCount: 1,
      pages: [{
        page: 1,
        paragraphs: [
          { id: "q1", text: "问：问题", sourceType: "native_text", confidence: null, charStart: 0, charEnd: 5, bbox: null },
          { id: "q2", text: "问题续行", sourceType: "native_text", confidence: null, charStart: 6, charEnd: 10, bbox: null },
          { id: "a1", text: "答：答案", sourceType: "native_text", confidence: null, charStart: 11, charEnd: 16, bbox: null },
        ],
      }],
      text: "问：问题\n问题续行\n答：答案",
      sizeLabel: "test",
      warnings: [],
      questionAnswers: [],
      evidenceBlocks: [{ id: "qa-1", kind: "qa", text: "问：问题\n问题续行\n答：答案", paragraphIds: ["q1", "q2", "a1"], page: 1, paragraph: 1 }],
    } satisfies ParsedDocument;
    const result = { evidenceAnchorIds: ["qa-1"], evidenceLocation: null, evidenceLocations: [] } as Pick<ReviewResult, "evidenceAnchorIds" | "evidenceLocation" | "evidenceLocations">;

    expect(evidenceAnchorRangesFor(result, document).map((range) => range.blockId)).toEqual(["q1", "q2", "a1"]);
  });
});
