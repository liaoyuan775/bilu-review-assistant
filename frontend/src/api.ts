/**
 * API 客户端 — 封装与后端的所有 HTTP 通信。
 *
 * 设计要点：
 * - 所有请求通过 fetch 发送，无外部 HTTP 库依赖。
 * - 统一的响应解析（parseResponse）处理错误提取与类型转换。
 * - pollReviewTask 提供基于轮询的异步任务等待机制（最长 10 分钟）。
 * - ApiError 类让调用方可以通过 error.code 判断错误类型。
 */

import type { DemoSummary, HealthResponse, ManualStatus, ReportData, ReviewResult, ReviewSummary, ReviewTask, RuleSummary } from "./types";

/** API 通信错误 — 包含后端返回的 error.code 与 message。 */
export class ApiError extends Error {
  constructor(public code: string, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * 通用响应解析器 — 检查 HTTP 状态并提取后端 JSON 体。
 *
 * @throws ApiError — 当 HTTP 状态非 2xx 或响应体无法解析时抛出。
 */
const parseResponse = async <T>(response: Response): Promise<T> => {
  const payload = await response.json().catch(() => null) as (T & { error?: { code?: string; message?: string } }) | null;
  if (!response.ok || !payload) throw new ApiError(payload?.error?.code ?? "request_failed", payload?.error?.message ?? "服务请求失败。");
  return payload;
};

/** 健康检查。 */
export const getHealth = async () => parseResponse<HealthResponse>(await fetch("/api/v1/health"));

/** 获取演示样例列表。 */
export const getDemos = async () => {
  const payload = await parseResponse<{ demos: DemoSummary[] }>(await fetch("/api/v1/demos"));
  return payload.demos;
};

/** 获取规则列表。 */
export const getRules = async () => {
  const payload = await parseResponse<{ rules: RuleSummary[] }>(await fetch("/api/v1/rules"));
  return payload.rules;
};

/** 上传文件并发起审查任务。 */
export const createUploadTask = async (file: File) => {
  const body = new FormData();
  body.append("file", file);
  return parseResponse<{ taskId: string; status: string }>(await fetch("/api/v1/reviews", { method: "POST", body }));
};

/** 对演示样例发起审查任务。 */
export const createDemoTask = async (demoId: string) =>
  parseResponse<{ taskId: string; status: string }>(await fetch(`/api/v1/reviews/demos/${encodeURIComponent(demoId)}`, {
    method: "POST",
  }));

/** 获取单条审查任务的详情。 */
export const getReviewTask = async (taskId: string) => parseResponse<ReviewTask>(await fetch(`/api/v1/reviews/${taskId}`));

/**
 * 轮询等待审查任务完成。
 *
 * 每 500ms 查询一次任务状态，通过 onUpdate 回调实时更新 UI。
 * 最长等待 10 分钟，超时时抛出 ApiError。
 *
 * @returns 已完成或失败的任务对象。
 */
export const pollReviewTask = async (taskId: string, onUpdate: (task: ReviewTask) => void) => {
  const startedAt = Date.now();
  while (Date.now() - startedAt < 600_000) {
    const task = await getReviewTask(taskId);
    onUpdate(task);
    if (task.status === "completed" || task.status === "failed") return task;
    await new Promise((resolve) => window.setTimeout(resolve, 500));
  }
  throw new ApiError("task_timeout", "审查任务等待超时，请稍后重试。");
};

/** 提交人工分流决策。 */
export const submitDecision = async (taskId: string, ruleId: string, status: ManualStatus, reason: string) => {
  const payload = await parseResponse<{ result: ReviewResult }>(await fetch(`/api/v1/reviews/${taskId}/results/${ruleId}/decision`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status, reason }),
  }));
  return payload.result;
};

/** 完成复核并归档。 */
export const archiveReview = async (taskId: string) =>
  parseResponse<{ reviewStatus: "archived"; archivedAt: string }>(await fetch(`/api/v1/reviews/${taskId}/complete`, { method: "POST" }));

/** 获取审查历史列表。 */
export const getReviewHistory = async () => {
  const payload = await parseResponse<{ reviews: ReviewSummary[] }>(await fetch("/api/v1/reviews"));
  return payload.reviews;
};

/** 获取补问清单。 */
export const getFollowUps = async (taskId: string) => {
  const payload = await parseResponse<{ items: ReviewResult[] }>(await fetch(`/api/v1/reviews/${taskId}/follow-ups`));
  return payload.items;
};

/** 获取审查报告数据。 */
export const getReportData = async (taskId: string) =>
  parseResponse<ReportData>(await fetch(`/api/v1/reviews/${taskId}/report-data`));
