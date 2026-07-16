import type { DemoSummary, HealthResponse, ManualStatus, ReviewMode, ReviewResult, ReviewTask } from "./types";

export class ApiError extends Error {
  constructor(public code: string, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

const parseResponse = async <T>(response: Response): Promise<T> => {
  const payload = await response.json().catch(() => null) as (T & { error?: { code?: string; message?: string } }) | null;
  if (!response.ok || !payload) throw new ApiError(payload?.error?.code ?? "request_failed", payload?.error?.message ?? "服务请求失败。");
  return payload;
};

export const getHealth = async () => parseResponse<HealthResponse>(await fetch("/api/v1/health"));

export const getDemos = async () => {
  const payload = await parseResponse<{ demos: DemoSummary[] }>(await fetch("/api/v1/demos"));
  return payload.demos;
};

export const createUploadTask = async (file: File) => {
  const body = new FormData();
  body.append("file", file);
  return parseResponse<{ taskId: string; status: string }>(await fetch("/api/v1/reviews", { method: "POST", body }));
};

export const createDemoTask = async (demoId: string, mode: ReviewMode) =>
  parseResponse<{ taskId: string; status: string }>(await fetch(`/api/v1/reviews/demos/${encodeURIComponent(demoId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  }));

export const getReviewTask = async (taskId: string) => parseResponse<ReviewTask>(await fetch(`/api/v1/reviews/${taskId}`));

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

export const submitDecision = async (taskId: string, ruleId: string, status: ManualStatus, reason: string) => {
  const payload = await parseResponse<{ result: ReviewResult }>(await fetch(`/api/v1/reviews/${taskId}/results/${ruleId}/decision`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status, reason }),
  }));
  return payload.result;
};
