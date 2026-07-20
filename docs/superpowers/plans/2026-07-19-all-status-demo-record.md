# 全状态演示笔录 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一份可在前端运行完整审查的脱敏 DOCX，使 34 条模板规则均有结果，且“已覆盖、未询问、回答不清、事实矛盾、待人工判断”五类状态均至少出现 1 条、至多以 3 条为目标。

**Architecture:** 在现有测试夹具生成脚本中新增第六份文档，保留原模板的问答结构。文档用明确事实覆盖多数规则，对少量指定字段分别制造缺失、模糊、总额矛盾和条件不确定；后端演示目录增加一个 `qwen` 样例，前端沿用已有样例接口和中文展示。

**Tech Stack:** Python 3、python-docx、FastAPI、pytest、React/TypeScript、Vite。

## Global Constraints

- 仅使用虚构、脱敏的人名、账号、电话号码、地址和流水号。
- 所有条件规则都应提供相关事实，避免“不适用”掩盖五类结果演示。
- 不承诺模型输出精确条数；以每个目标状态至少 1 条作为验收条件。
- 保持现有 `mock`/`qwen` 执行模式与 API 契约不变。

---

### Task 1: 写入全状态演示笔录

**Files:**

- Modify: `backend/scripts/create_adaptation_fixtures.py`
- Create: `backend/test-fixtures/06-all-statuses-demo.docx`
- Test: `backend/tests/test_demo_cases.py`

**Interfaces:**

- Consumes: 原模板完成版和 `python-docx.Document`。
- Produces: 可由 `load_demo_document()` 解析的 `06-all-statuses-demo.docx`。

- [ ] **Step 1: 写失败测试**

```python
assert [case.id for case in DEMO_CASES][-1] == "case-06-all-statuses-demo"
assert DEMO_CASES[-1].path.name == "06-all-statuses-demo.docx"
assert DEMO_CASES[-1].path.is_file()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_demo_cases.py::test_demo_catalog_includes_all_statuses_demo`

Expected: FAIL，因为当前目录没有第六个样例。

- [ ] **Step 3: 最小实现**

在 `build()` 中追加 `Document(SOURCE)` 的第六份副本：为多数模板问答写入明确、互相一致的事实；针对四条不同规则分别留下未回答字段、描述性模糊字段、金额合计矛盾字段和无法确认的条件字段。写入后保存为 `OUT / "06-all-statuses-demo.docx"`。

- [ ] **Step 4: 运行测试确认通过**

Run: `backend\\.venv\\Scripts\\python.exe backend/scripts/create_adaptation_fixtures.py; backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_demo_cases.py::test_all_demo_docx_files_parse_into_non_empty_documents`

Expected: PASS，六份文件均能解析为非空 DOCX。

### Task 2: 将演示笔录接入中文前端样例

**Files:**

- Modify: `backend/app/data/demo_cases.py`
- Modify: `backend/tests/test_demo_cases.py`

**Interfaces:**

- Consumes: `DemoCase(id, filename, display_name, intent, executionMode)`。
- Produces: `GET /api/v1/demos` 返回第六个中文名称、`qwen` 模式样例。

- [ ] **Step 1: 写失败测试**

```python
assert [case.id for case in DEMO_CASES] == [
    "case-01-baseline", "case-02-line-breaks", "case-03-blank-answer",
    "case-04-long-answer", "case-05-table-and-symbols", "case-06-all-statuses-demo",
]
assert DEMO_CASES[-1].executionMode == "qwen"
assert "五类结果" in DEMO_CASES[-1].display_name
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_demo_cases.py::test_demo_catalog_includes_all_statuses_demo`

Expected: FAIL，因为目录中尚未注册第六个样例。

- [ ] **Step 3: 最小实现**

在 `DEMO_CASES` 末尾增加：

```python
DemoCase(
    "case-06-all-statuses-demo",
    "06-all-statuses-demo.docx",
    "06 五类结果演示笔录",
    "覆盖、遗漏、不清、矛盾、人工判断｜完整审查",
    "qwen",
)
```

并把前端样例说明中的范围从“02–05”更新为“02–06”。

- [ ] **Step 4: 运行测试确认通过**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_demo_cases.py`

Expected: PASS，API 返回六个样例且第六个可创建完整审查任务。

### Task 3: 运行完整审查并验证五类结果

**Files:**

- Create: `backend/test-results/all-statuses-demo-result.json`
- Create: `backend/test-results/all-statuses-demo-result.md`

**Interfaces:**

- Consumes: `POST /api/v1/reviews/demos/case-06-all-statuses-demo` 的完成任务。
- Produces: 规则总数和状态分布的可审计记录。

- [ ] **Step 1: 写失败验证断言**

```python
required = {"covered", "missing", "incomplete", "inconsistent", "needs_manual_review"}
assert len(task["results"]) == 34
assert required.issubset({result["status"] for result in task["results"]})
```

- [ ] **Step 2: 运行完整审查**

Run: 使用现有本地后端创建 `case-06-all-statuses-demo` 任务并轮询至完成，不把密钥写入文件或命令输出。

Expected: 34 条规则结果，五个目标状态均至少出现一次。

- [ ] **Step 3: 必要时仅调整文档问答内容**

若某个目标状态缺失，修改第六份夹具中对应的单条问答，使其满足规则引擎的明确状态条件后，重新生成并复测；不修改规则库来迎合演示文档。

- [ ] **Step 4: 完整回归检查**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_demo_cases.py backend/tests/test_template_rule_engine.py; npm run build`

Expected: pytest 退出码为 0，Vite 构建退出码为 0。
