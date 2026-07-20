# 七域模型笔记

首先就是我看document表似乎存储了原始文档的三种派生，是不是只需要存储一个page文档就够了？剩下俩是不是就是通过DocumentPage派生得到的？

```

 每条规则返回 COVER / NOT_APPLICABLE / NEEDS_MANUAL_REVIEW
```


```
return {
    "type": "object",#json schema约束
    "properties": {
        "facts":   { ... },    # 每个域不同（路径不同）,是每个域自己的规则点集合
        "entities": { ... },   # 每个域不同（有实体域才有内容）重复实体列表（比如多笔转账、多次取款）。没实体的域就传 {}
        "failedDomains": { ... }  # 全部一样：必须 []标记这个域是否失败。留着它是为了统一结构，正常情况必须是 []
    },
    "required": ["facts", "entities", "failedDomains"],
    "additionalProperties": false,
}
```

其中：每个facts结构如下：

clarity表示模型对valuep判断的信心

```
  facts: {
    "record.interviewers":    {value:"张三、李四", clarity:"clear", evidenceAnchorIds:["a001"]},
    "procedure.recusal_requested": {value:false, clarity:"clear", evidenceAnchorIds:["a015"]},
    "victim.name":           {value:"王五", clarity:"clear", evidenceAnchorIds:["a002"]},
    "victim.age":            {value:35, clarity:"clear", evidenceAnchorIds:["a003"]},
    "case.timeline":         {value:"2026年7月...", clarity:"clear", evidenceAnchorIds:["a020"]},
    "online_money.used":     {value:true, clarity:"clear", evidenceAnchorIds:["a035"]},
    "money.gross_loss":      {value:50000, clarity:"clear", evidenceAnchorIds:["a040"]},
    ...共 ~70 条事实
  },
  entities: {
    "transfers": [
      {id:"e1", entityType:"transfers", fields:{"time":{value:"7月18日",...}, "amount":{value:50000,...}}}
    ],
    "withdrawals": [
      {id:"e2", entityType:"withdrawals", fields:{"bank":{value:"工商银行",...}, ...}}
    ]
  }
```



#

提取笔录本身的基本信息：





## 业务域一：头信息与程序事项

### 组 1：笔录元信息（`record.*`）— 4 个路径

提取笔录本身的基本信息：

| 路径                  | 含义               | 例子                    |
| :-------------------- | :----------------- | :---------------------- |
| `record.interviewers` | 询问人（民警）     | "张三、李四"            |
| `record.respondent`   | 被询问人（受害人） | "王五"                  |
| `record.location`     | 询问地点           | "XX派出所"              |
| `record.started_at`   | 开始时间           | "2026年7月18日15时30分" |
| `record.signatures`   | 签名确认情况       | "已逐页签名"            |

### 组 2：程序性权利告知（`procedure.*`）— 7 个路径

检查民警有没有履行法定告知义务：

| 路径                                    | 含义                           | 值类型  |
| :-------------------------------------- | :----------------------------- | :------ |
| `procedure.rights_notice_read`          | 是否宣读权利义务告知书         | boolean |
| `procedure.truth_notice_confirmed`      | 是否告知要如实提供证据         | boolean |
| `procedure.statement_confirmed_true`    | 被询问人是否确认陈述属实       | boolean |
| `procedure.record_matches_statement`    | 笔录是否与其陈述一致           | boolean |
| `procedure.record_reviewed`             | 被询问人是否核对过笔录         | boolean |
| `procedure.recusal_requested`           | 是否申请过回避                 | boolean |
| `procedure.key_information_reconfirmed` | 关键信息是否重新确认           | boolean |
| `procedure.rights_request`              | 被询问人行使了什么权利（文本） | string  |

### 组 3：受害人基础信息（`victim.*`）— 7 个路径

| 路径                | 含义     |
| :------------------ | :------- |
| `victim.name`       | 姓名     |
| `victim.gender`     | 性别     |
| `victim.age`        | 年龄     |
| `victim.id_number`  | 身份证号 |
| `victim.phone`      | 联系电话 |
| `victim.education`  | 文化程度 |
| `victim.employer`   | 工作单位 |
| `victim.occupation` | 职业     |

## 域二：`case_timeline` — 案件经过时间线（无实体）

**事实路径 22 个**：

### 组 1：案件基本信息（`case.*`）

