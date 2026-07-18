# 七份 DOCX 演示案例 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 `output/doc` 的七份真实 DOCX 替换旧三案例，01 提供明确标识的快速 mock 结果，02-07 走真实 Qwen 审查链路。

**Architecture:** 新增后端白名单案例目录，所有案例都读取真实 DOCX 并经过解析。01 在解析后生成与当前规则和真实页段对应的固定 mock 结果；02-07 复用 Qwen 审查。旧 `local` 只保留历史反序列化兼容，不再允许创建。

**Tech Stack:** FastAPI, Pydantic, python-docx, React, TypeScript, pytest, Vitest。

## Global Constraints

- 只允许白名单中的七个 DOCX，不接受任意路径。
- 旧三个短文本案例和旧 ID 不再进入运行时。
- 01 的结果、历史和报告必须标识为 mock，不得显示为 Qwen。
- 02-07 不允许回退 mock 或关键词分析。
- 保留 SQLite 旧 `local` 记录的读取兼容。
- 普通测试不得访问外部模型服务。

---

### Task 1: 七案例目录与真实文档加载

**Files:**
- Create: `backend/app/demo_cases.py`
- Modify: `backend/app/data.py`
- Modify: `backend/app/models.py`
- Test: `backend/tests/test_demo_cases.py`

**Interfaces:**
- Produces: `DEMO_CASES`, `get_demo_case(case_id)`, `load_demo_document(case)` and `DemoExecutionMode`/`ReviewMode.MOCK`。

- [ ] 写失败测试，断言七个 ID 顺序、文件存在、旧 ID 不存在、七份 DOCX 均可解析。
- [ ] 运行 `backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_demo_cases.py`，确认因目录模块缺失而失败。
- [ ] 实现固定白名单目录和 DOCX 加载，移除 `data.py` 旧内置文本，只保留 `RULES`。
- [ ] 运行聚焦测试，确认通过。

### Task 2: 01 mock 与 02-07 Qwen 任务

**Files:**
- Create: `backend/app/services/mock_review.py`
- Modify: `backend/app/services/review.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/models.py`
- Modify: `backend/scripts/verify_qwen.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Produces: `build_mock_review(document) -> list[ReviewResult]`；`process_demo` 根据目录中固定 `executionMode` 分流。

- [ ] 写失败 API 测试：列表七条；01 为 mock 且不调用 Qwen；02 为 qwen 且调用 Qwen；旧 ID 404；客户端 mode 被忽略/不再接受。
- [ ] 运行聚焦 API 测试确认失败。
- [ ] 01 使用真实解析文档和动态证据位置构造七条 mock 结果；02-07 调用 Qwen；删除运行时 `analyze_document` 调用。
- [ ] `verify_qwen.py` 改为解析 02 DOCX 后调用模型。
- [ ] 运行后端测试，修正所有旧夹具引用但不触网。

### Task 3: 前端七案例与来源标识

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Test: existing Vitest suite plus build.

**Interfaces:**
- Consumes: `DemoSummary.executionMode: "mock" | "qwen"`；创建演示任务不再传 mode。

- [ ] 更新类型和 API，移除前端模式选择参数。
- [ ] 新建页显示七案例；01 标记“快速演示”，02-07 标记“Qwen 完整审查”；离线时仅 01 可用。
- [ ] 报告模式显示 mock/Qwen/旧 local 三种来源。
- [ ] 运行 `npm --prefix frontend run test` 和 `npm --prefix frontend run build`。

### Task 4: 文档与集成验证

**Files:**
- Modify: `README.md`
- Modify: `docs/product-requirements-v0.1.md`
- Modify: `docs/project-technical-guide.md`
- Refresh: `docs/openapi.json`

- [ ] 更新七案例和双通道说明，删除旧三案例口径。
- [ ] 导出当前 OpenAPI 快照。
- [ ] 运行 `npm test`、`npm run build`、`git diff --check`。
- [ ] 浏览器验证七案例、01 mock、节点结果来源和 02 Qwen 启动路径。
