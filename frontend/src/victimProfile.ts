/**
 * 被害人信息工具 — 头像显示与样式变体生成。
 */
/**
 * 获取被害人姓氏的首字符（用于头像显示）。
 * 如果姓名为空，返回 "?"。
 */
export const getVictimInitial = (name: string) => name.trim().charAt(0) || "?";

/**
 * 基于姓名的哈希值生成头像样式变体（variant-1 ~ variant-6）。
 *
 * 相同姓名始终生成相同的变体，确保同一人的头像风格一致。
 * 使用 31 作为乘数（Java String.hashCode 的惯用值），取模 6 后 +1。
 */
export const getVictimAvatarVariant = (name: string) => {
  let hash = 0;
  for (const character of name.trim() || "?") {
    hash = (hash * 31 + (character.codePointAt(0) ?? 0)) >>> 0;
  }
  return `variant-${(hash % 6) + 1}`;
};