| 路径                   | 含义                   | 值类型 |
| :--------------------- | :--------------------- | :----- |
| `case.initial_contact` | 首次接触方式描述       | string |
| `case.initial_channel` | 首次接触渠道           | string |
| `case.contact_method`  | 主要联系方式           | string |
| `case.fraud_method`    | 诈骗手段               | string |
| `case.fraud_tools`     | 诈骗工具（APP/网站等） | string |
| `case.location`        | 案发地点               | string |
| `case.channel_changes` | 渠道变更情况           | string |
| `case.payment_summary` | 付款方式概述           | string |
| `case.rebate_summary`  | 返利情况概述           | string |
| `case.payment_reason`  | 付款原因               | string |
| `case.total_loss`      | 总损失金额             | number |
| `case.report_reason`   | 报案原因               | string |
| `case.timeline`        | 完整经过陈述           | string |

### 组 2：时间线精确时间（`timeline.*`）

| 路径                          | 含义          | 值类型 |
| :---------------------------- | :------------ | :----- |
| `timeline.first_contact_at`   | 首次联系时间  | string |
| `timeline.incident_at`        | 案发时间      | string |
| `timeline.incident_community` | 案发社区/小区 | string |
| `timeline.incident_district`  | 案发区/县     | string |
| `timeline.incident_street`    | 案发街道/路   | string |

### 组 3：隐私信息泄露（`privacy.*`）

| 路径                            | 含义               | 值类型  |
| :------------------------------ | :----------------- | :------ |
| `privacy.disclosure_occurred`   | 是否发生过信息泄露 | boolean |
| `privacy.disclosed_information` | 泄露了哪些信息     | string  |
| `privacy.disclosure_reason`     | 泄露原因           | string  |
| `privacy.disclosure_time`       | 泄露时间           | string  |

### 组 4：持续联系动机（`motive.*`）

| 路径                              | 含义           | 值类型 |
| :-------------------------------- | :------------- | :----- |
| `motive.continued_contact_reason` | 持续联系的原因 | string |

------

## 域三：`contact_channels` — 联系渠道

**事实路径 7 个 + 1 种实体**：

### 事实（facts）

| 路径                      | 含义             | 值类型  |
| :------------------------ | :--------------- | :------ |
| `contact.initial_channel` | 初始接触渠道     | string  |
| `contact.initial_account` | 初始联系账号     | string  |
| `contact.initial_content` | 初始联系内容     | string  |
| `contact.chat_used`       | 是否使用聊天工具 | boolean |
| `contact.phone_used`      | 是否使用电话     | boolean |
| `contact.voice_call`      | 是否使用语音通话 | boolean |
| `contact.switch_count`    | 渠道切换次数     | number  |

### 实体：`contact_switches`（每次切换渠道的记录）

| 字段                    | 含义           | 值类型 |
| :---------------------- | :------------- | :----- |
| `time`                  | 切换时间       | string |
| `channel`               | 切换到什么渠道 | string |
| `account`               | 对方的账号     | string |
| `important_information` | 重要信息       | string |
| `details`               | 详细情况       | string |

------

## 域四：`risk_and_evidence` — 风险与证据（无实体）

**事实路径 18 个**：

### 组 1：反诈宣传（`prevention.*`）

| 路径                                    | 含义               | 值类型  |
| :-------------------------------------- | :----------------- | :------ |
| `prevention.received_publicity`         | 是否接受过反诈宣传 | boolean |
| `prevention.community_police_publicity` | 社区民警是否宣传过 | boolean |
| `prevention.anti_fraud_app_installed`   | 是否安装了反诈APP  | boolean |

### 组 2：风险识别（`risk.*`）

| 路径                            | 含义                    | 值类型  |
| :------------------------------ | :---------------------- | :------ |
| `risk.account_loss_reported`    | 是否有账户挂失报案      | boolean |
| `risk.loss_report_time`         | 挂失报案时间            | string  |
| `risk.payment_warning_received` | 转账时是否收到预警      | boolean |
| `risk.payment_warning_channel`  | 预警渠道（银行/反诈等） | string  |
| `risk.payment_warning_content`  | 预警内容                | string  |
| `risk.phone_warning_received`   | 是否收到电话预警        | boolean |
| `risk.phone_card_real_name`     | 电话卡是否实名          | boolean |
| `risk.victim_chat_real_name`    | 受害人聊天工具是否实名  | boolean |
| `risk.suspect_chat_real_name`   | 嫌疑人聊天工具是否实名  | boolean |
| `risk.post_report_transfers`    | 报案后是否还有转账      | boolean |

