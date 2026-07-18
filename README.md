# Bilu 电信诈骗询问笔录审查助手

项目面向办案民警复核电信网络诈骗询问笔录。系统上传脱敏 DOCX/PDF 后，按内部《询问笔录模版(1).docx》完成文档标准化、问答重建、事实抽取、确定性规则校验、原文定位、补问处理、报告生成和归档。

该工具只辅助发现漏问、回答含糊、数量/金额/时间矛盾和证据定位问题，不作案件定性、法律结论、责任判断或证据效力判断。审查结果必须由民警复核。

## 审查依据

- 唯一业务规则来源是内部模板，不再以“三现四流”作为最终审查口径。
- 规则目录版本为 `1.0.0`，对应模板 SHA-256 `c37c38663c282a8acd6f4ca2e10e609c517f64c33895c73843a0b4f6dbdee329`。
- 模板正文包含 144 个结构块和 33 个问题标记，落地为 33 条问题规则和 1 条笔录结构规则。
- 34 条规则覆盖笔录结构、程序告知、案情经过、预警劝阻、风险操作、现金交付、时间地点、隐私泄露、线索来源、动机、联系渠道、线上资金、线下交付、特殊场景和证据材料等 15 组内容。
- 模型只抽取带原文证据的事实；是否漏问、不完整、不一致或不适用由后端确定性规则计算。

## 完整流程

1. 上传单份脱敏 DOCX/PDF，保存内容寻址的原件和 SHA-256。
2. 容错读取 DOCX/PDF，隔离损坏的非必要媒体，保留页、段、字符范围和 PDF 坐标。
3. 重建同段、跨段和跨页问答，将括号内模板说明与案件回答分离。
4. 使用项目当前配置的 `Qwen3.6-35B-A3B`，按七个独立业务域返回 strict JSON Schema 事实和重复实体。
5. 校验证据锚点、实体数量与字段，再计算 34 条模板规则状态。
6. 在工作台按问题定位原文，确认、忽略、加入补问或记录补问答案；只复审受影响业务域。
7. 生成审查 PDF、补问 DOCX、结构化 JSON 和 SHA-256 清单。
8. 通过失败域、未确认警告、高风险待处理项和产物完整性门禁后归档；归档后只读。

任务、文档版本、模型运行、事实、问题、人工事件和产物元数据保存在 SQLite。原件和生成文件保存在受控产物目录，不把文件字节写入数据库。

## 支持范围

- DOCX：正文、表格、页眉页脚、嵌入图片和损坏非必要媒体的容错读取。
- PDF：文本型、扫描型及混合文档；原生文本块保留页面坐标。
- 单文件上限 20 MB。
- 不支持旧版二进制 `.doc`，请先另存为 `.docx` 或 `.pdf`。
- 扫描页和文档图片可能发送到当前配置的多模态模型服务，生产使用前必须完成网络、权限、存储和脱敏制度评审。

## 结构化抽取与校验

七个事实域为 `header_procedure`、`case_timeline`、`contact_channels`、`risk_and_evidence`、`online_money`、`offline_delivery` 和 `special_scenarios`。每个域拥有固定事实路径和实体字段 Schema。

- 采样温度固定为 `0`。
- Schema、工具调用和证据锚点均采用白名单校验。
- clear/unclear/unknown 事实必须引用真实段落锚点；missing 事实不得引用锚点。
- 联系渠道切换、转账、返款、取现和线下交付逐项保留，实体 ID 必须全域唯一。
- 单域结构、证据或临时网络错误最多尝试 3 次；鉴权和模型未配置错误直接终止。
- 初次抽取完成后，只对适用性仍含糊的事实路径使用缩小后的 Schema 定向复核。
- 任一必需业务域失败都会阻止审查完成和归档，不合并部分结果冒充完整审查。

## 环境准备

```powershell
npm install
npm --prefix frontend install
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

将 `backend/.env.example` 复制为 `backend/.env.local`，配置 OpenAI 兼容模型接口。不要提交 API Key。

```dotenv
QWEN_BASE_URL=http://127.0.0.1:6001/v1
QWEN_API_KEY=replace-with-your-api-key
QWEN_MODEL=Qwen3.6-35B-A3B
```

## 启动

```powershell
npm run dev
```

- 前端：<http://127.0.0.1:4173>
- 后端：<http://127.0.0.1:8787/api/v1>
- Swagger：<http://127.0.0.1:8787/api/docs>

## 主要接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/health` | 模型状态和模板规则数量 |
| GET | `/api/v1/rules` | 34 条模板规则摘要 |
| POST | `/api/v1/reviews` | 上传文件并创建审查任务 |
| GET | `/api/v1/reviews/{task_id}` | 查询解析、审查、问题和产物状态 |
| GET | `/api/v1/reviews/{task_id}/versions` | 查询文档版本 |
| POST | `/api/v1/reviews/{task_id}/issues/{rule_id}/actions` | 记录人工处置 |
| POST | `/api/v1/reviews/{task_id}/issues/{rule_id}/follow-up-answer` | 记录补问答案并复审 |
| POST | `/api/v1/reviews/{task_id}/domains/{domain}/retry` | 重试失败业务域 |
| POST | `/api/v1/reviews/{task_id}/artifacts/generate` | 生成四类归档产物 |
| GET | `/api/v1/reviews/{task_id}/artifacts/{artifact_id}` | 下载并校验产物 |
| POST | `/api/v1/reviews/{task_id}/archive` | 执行归档门禁并转为只读 |

完整接口以 [OpenAPI 快照](docs/openapi.json) 为准。

## 验证

```powershell
# 自动化回归与生产构建
npm run test
npm run build

# 12 组契约 DOCX/PDF、4 组手写自然案例双格式、136 个规则变体和敏感形态扫描
backend\.venv\Scripts\python.exe backend\scripts\verify_template_quality.py --offline

# 当前模型真实质量门禁，连续三轮
backend\.venv\Scripts\python.exe backend\scripts\verify_template_quality.py --live --runs 3 --domain-concurrency 7 --output .runtime\template-quality.json

# 性能基线与候选，候选必须保持质量指纹并改善至少 10%
backend\.venv\Scripts\python.exe backend\scripts\benchmark_template_review.py --runs 5 --domain-concurrency 2 --output .runtime\benchmark-before.json
backend\.venv\Scripts\python.exe backend\scripts\benchmark_template_review.py --runs 5 --domain-concurrency 7 --baseline .runtime\benchmark-before.json --output .runtime\benchmark-after.json
```

测试语料使用显式合成命名空间，并扫描完整身份证号、手机号、银行卡号、URL 和公网 IP 形态。`.runtime` 中的报告和临时渲染文件不提交。

## 运行边界

- 当前没有身份认证、角色授权、案件系统集成、持久任务队列或自动数据保留策略。
- SQLite 和本地产物目录适合受控单机演示/试点，不等同于已完成正式公安内网部署评审。
- DOCX 的页码是逻辑页；PDF 保留原页和原生文本坐标。OCR 图片区域目前不保证精确坐标级定位。
- 规则和流程实现经过自动化及脱敏语料验证，不代表业务主管部门已经完成规则批准。

实现设计见 [模板全流程设计](docs/superpowers/specs/2026-07-18-template-complete-review-design.md)，性能结论见 [性能报告](docs/template-review-performance.md)。
