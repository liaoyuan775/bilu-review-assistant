# Evidence-Block Driven Document Model

## Goal

保留 DOCX 原始段落，同时把问答对作为模型判断、规则证据和前端高亮的统一证据块，避免问题续行丢失、模型只引用“问”以及高亮范围过窄。

## Current Root Causes

- `ParsedDocument.pages[].paragraphs[]` 是原始段落；`QuestionAnswerBlock` 只是并行派生结构。
- `reconstruct_question_answers` 在尚未遇到 `答：` 时不会追加无标记续行，因此多段问题可能丢失。
- `QuestionAnswerBlock.id` 没有进入模型 Schema；模型使用 `anchorIds` 中的段落 ID。
- `ReviewResult.evidenceLocations` 由段落 ID 反查，前端也按段落位置高亮，因此单个“问”锚点只高亮单个段落。

## Design

新增 `EvidenceBlock` 投影，不删除或改写原始 `DocumentParagraph`：

- 非 QA 段落按原顺序各自成为一个 block。
- 一个 QA 从 `问：` 开始，收集问题续行、`答：` 和答案续行，成为一个 block。
- QA block 使用稳定 hash ID；block 保留 `paragraphIds` 作为内部追溯，不暴露给模型作为证据选择项。
- 模型 Schema 的 evidence anchor enum 只包含 evidence block ID。
- 规则结果保留 `evidenceAnchorIds`，但值改为 block ID。
- 前端优先按 block ID 高亮整个 block；旧任务没有 block ID 时继续使用现有页/段落位置兼容逻辑。

## Boundaries

- `VictimProfile` 仍是独立的正则提取，不并入 Qwen QA block。
- 原始 `pages[].paragraphs[]` 保持 API 和 SQLite 兼容，便于审计、下载和旧任务读取。
- 不把多个无关 QA 合并；每个问答对一个 block ID。
- 非 QA 文本不丢弃、不拼接到相邻 QA。

## Verification

- 状态机测试覆盖多段问题续行、多段答案续行、无答问题和非 QA 段落顺序。
- 合同渲染测试确认模型只看到 block ID。
- 规则/结果测试确认一个 QA block 生成一个高亮位置，旧段落结果仍可渲染。
- 用 `06-all-statuses-demo.docx` 验证模型请求、结果证据和浏览器高亮范围。
