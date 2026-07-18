# 内部询问笔录全流程审查实施计划

## Goal

在 `codex/template-complete-review` 分支完成内部模板驱动的上传、抽取、规则、定位、处理、产出、归档、脱敏质量和无损性能优化，并在全部门槛通过后合并到 `main`。

## Current Phase

Completed - 端到端验证、推送和合并 main

## Execution Plan

- [x] Task 1: 隔离基线与损坏媒体模板回归
- [x] Task 2: 容错 DOCX/PDF 解析和精确锚点
- [x] Task 3: 问答重建与模板说明隔离
- [x] Task 4: 版本化模板规则与确定性引擎
- [x] Task 5: Qwen 证据事实抽取与定向复核
- [x] Task 6: 文档、运行、问题、事件和产物持久化
- [x] Task 7: API 生命周期与归档门槛
- [x] Task 8: 民警模板审查工作台
- [x] Task 9: PDF/DOCX/JSON 产出和归档清单
- [x] Task 10: 脱敏金标准与真实模型质量门槛
- [x] Task 11: 质量不下降的性能评测与优化
- [x] Task 12: 端到端验证、推送和合并 main

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
| Unknown fact with evidence was classified as fully missing | 5 | Evaluate clarity before an empty normalized value so unknown remains incomplete |
| Legacy Qwen protocol tests were routed through the new domain extractor | 6 | Keep legacy demo protocol coverage isolated while uploads use the template adapter |
| Configured Qwen rejected the extraction schema `uniqueItems` keyword | 7 | Removed the unsupported keyword and added grammar-error tool fallback detection |
| Playwright CLI defaulted to a missing Chrome installation | 8 | Use the installed Microsoft Edge channel after confirming CLI browser support and the executable path |
| Task 8 full backend run had ten stale legacy-demo assertions and one expired temporary template path | 9 | Move legacy Qwen transport coverage to its direct adapter boundary; locate a current copy of the supplied template before rerunning the optional integration test |
| `gold-06-offline-delivery` live gate hit one 240-second read timeout, then two strict-schema validation failures in `offline_delivery` | 10 | Confirmed the other six domains completed and no stale verifier remained; retry only this case after isolating model load, without weakening schema or anchor checks |
| Isolated `gold-06` reproduced the same invalid `offline_delivery` payload on both retries | 11 | Root cause was a duplicate entity ID with a null correction instruction; added tested global-unique-ID instructions to the base prompt and retry feedback while preserving strict rejection |
| Formal three-run `gold-06` gate held at 94.12% because both repeat-entity arrays were empty | 12 | Gold text and rules require one withdrawal and one handoff; add the domain's entity arrays and required fields to the prompt, including the single-occurrence case, then re-run strict live gates |
| Entity-aware three-run `gold-06` gate reached 91.18% because unrelated timeline facts became incomplete | 13 | Isolated timeline extraction returned all missing; prompt hashes changed across regenerated but visibly identical DOCX files because paragraph IDs include raw package SHA. Make anchors depend on normalized document structure, then re-evaluate semantics |
| Diagnostic import used nonexistent `document_parser`, then assumed temporary gold DOCX was persisted | 14 | Switched to `app.services.parser` and generated the corpus inside `TemporaryDirectory`; neither failed attempt called the model |
| `gold-08` targeted recheck failed after 240s timeout, invalid anchor retry, and another 240s timeout | 15 | Isolated `contact_channels` completed its invalid-anchor correction in 55s; keep initial domain concurrency 2 but serialize targeted recheck domains to avoid long-document model-server contention |
| Serial targeted recheck reproduced the identical timeout / invalid-anchor / timeout sequence | 16 | Concurrency was not causal. Remove the serial-only change and make targeted recheck use a domain-filtered focus list and focus-only Schema instead of returning the full domain |
| `gold-08` reported 100% stability despite one run containing extra transfer/rebate entities | 17 | Live verifier compared only rule ID/status pairs and never called the existing semantic fingerprint. Add a regression and fingerprint the final extraction plus issues for every case/run |
| `gold-10` matched every gold fact/entity/rule but failed raw-value stability | 18 | Canonicalize only values that pass the existing gold-equivalence comparator, retain drift detection for non-equivalent facts/entities, and report drift paths without values |
| Performance probes had different raw hashes despite identical gold correctness | 19 | Gate every benchmark sample with the same 92-fact/entity/rule/anchor oracle and compare gold-semantic fingerprints instead of wording/anchor-choice serialization |
| Retry from an empty partial extraction could complete after only one domain | 20 | Preserve successful parallel domains; rerun all domains without a usable base; require 92 facts, entity collections, and 34 results before completion |
| Affected-domain re-review reset unrelated manual decisions | 21 | Preserve decisions by rule outside the affected domain and append an invalidation event for affected prior decisions |
| Stale model responses and separate audit writes could overwrite archive or leave partial history | 22 | Add SQLite revision/CAS and transactional task/event plus run/fact/issue writes; recheck revision after model awaits |
| Generated gold questions and production-derived statuses made the quality gate circular | 23 | Retain the generated contract suite and add four static hand-authored natural document mutations executed as both DOCX and PDF |
| Natural unclear case inferred entities incorrectly across count and money domains | 24 | Require placeholder entities for explicit counts with missing details and enforce online-transfer versus offline-delivery domain boundaries |

## References

- `docs/superpowers/specs/2026-07-18-template-complete-review-design.md`
- `docs/superpowers/plans/2026-07-18-template-complete-review.md`
