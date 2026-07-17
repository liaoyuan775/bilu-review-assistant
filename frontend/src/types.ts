/**
 * 核心类型定义 — 前端全部数据模型的 TypeScript 类型声明。
 *
 * 类型体系与后端 Pydantic 模型保持一一对应，确保前后端通信的类型安全。
 * 所有接口类型均通过 API 层（api.ts）从后端 JSON 响应反序列化得到。
 */

/** 审查任务状态机 — 与后端 TaskStatus 枚举同步。 */
export type TaskStatus = "idle" | "uploading" | "parsing" | "recognizing" | "checking" | "validating" | "completed" | "failed";

/** 审查模式 — QWEN: 模型审查 / MOCK: 快速模拟 / LOCAL: 旧历史兼容。 */
export type ReviewMode = "qwen" | "mock" | "local";

/** 复核状态 — in_review: 可修改 / archived: 只读归档。 */
export type ReviewStatus = "in_review" | "archived";

/** 单条规则的审查结论。 */
export type RuleStatus = "covered" | "missing" | "incomplete" | "inconsistent" | "not_applicable" | "needs_manual_review";

/** 人工处置状态。 */
export type ManualStatus = "pending" | "confirmed" | "supplemented" | "ignored" | "resolved" | "not_applicable";

/** 文档页面 — 包含段落列表。 */
export interface DocumentPage {
  page: number;
  paragraphs: DocumentParagraph[];
}

/** 段落 — 包含文本、来源类型和 OCR 置信度。 */
export interface DocumentParagraph {
  id: string;
  text: string;
  sourceType: "native_text" | "table" | "vision" | "header" | "footer";
  confidence: number | null;
  charStart: number;
  charEnd: number;
  bbox: [number, number, number, number] | null;
}

export interface DocumentWarning {
  code: string;
  message: string;
  partName: string | null;
}

export interface QuestionAnswerBlock {
  id: string;
  question: string;
  answer: string;
  guidance: string[];
  anchorIds: string[];
  answerClarity: "clear" | "blank" | "unclear";
}

/** 标准化文档 — 统一 PDF/DOCX/SAMPLE 的内部表示。 */
export interface ParsedDocument {
  id: string;
  name: string;
  format: "DOCX" | "PDF" | "SAMPLE";
  pageCount: number;
  pages: DocumentPage[];
  text: string;
  sizeLabel: string;
  warnings: DocumentWarning[];
  questionAnswers: QuestionAnswerBlock[];
}

/** 被害人信息 — 全部字段可为空。 */
export interface VictimProfile {
  name: string | null;
  gender: string | null;
  age: number | null;
  ethnicity: string | null;
  idNumber: string | null;
  employer: string | null;
  address: string | null;
  contact: string | null;
}

/** 证据定位 — 页号+段号，均从 1 开始。 */
export interface EvidenceLocation {
  page: number;
  paragraph: number;
}

/** 人工处置记录。 */
export interface ManualDecision {
  status: ManualStatus;
  reason: string;
}

/** 确定性校验通过的规则审查结果。 */
export interface ReviewResult {
  ruleId: string;
  ruleName: string;
  category: string;
  group: string;
  status: RuleStatus;
  missingFacts: string[];
  evidence: string;
  evidenceLocation: EvidenceLocation | null;
  evidenceLocations?: EvidenceLocation[];
  evidenceAnchorIds: string[];
  reason: string;
  suggestedQuestion: string;
  advisories: string[];
  manualDecision: ManualDecision;
  source: string;
  severity: "high" | "medium" | "low";
}

export interface ArtifactSummary {
  id: string;
  type: string;
  filename: string;
  sha256: string;
  sizeBytes: number;
}

/** 审查任务聚合根 — 包含一份笔录的全部审查状态。 */
export interface ReviewTask {
  id: string;
  mode: ReviewMode;
  status: TaskStatus;
  document: ParsedDocument | null;
  documentId: string | null;
  documentVersionId: string | null;
  reviewRunId: string | null;
  extractionPayload: Record<string, unknown> | null;
  victimProfile: VictimProfile | null;
  results: ReviewResult[];
  failedDomains: string[];
  acknowledgedWarnings: string[];
  artifacts: ArtifactSummary[];
  requiredArtifacts: string[];
  timings?: ReviewTimings;
  reviewStatus: ReviewStatus;
  archivedAt: string | null;
  createdAt: string;
  updatedAt: string;
  errorCode?: string;
  errorMessage?: string;
}

/** 任务各阶段耗时统计。 */
export interface ReviewTimings {
  parseMs: number | null;
  modelReviewMs: number | null;
  modelGroupsMs: Record<string, number>;
  totalMs: number | null;
}

/** 审查历史列表中的单条摘要。 */
export interface ReviewSummary {
  id: string;
  documentName: string;
  createdAt: string;
  updatedAt: string;
  reviewStatus: ReviewStatus;
  pendingCount: number;
}

/** 审查报告数据。 */
export interface ReportData {
  id: string;
  document: ParsedDocument | null;
  victimProfile: VictimProfile | null;
  mode: ReviewMode;
  createdAt: string;
  archivedAt: string | null;
  reviewStatus: ReviewStatus;
  results: ReviewResult[];
}

/** 演示样例摘要。 */
export interface DemoSummary {
  id: string;
  name: string;
  pageCount: number;
  intent: string;
  executionMode: "mock" | "qwen";
}

/** 规则摘要（对前端暴露的简化版本）。 */
export interface RuleSummary {
  id: string;
  name: string;
  category: string;
  group: string;
  scope: string;
  requiredFacts: string[];
  source: string;
}

/** 健康检查响应。 */
export interface HealthResponse {
  ok: boolean;
  qwen: {
    configured: boolean;
    reachable: boolean;
    model: string | null;
  };
  ruleCount: number;
}
