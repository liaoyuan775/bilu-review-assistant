/**
 * 证据定位辅助函数 — 提取与判断证据位置。
 *
 * 兼容两种数据格式：
 * - 新版: result.evidenceLocations（数组）
 * - 旧版: result.evidenceLocation（单字段）
 *
 * isEvidencePage / isEvidenceParagraph 用于在文档视图中高亮证据。
 */
import type { EvidenceLocation, ReviewResult } from "./types";

/**
 * 从审查结果中提取证据定位列表。
 *
 * 优先使用 evidenceLocations（新版），降级使用 evidenceLocation（旧版兼容）。
 */
export const evidenceLocationsFor = (
  result: Pick<ReviewResult, "evidenceLocation" | "evidenceLocations"> | null,
): EvidenceLocation[] => {
  if (!result) return [];
  if (result.evidenceLocations && result.evidenceLocations.length > 0) return result.evidenceLocations;
  return result.evidenceLocation ? [result.evidenceLocation] : [];
};

/** 判断某页是否包含证据（用于高亮证据页标签）。 */
export const isEvidencePage = (locations: EvidenceLocation[], page: number) =>
  locations.some((location) => location.page === page);

/** 判断某段是否包含证据（用于高亮证据段落背景）。 */
export const isEvidenceParagraph = (locations: EvidenceLocation[], page: number, paragraph: number) =>
  locations.some((location) => location.page === page && location.paragraph === paragraph);