### 组 3：证据保留（`evidence.*`）

| 路径                                 | 含义             | 值类型  |
| :----------------------------------- | :--------------- | :------ |
| `evidence.can_provide`               | 能否提供证据     | boolean |
| `evidence.record_types`              | 有哪些记录类型   | string  |
| `evidence.records_retained`          | 记录是否完整保留 | boolean |
| `evidence.voice_recording_exists`    | 是否有录音       | boolean |
| `evidence.voice_recording_available` | 录音能否提供     | boolean |

------

## 域五：`online_money` — 线上资金

**事实路径 9 个 + 2 种实体**：

### 事实（facts）

| 路径                            | 含义                      | 值类型  |
| :------------------------------ | :------------------------ | :------ |
| `online_money.used`             | 是否有线上资金行为        | boolean |
| `online_money.total`            | 线上资金总金额            | number  |
| `online_money.transfer_count`   | 转账笔数                  | number  |
| `money.gross_loss`              | 总转出金额                | number  |
| `money.net_loss`                | 净损失金额                | number  |
| `money.rebate_total`            | 返利总金额                | number  |
| `money.credentials_disclosed`   | 是否透露过支付密码/验证码 | boolean |
| `money.remote_control_used`     | 是否被远程控制            | boolean |
| `money.transfer_control_method` | 转账操作方式              | string  |

### 实体一：`transfers`（每笔转账记录）

| 字段                | 含义       | 值类型 |
| :------------------ | :--------- | :----- |
| `time`              | 转账时间   | string |
| `amount`            | 金额       | number |
| `payment_method`    | 支付方式   | string |
| `payer_account`     | 付款账号   | string |
| `recipient_account` | 收款账号   | string |
| `transaction_id`    | 交易流水号 | string |

### 实体二：`rebates`（每笔返利记录）

| 字段                | 含义       | 值类型 |
| :------------------ | :--------- | :----- |
| `time`              | 返利时间   | string |
| `amount`            | 返利金额   | number |
| `method`            | 返利方式   | string |
| `recipient_account` | 收款账号   | string |
| `transaction_id`    | 交易流水号 | string |

------

## 域六：`offline_delivery` — 线下交付

**事实路径 11 个 + 2 种实体**：

### 事实（facts）

| 路径                           | 含义                 | 值类型  |
| :----------------------------- | :------------------- | :------ |
| `offline.used`                 | 是否有线下交付行为   | boolean |
| `offline.handoff_count`        | 线下交付次数         | number  |
| `offline.appointment_time`     | 约定交付时间         | string  |
| `offline.appointment_location` | 约定交付地点         | string  |
| `offline.appointment_amount`   | 约定交付金额/价值    | number  |
| `offline.property_source`      | 财物来源             | string  |
| `offline.suspect_appointment`  | 嫌疑人是否约定了交付 | boolean |
| `cash.withdrawal_count`        | 取款次数             | number  |
| `cash.bank_appointment`        | 银行是否预约         | boolean |
| `cash.bank_warning_received`   | 取款时银行是否预警   | boolean |
| `cash.bank_warning_channel`    | 银行预警方式         | string  |

### 实体一：`withdrawals`（每次银行取款记录）

| 字段      | 含义      | 值类型 |
| :-------- | :-------- | :----- |
| `bank`    | 银行名称  | string |
| `branch`  | 支行/网点 | string |
| `address` | 银行地址  | string |
| `time`    | 取款时间  | string |
| `amount`  | 取款金额  | number |

### 实体二：`offline_handoffs`（每次线下交接记录）

| 字段                     | 含义                  | 值类型 |
| :----------------------- | :-------------------- | :----- |
| `time`                   | 交接时间              | string |
| `location`               | 交接地点              | string |
| `property_type`          | 财物类型（现金/实物） | string |
| `amount_or_value`        | 金额或价值            | number |
| `method`                 | 交接方式              | string |
| `recipient_or_logistics` | 接收方或物流信息      | string |

------

## 域七：`special_scenarios` — 特殊场景标记（无实体）

**事实路径 3 个**：

| 路径                                        | 含义             | 值类型  |
| :------------------------------------------ | :--------------- | :------ |
| `special.gambling_related`                  | 是否涉赌         | boolean |
| `special.ecommerce_logistics_impersonation` | 是否冒充电商物流 | boolean |
| `case.additional_statement`                 | 补充陈述内容     | string  |

