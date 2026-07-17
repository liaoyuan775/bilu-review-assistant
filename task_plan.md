# 内部询问笔录全流程审查实施计划

## Goal

在 `codex/template-complete-review` 分支完成内部模板驱动的上传、抽取、规则、定位、处理、产出、归档、脱敏质量和无损性能优化，并在全部门槛通过后合并到 `main`。

## Current Phase

Task 4 - 版本化模板规则与确定性引擎

## Execution Plan

- [x] Task 1: 隔离基线与损坏媒体模板回归
- [x] Task 2: 容错 DOCX/PDF 解析和精确锚点
- [x] Task 3: 问答重建与模板说明隔离
- [ ] Task 4: 版本化模板规则与确定性引擎
- [ ] Task 5: Qwen 证据事实抽取与定向复核
- [ ] Task 6: 文档、运行、问题、事件和产物持久化
- [ ] Task 7: API 生命周期与归档门槛
- [ ] Task 8: 民警模板审查工作台
- [ ] Task 9: PDF/DOCX/JSON 产出和归档清单
- [ ] Task 10: 脱敏金标准与真实模型质量门槛
- [ ] Task 11: 质量不下降的性能评测与优化
- [ ] Task 12: 端到端验证、推送和合并 main

## Success Criteria

- 批准语料上的解析、问答、字段、实体、适用性、问题和证据锚点达到设计门槛。
- 民警可定位、标记、补问、记录答案、重审、产出并归档。
- 性能优化只有在质量指纹不变且 P50/P95 改善达到准入条件时保留。
- 本地和远端功能分支持续同步；最终 `main` 包含已验证交付。

## Errors

| Error | Attempt | Resolution |
|-------|---------|------------|
| Actual-template regression used an arbitrary character threshold | 1 | Assert exact structural coverage and key content instead |
| Question oracle omitted one same-paragraph question | 2 | Corrected structural count to 33 markers |
| Header/footer preservation changed the actual-template total from 144 to 145 blocks | 3 | Count the 144 body/table blocks separately from the retained footer |
| Scanned-PDF API regression expected the pre-anchor paragraph schema | 4 | Assert the stable ID/range/bbox fields explicitly |

## References

- `docs/superpowers/specs/2026-07-18-template-complete-review-design.md`
- `docs/superpowers/plans/2026-07-18-template-complete-review.md`
