# Bilu Review Assistant（笔录审查助手）V0.2

项目采用 React + TypeScript 前端和 FastAPI 后端。上传脱敏 PDF 或 DOCX 后，系统先标准化文档并调用当前配置的多模态 Qwen 识别图像文字，再通过独立模型调用依据七条“三现四流”工作规则审查，最后程序化校验证据和结果。

该工具用于询问笔录辅助复盘，不作案件定性、法律结论、责任判断或证据效力判断，结果必须人工复核。

## 支持范围

- PDF：文本型、扫描型、文本与图片混合文档。
- DOCX：正文、表格和内嵌图片；页码为逻辑分页。
- 单文件不超过 20 MB。
- 不支持旧版二进制 `.doc`，请先另存为 `.docx` 或 `.pdf`。

原始文件、解析文本、审查结果和人工决定只保存在后端进程内存中，服务重启后清空。原始内容和识别文本会发送到 `.env.local` 配置的模型服务，只能上传脱敏材料。

当前证据位置指向标准化文档的页码和段落号。PDF 保留原始页码；DOCX 使用逻辑页。DOCX 表格保持正文顺序，但内嵌图片识别结果当前追加到正文块之后；PDF 内嵌图片识别结果保留原页，但不保存图片坐标。因此当前可以回查标准化原文和 PDF 原页，不能宣称已经支持 Word 物理页或图片区域的精确高亮定位。

## 三现四流

七条强制规则为：案发现场、涉案现物、电子现痕、人员流、信息流、资金流、行为流。规则的 `requiredFacts` 决定 `covered`、`missing`、`incomplete`、`not_applicable` 状态。

百度千帆示例中的账号、聊天、APP、寄递、返利和第三方人员字段只作为 `referenceHints` 补充模型理解，可生成“补充关注”，不得进入强制缺失字段或改变状态。

## 结构化输出与重试

上传审查首先使用模型服务端 `strict JSON Schema`，顶层固定为七个规则 ID；每条规则的全部 `requiredFacts` 也是固定键，模型只能逐项选择 `covered`、`missing` 或 `unknown`。总体状态和 `missingFacts` 由后端确定性生成，补充项没有进入硬缺失字段的入口。模型只选择 `evidenceLocation`，最终证据文字由后端从对应页码和段落直接读取，不采用模型转述。

返回内容还会经过 Pydantic 类型校验以及程序化的页码、段落和规则一致性校验。JSON Schema只负责结构约束，不替代事实判断和原文位置校验。

- 证据或业务校验失败：携带稳定错误码、规则 ID、字段和纠正要求，用相同 strict JSON Schema 完整重生成一次。
- 临时网络错误、HTTP 408/429/5xx：用 strict JSON Schema 重试一次。
- 模型接口明确不支持 strict JSON Schema：第二次改用复用同一 Schema 的 Function Calling。
- 鉴权、文件格式和解析错误不重试。
- 每个审查任务最多调用两次审查模型；第二次仍失败时整单失败，不合并或返回第一次的部分结果。
- 上传审查不会降级到纯提示词 JSON 或本地关键词分析。

模型请求、结构解析和确定性校验是独立函数。未来切换到 LangChain `with_structured_output(method="json_schema", strict=True)` 时，只替换模型请求适配层，不修改三现四流规则和证据校验。

## 环境准备

```powershell
cd bilu-review-assistant
npm install
npm --prefix frontend install
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

将 `backend/.env.example` 复制为 `backend/.env.local`，填写兼容 OpenAI `/chat/completions` 且支持图像输入的模型配置。不要提交真实 API Key。

## 启动

```powershell
npm run dev
```

- 前端：<http://127.0.0.1:4173>
- 后端接口：<http://127.0.0.1:8787/api/v1>
- Swagger：<http://127.0.0.1:8787/api/docs>

真实文件上传固定使用 Qwen，不接受本地关键词降级。本地分析器仅用于内置脱敏演示样例；模型、响应或证据校验失败时，任务整体失败并清空结果。

## 核心接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/health` | 模型状态与规则数量 |
| GET | `/api/v1/rules` | 七条三现四流规则摘要 |
| GET | `/api/v1/demos` | 脱敏样例列表 |
| POST | `/api/v1/reviews` | 上传 PDF/DOCX 并创建模型审查任务 |
| POST | `/api/v1/reviews/demos/{demo_id}` | 用脱敏样例创建任务 |
| GET | `/api/v1/reviews/{task_id}` | 查询任务、标准原文和结果 |
| PATCH | `/api/v1/reviews/{task_id}/results/{rule_id}/decision` | 提交人工处理 |

## 验证

```powershell
npm run test
npm run build
npm run verify:model
```

`verify:model` 使用内置脱敏样例验证当前模型能否返回完整的 7 条结果。失败时只输出稳定错误码和非敏感状态，不打印 API Key 或请求正文。

规则依据与补充资料边界详见 [设计说明](docs/superpowers/specs/2026-07-16-multimodal-three-present-four-flows-review-design.md)。
