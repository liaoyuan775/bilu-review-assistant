/**
 * 审查耗时格式化 — 将后端耗时（毫秒）转为 UI 可读文本。
 */
import type { ReviewTimings } from "./types";

/**
 * 格式化模型审查耗时。
 *
 * @returns 如 "模型审查 12.34 秒"，或空字符串（无耗时数据时）。
 */
export const formatModelReviewDuration = (
  timings: Pick<ReviewTimings, "modelReviewMs"> | undefined,
) => timings?.modelReviewMs === null || timings?.modelReviewMs === undefined
  ? ""
  : `模型审查 ${(timings.modelReviewMs / 1000).toFixed(2)} 秒`;