------

### 汇总

| 域                  | 事实数 | 实体类型数 | 实体类型                          |
| :------------------ | :----- | :--------- | :-------------------------------- |
| `header_procedure`  | 21     | 0          | —                                 |
| `case_timeline`     | 22     | 0          | —                                 |
| `contact_channels`  | 7      | 1          | `contact_switches`                |
| `risk_and_evidence` | 18     | 0          | —                                 |
| `online_money`      | 9      | 2          | `transfers`, `rebates`            |
| `offline_delivery`  | 11     | 2          | `withdrawals`, `offline_handoffs` |
| `special_scenarios` | 3      | 0          | —                                 |
| **合计**            | **91** | **5**      |                                   |

---

---

# 询问笔录智能审查系统 — 七域模型技术说明（汇报版）

> 本文档面向非技术背景的领导汇报使用，说明系统的核心设计思路和完整工作流程。

---

## 一、一句话概括

**系统做的事情：把一份询问笔录交给 AI 模型，模型从中提取出 91 个关键信息点，然后通过 34 条确定性规则自动判断这份笔录问得全不全、有没有矛盾，最后生成一份审查报告给审查员。**

---

## 二、整体工作流程

```
上传笔录文档（DOCX/PDF）
        │
        ▼
第一步：文档解析
  将笔录按段落拆分，识别哪些是"问-答"、哪些是"笔录抬头"
  输出：结构化的文档对象
        │
        ▼
第二步：七域事实抽取
  AI 模型并行阅读 7 个业务维度
  每个维度提取若干条结构化信息（叫什么、转了多少钱、有没有风险提示等）
  输出：91 条事实 + 实体记录（转账明细等）
        │
        ▼
第三步：规则引擎判定
  34 条确定性规则（纯代码，不依赖 AI）逐条检查事实是否完整、一致
  输出：34 条审查结论（通过/缺失/矛盾/不适用）
        │
        ▼
第四步：前端展示
  审查员看到 34 条结论，每条附有原文出处、缺了什么、建议问什么
  审查员可以逐条确认、忽略或标记为已处理
```

---

## 三、七个业务域

系统将笔录内容划分为 **7 个业务维度**，AI 模型对这 7 个维度并行提取信息：

| 业务域 | 提取信息量 | 提取什么内容 | 有什么实体 | 用途 |
|:---|---|---|---|---|
| **1. 笔录头与程序事项** | 21 条 | 询问人、被询问人、时间地点、签名、权利义务告知、回避申请、受害人身份信息 | 无 | 检查笔录程序是否合法 |
| **2. 案件时间线** | 22 条 | 诈骗手法、首次联系时间、案发时间地点、信息是否泄露、持续联系原因 | 无 | 还原案件全貌 |
| **3. 联系渠道** | 7 条 | 首次怎么联系、用了什么聊天工具、电话、渠道切换次数 | 每次切换渠道的记录 | 追溯嫌疑人联系方式 |
| **4. 风险与证据** | 18 条 | 是否接受过反诈宣传、转账时银行是否预警、电话是否实名、证据是否保留 | 无 | 评估受害人风险意识和证据保全情况 |
| **5. 线上资金** | 9 条 | 是否线上转账、总金额、转账笔数、净损失、返利、是否透露密码 | 每笔转账记录、每笔返利记录 | 核对资金流向 |
| **6. 线下交付** | 11 条 | 是否有线下交付、取款次数、银行预约、嫌疑人是否约定了交付 | 每次银行取款记录、每次线下交接记录 | 核对线下资金/实物交付 |
| **7. 特殊场景** | 3 条 | 是否涉赌、是否冒充电商物流、补充陈述 | 无 | 标记特殊案件类型 |
| **合计** | **91 条** | | **5 种实体类型** | |

### 什么是"实体"？

实体就是**重复发生的具体事件**。比如受害人转了 3 笔钱，AI 会逐条提取这 3 笔转账的明细：

```
第一笔：7月18日 10:00，转账 10000 元，手机银行，建行卡 → 工行卡
第二笔：7月18日 14:00，转账 20000 元，手机银行，建行卡 → 农行卡
第三笔：7月19日 09:00，转账 20000 元，支付宝，余额 → 对方账户
```

