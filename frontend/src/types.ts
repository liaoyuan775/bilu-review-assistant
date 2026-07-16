export type TaskStatus = "idle" | "uploading" | "parsing" | "recognizing" | "checking" | "validating" | "completed" | "failed";
export type ReviewMode = "qwen" | "local";

export type RuleStatus = "covered" | "missing" | "incomplete" | "not_applicable";

export type ManualStatus = "pending" | "confirmed" | "supplemented" | "ignored";

export interface DocumentPage {
  page: number;
  paragraphs: DocumentParagraph[];
}

export interface DocumentParagraph {
  text: string;
  sourceType: "native_text" | "table" | "vision";
  confidence: number | null;
}

export interface ParsedDocument {
  id: string;
  name: string;
  format: "DOCX" | "PDF" | "SAMPLE";
  pageCount: number;
  pages: DocumentPage[];
  text: string;
  sizeLabel: string;
}

export interface EvidenceLocation {
  page: number;
  paragraph: number;
}

export interface ManualDecision {
  status: ManualStatus;
  reason: string;
}

export interface ReviewResult {
  ruleId: string;
  ruleName: string;
  category: string;
  group: "三现" | "四流";
  status: RuleStatus;
  missingFacts: string[];
  evidence: string;
  evidenceLocation: EvidenceLocation | null;
  reason: string;
  suggestedQuestion: string;
  advisories: string[];
  manualDecision: ManualDecision;
  source: string;
}

export interface ReviewTask {
  id: string;
  mode: ReviewMode;
  status: TaskStatus;
  document: ParsedDocument | null;
  results: ReviewResult[];
  createdAt: string;
  updatedAt: string;
  errorCode?: string;
  errorMessage?: string;
}

export interface DemoSummary {
  id: string;
  name: string;
  pageCount: number;
  intent: string;
}

export interface HealthResponse {
  ok: boolean;
  qwen: {
    configured: boolean;
    reachable: boolean;
    model: string | null;
  };
  ruleCount: number;
}
