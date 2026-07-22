# 域 JSON Schema 字段说明设计

## 目标

将 `backend/domain-contracts/*.json` 已有的中文字段说明自动写入模型实际接收的严格 JSON Schema，降低相似事实和实体字段之间的语义错填，同时保持现有输出结构、六域并发和重试策略不变。

## 结构

- 每个事实对象增加 `description`，值取自 `FactContract.description`。
- 每个事实的 `value` 属性增加同一字段说明，使说明紧邻模型实际填写的位置。
- `clarity` 增加统一说明，明确 `clear`、`unclear`、`unknown`、`missing` 的含义。
- `evidenceAnchorIds` 增加统一说明，明确直接证据要求和空数组规则。
- 每个实体数组增加实体说明。
- 实体的 `id`、`entityType`、`fields` 增加简短通用说明；每个实体字段按事实字段相同方式生成说明。

## 数据来源

不增加 `valueDescription` 等新合同字段。本次只复用现有 `description`，避免提示词、合同和 Schema 出现多份独立语义来源。六个域的特殊边界仍由各自提示词文件负责。

## 不变项

- 模型输出仍只有 `facts`、`entities`、`failedDomains`。
- 每个事实仍只输出 `value`、`clarity`、`evidenceAnchorIds`。
- `required`、`type`、`enum`、范围、`additionalProperties: false` 和锚点枚举不变。
- `description` 是模型语义提示，不作为服务端业务正确性的强制验证条件。
- 不修改 34 条规则、文档解析、证据块、前端和接口结构。

## 验证

1. 单元测试断言事实、值、实体和实体字段均携带合同说明。
2. 现有域 Schema 与抽取测试全部通过，证明结构约束未改变。
3. 使用当前 Qwen 模型执行一次 Schema 探测；若服务端拒绝 `description`，不扩大上线范围并保留测试证据。
4. 探测通过后使用 `06-all-statuses-demo.docx` 完成一次真实六域审查，核对 34 条结果、失败域和重试次数。