5 种实体类型：联系渠道切换、线上转账、返利、银行取款、线下实物交接。

---

## 四、34 条审查规则

AI 模型提取完 91 条信息后，**规则引擎**（纯代码，不调用 AI）逐条判定。

### 检查类型一：基本信息是否问到（20 条）

这是最基础的检查——笔录里该问的是不是都问了。

| 规则示例 | 检查什么 | 可能的结论 |
|---|---|---|
| 笔录头与签名结构完整 | 笔录时间、地点、询问人、被询问人、签名是否清晰 | 通过 / 缺失（签名没问） |
| 被害人基本情况 | 姓名、性别、年龄、身份证号等 8 项是否清晰 | 通过 / 不完整（缺了工作单位） |
| 如实作答义务告知 | 民警是否告知了"要如实回答" | 通过 / 缺失 |
| 报案原因与案件概述 | 诈骗手法、案发地、总损失金额等 6 项是否清晰 | 通过 / 不完整 |

### 检查类型二：条件触发才检查（7 条）

先看"某种行为是否发生"，发生了再检查细节，没发生就标记"不适用"。

| 规则示例 | 触发条件 | 触发后检查什么 |
|---|---|---|
| 多次转账风险提示 | 转账超过 1 笔 | 银行有没有给你发风险提示？提示了什么？ |
| 电话卡实名与预警 | 用了电话联系 | 电话卡实名了吗？收到预警了吗？ |
| 线下交付信息 | 有线下交付行为 | 嫌疑人约了你几点在哪交钱？ |

### 检查类型三：实体数量和字段是否完整（3 条）

| 规则示例 | 检查什么 |
|---|---|
| 逐笔转账资金流向 | 说转了 3 笔，AI 是否提取了 3 条记录？每条的时间、金额、账户是否都填了？ |
| 逐次取款明细 | 说取了 2 次，AI 是否提取了 2 条记录？每条银行、网点、金额是否都填了？ |
| 线下交付明细 | 说交了 3 次，AI 是否提取了 3 条记录？ |

### 检查类型四：数值和时间一致性检查（4 条）

这是 AI 做不了、但代码可以精确计算的部分：

| 规则示例 | 检查逻辑 |
|---|---|
| 净损失计算 | 总转出 - 返利 = 净损失？（如 50000 - 200 = 49800） |
| 转账合计 | 各笔转账金额之和 = 受害人说的总金额？ |
| 时间先后 | 首次联系时间是否早于案发时间？ |

---

## 五、前端展示的五种状态

34 条规则判定完后，每条规则展示一个状态：

| 状态 | 含义 | 图标色 | 代表什么 |
|---|---|---|---|
| **已通过** | 规则通过 | 绿色 | 该问的都问到了，校验通过 |
| **不适用** | 规则不适用 | 灰色 | 该行为没发生（比如没用线下交付），无需关注 |
| **缺失** | 完全缺失 | 红色 | 笔录完全没问到相关内容，需要补问 |
| **不完整** | 部分缺失 | 黄色 | 问到了但回答不清或部分缺失 |
| **矛盾** | 事实矛盾 | 橙色 | 金额对不上、时间顺序颠倒、数量不匹配 |

每条结论附带：
- **原文证据**：AI 引用的是笔录中哪几段话
- **缺失清单**：具体哪些信息没问到
- **补问建议**：建议审查员追问什么问题
- **严重等级**：高/中/低

---

## 六、与传统人工审查的对比

| 对比项 | 传统人工审查 | 本系统辅助审查 |
|---|---|---|
| 阅读笔录 | 逐字逐句阅读全部内容 | AI 自动提取关键信息 |
| 检查完整性 | 靠经验判断是否问全了 | 规则逐条核对 91 个信息点 |
| 核对金额 | 人工加总各笔转账 | 自动求和并与声称金额比对 |
| 发现矛盾 | 靠记忆和反复翻看 | 自动检测金额/时间/数量不一致 |
| 标记问题 | 手动标注 | 自动生成 34 条结构化结果 |
| 输出结果 | 依赖个人经验和细致程度 | 标准化、可复现、不遗漏 |

---

## 七、数据汇总

| 指标 | 数量 |
|---|---|
| 业务域 | 7 个 |
| AI 提取的信息点 | 91 条 |
| 实体类型（重复记录） | 5 种 |
| 审查规则 | 34 条 |
| 前端展示状态 | 5 种 |
