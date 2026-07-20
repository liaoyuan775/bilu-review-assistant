import { describe, expect, it } from "vitest";

import {
  archiveBlockers,
  countTemplateStatuses,
  processingLabel,
  groupTemplateResults,
  nextActionableIssueId,
  sectionTemplateResults,
  summaryStatuses,
} from "./templateReviewState";
import type { ManualStatus, ReviewResult, ReviewStatus, RuleStatus, ReviewTask, TaskStatus } from "./types";


const result = (
  ruleId: string,
  group: string,
  status: RuleStatus,
  manualStatus: ManualStatus = "pending",
  severity: ReviewResult["severity"] = "high",
): ReviewResult => ({
  ruleId,
  ruleName: ruleId,
  category: group,
  group,
  status,
  missingFacts: [],
  evidence: "",
  evidenceLocation: null,
  evidenceLocations: [],
  evidenceAnchorIds: [],
  reason: "",
  suggestedQuestion: "",
  advisories: [],
  manualDecision: { status: manualStatus, reason: manualStatus === "ignored" ? "测试依据" : "" },
  source: "内部模板",
  severity,
});


const task = (overrides: Partial<ReviewTask> = {}): ReviewTask => ({
  id: "task-1",
  mode: "qwen",
  status: "completed" as TaskStatus,
  document: null,
  documentId: "document-1",
  documentVersionId: "version-1",
  reviewRunId: "run-1",
  extractionPayload: null,
  victimProfile: null,
  results: [],
  failedDomains: [],
  acknowledgedWarnings: [],
  artifacts: [
    { id: "a1", type: "review_pdf", filename: "review.pdf", sha256: "a".repeat(64), sizeBytes: 1 },
    { id: "a2", type: "follow_up_docx", filename: "follow-up.docx", sha256: "b".repeat(64), sizeBytes: 1 },
    { id: "a3", type: "structured_json", filename: "review.json", sha256: "c".repeat(64), sizeBytes: 1 },
    { id: "a4", type: "archive_manifest", filename: "manifest.json", sha256: "d".repeat(64), sizeBytes: 1 },
  ],
  requiredArtifacts: ["review_pdf", "follow_up_docx", "structured_json", "archive_manifest"],
  reviewStatus: "in_review" as ReviewStatus,
  archivedAt: null,
  createdAt: "2026-07-18T00:00:00Z",
  updatedAt: "2026-07-18T00:00:00Z",
  ...overrides,
});


describe("template review state", () => {
  it("groups by server-provided names and puts actionable issues first", () => {
    const groups = groupTemplateResults([
      result("CASE-OK", "CASE", "covered"),
      result("MONEY-BAD", "MONEY", "inconsistent"),
      result("CASE-MISS", "CASE", "missing"),
      result("PROC-NA", "PROC", "not_applicable"),
    ]);

    expect(groups.map((group) => group.name)).toEqual(["CASE", "MONEY", "PROC"]);
    expect(groups[0].results.map((item) => item.ruleId)).toEqual(["CASE-MISS", "CASE-OK"]);
  });

  it("sections open issues before closed, not applicable, and covered results", () => {
    const closed = result("CLOSED", "CASE", "missing", "resolved", "high");
    closed.manualDecision.reason = "已核实";
    const sections = sectionTemplateResults([
      result("OK", "CASE", "covered"),
      result("LOW-INCOMPLETE", "MONEY", "incomplete", "pending", "low"),
      result("NA", "PROC", "not_applicable"),
      closed,
      result("MEDIUM-INCONSISTENT", "CASE", "inconsistent", "pending", "medium"),
      result("HIGH-MISSING", "RISK", "missing", "pending", "high"),
    ]);

    expect(sections.map((section) => section.key)).toEqual([
      "open", "closed", "not_applicable", "covered",
    ]);
    expect(sections[0].groups.flatMap((group) => group.results.map((item) => item.ruleId))).toEqual([
      "HIGH-MISSING", "MEDIUM-INCONSISTENT", "LOW-INCOMPLETE",
    ]);
  });

  it("counts all six deterministic statuses", () => {
    const statuses: RuleStatus[] = [
      "covered", "missing", "incomplete", "inconsistent", "not_applicable", "needs_manual_review",
    ];

    expect(countTemplateStatuses(statuses.map((status, index) => result(`R${index}`, "CASE", status)))).toEqual({
      covered: 1,
      missing: 1,
      incomplete: 1,
      inconsistent: 1,
      not_applicable: 1,
      needs_manual_review: 1,
    });
  });

  it("keeps not applicable visible in the review summary", () => {
    expect(summaryStatuses).toEqual([
      "missing", "incomplete", "inconsistent", "needs_manual_review", "not_applicable", "covered",
    ]);
  });

  it("does not add a processing label to already covered rules", () => {
    expect(processingLabel(result("OK", "CASE", "covered"))).toBeNull();
    expect(processingLabel(result("MISSING", "CASE", "missing"))).toBe("待处理");
  });

  it("selects the next pending actionable issue and wraps", () => {
    const results = [
      result("A", "CASE", "missing", "resolved"),
      result("B", "CASE", "inconsistent"),
      result("C", "CASE", "covered"),
      result("D", "CASE", "needs_manual_review"),
    ];

    expect(nextActionableIssueId(results, "A")).toBe("B");
    expect(nextActionableIssueId(results, "D")).toBe("B");
  });

  it("reports archive gates for failed domains, warnings, artifacts, and high-risk issues", () => {
    const blocked = task({
      failedDomains: ["case_timeline"],
      document: {
        id: "doc",
        name: "test.docx",
        format: "DOCX",
        pageCount: 1,
        pages: [],
        text: "",
        sizeLabel: "test",
        warnings: [{ code: "media_corrupt", message: "媒体损坏", partName: "word/media/image1.png" }],
        questionAnswers: [],
      },
      acknowledgedWarnings: [],
      artifacts: [],
      results: [result("CASE-001", "CASE", "missing")],
    });

    expect(archiveBlockers(blocked).map((item) => item.code)).toEqual([
      "failed_domains",
      "unresolved_warnings",
      "missing_artifacts",
      "unresolved_issues",
    ]);
  });

  it.each([
    ["low", "pending"],
    ["medium", "supplemented"],
    ["high", "confirmed"],
  ] as const)("blocks archive for unresolved %s-risk issues in %s", (severity, manualStatus) => {
    const blockers = archiveBlockers(task({
      results: [result("CASE-001", "CASE", "incomplete", manualStatus, severity)],
    }));

    expect(blockers).toContainEqual({
      code: "unresolved_issues",
      label: "未闭环问题",
      count: 1,
    });
  });

  it.each([
    ["resolved", "已人工核对。"],
    ["not_applicable", "本案不涉及该场景。"],
    ["ignored", "经确认不再处理。"],
  ] as const)("allows archive for terminal decision %s with a reason", (manualStatus, reason) => {
    const item = result("CASE-001", "CASE", "missing", manualStatus, "low");
    item.manualDecision.reason = reason;

    expect(archiveBlockers(task({ results: [item] }))).toEqual([]);
  });
});
