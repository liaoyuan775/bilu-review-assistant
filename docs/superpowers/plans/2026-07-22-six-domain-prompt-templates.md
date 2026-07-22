# Six-Domain Prompt Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the six short domain instruction files into complete domain semantic templates while preserving the shared strict-output template and generated JSON Schema.

**Architecture:** `domain-extraction.txt` remains the single source for strict output, anchor, entity, and correction-feedback rules. Each file under `prompt-templates/domains` gains the same five-section structure and domain-specific clarity/inference guidance; `render_domain_prompt` continues concatenating these existing sources without code changes.

**Tech Stack:** Python 3.11+, pytest, FastAPI/Pydantic models, JSON Schema text contracts, Qwen OpenAI-compatible API.

## Global Constraints

- Keep exactly six extraction domains: `header_procedure`, `case_timeline`, `contact_channels`, `risk_and_evidence`, `online_money`, `offline_delivery`.
- Do not change `domain-extraction.txt`, `domain-contracts/*.json`, `template_rules.json`, Schema generation, retry policy, concurrency, or frontend code.
- Preserve `strict=true`, `enable_thinking=false`, `temperature=0`, and the prohibition on plain/tool fallback.
- Do not add keyword-based evidence filtering, model re-judging, extra requests, or field-level retry.
- Domain templates must contain no real personal data or case text.

---

### Task 1: Lock Domain Template Structure and Isolation

**Files:**
- Modify: `backend/tests/test_domain_contracts.py`
- Test: `backend/tests/test_domain_contracts.py`

**Interfaces:**
- Consumes: `DOMAIN_ORDER` and `render_domain_prompt(document, contract, fact_paths=None, correction=None) -> str`.
- Produces: Regression tests defining the required section headings, one unique semantic guard per domain, and prompt isolation.

- [x] **Step 1: Write the failing tests**

Add these imports and tests:

```python
from pathlib import Path

from app.core.models import ParsedDocument
from app.review.domain_contract_rendering import render_domain_prompt


PROMPT_ROOT = Path(__file__).resolve().parents[1] / "prompt-templates" / "domains"
DOMAIN_TEMPLATE_SECTIONS = (
    "【本域目标】",
    "【包含与排除】",
    "【clarity 判定】",
    "【字段与实体规则】",
    "【禁止推断】",
)
DOMAIN_UNIQUE_GUARDS = {
    "header_procedure": "不得从签名存在推断程序告知已经完成",
    "case_timeline": "案发地点按完整地点一次抽取",
    "contact_channels": "不得从存在电话号码推断使用过聊天软件",
    "risk_and_evidence": "不得从发生过通话推断存在录音",
    "online_money": "不得从总损失反推转账笔数或逐笔金额",
    "offline_delivery": "不得从取现推断现金已经交付",
}


def _empty_document() -> ParsedDocument:
    return ParsedDocument(
        name="提示词结构测试.docx",
        format="DOCX",
        pageCount=0,
        pages=[],
        text="",
        sizeLabel="0 KB",
    )


def test_domain_prompt_files_are_complete_semantic_templates():
    for domain in DOMAIN_ORDER:
        text = (PROMPT_ROOT / f"{domain.replace('_', '-')}.txt").read_text(encoding="utf-8")
        for section in DOMAIN_TEMPLATE_SECTIONS:
            assert section in text, f"{domain} missing {section}"
        assert DOMAIN_UNIQUE_GUARDS[domain] in text


def test_rendered_prompt_contains_only_its_domain_semantic_guard():
    document = _empty_document()
    for domain in DOMAIN_ORDER:
        prompt = render_domain_prompt(document, DOMAIN_CONTRACTS[domain])
        assert DOMAIN_UNIQUE_GUARDS[domain] in prompt
        assert prompt.count("clarity 只能是 clear、unclear、unknown、missing") == 1
        for other_domain, guard in DOMAIN_UNIQUE_GUARDS.items():
            if other_domain != domain:
                assert guard not in prompt
```

- [x] **Step 2: Run tests to verify RED**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_domain_contracts.py -k "domain_prompt_files_are_complete or rendered_prompt_contains_only"
```

Expected: both tests fail because the existing three-line domain files do not contain the five headings or unique guard text.

- [x] **Step 3: Commit the failing contract tests only after implementation is ready for the same changeset**

Do not commit a permanently red branch. Keep the verified RED output in the task record, then continue directly to Task 2.

---

### Task 2: Expand the Six Domain Semantic Templates

**Files:**
- Modify: `backend/prompt-templates/domains/header-procedure.txt`
- Modify: `backend/prompt-templates/domains/case-timeline.txt`
- Modify: `backend/prompt-templates/domains/contact-channels.txt`
- Modify: `backend/prompt-templates/domains/risk-and-evidence.txt`
- Modify: `backend/prompt-templates/domains/online-money.txt`
- Modify: `backend/prompt-templates/domains/offline-delivery.txt`
- Test: `backend/tests/test_domain_contracts.py`
- Test: `backend/tests/test_template_extraction.py`

**Interfaces:**
- Consumes: Existing `{{DOMAIN_INSTRUCTIONS}}` placeholder and contract-generated field descriptions.
- Produces: Six UTF-8 text templates containing the five exact section headings and the corresponding unique guard from Task 1.

- [x] **Step 1: Replace `header-procedure.txt`**

The file must state:

```text
【本域目标】
只抽取笔录头部、被询问人结构信息、程序告知、权利确认、回避申请、陈述真实性和笔录核对事实。

【包含与排除】
包含合同列出的 record、victim 和 procedure 事实。案件经过、联系渠道、资金、风险操作和证据材料由其他域抽取，本域不得概括。

【clarity 判定】
原文明确肯定或明确否定均为 clear；“无、否、没有其他要求、不申请回避、不适用”是有效清晰回答。问题存在但答案含糊时为 unclear；无法确认是否发生时为 unknown；没有提供该事项时为 missing。已阅读告知书且回答没有其他要求，分别表示已阅读和无额外请求，不得判为缺失。

【字段与实体规则】
按合同类型返回布尔值、原文或 null。结构区已有的被询问人姓名直接复用 victim.name，不生成重复字段。本域没有重复实体，不得自行增加人员、签名或程序事件数组。

【禁止推断】
不得从签名存在推断程序告知已经完成。不得从笔录格式完整推断当事人已阅读告知书、已理解义务或未申请回避；每项都必须有对应原文证据。
```

- [x] **Step 2: Replace `case-timeline.txt`**

```text
【本域目标】
只抽取报案原因、诈骗手法、连续经过、关键时间、完整案发地点、隐私泄露、付款原因、持续联系原因和补充陈述。

【包含与排除】
包含合同列出的 case、timeline、privacy 和 motivation 事实。联系渠道、联系人账号、逐笔资金、总损失、返款、取现和线下交付由专门域抽取，本域不得重复概括。

【clarity 判定】
原文给出确定经过、时间、地点或原因时为 clear；只说“大概、可能、记不清具体情况”等且无法得到确定值时为 unclear；原文明确表示无法确认是否发生时为 unknown；没有提供对应事项时为 missing。“是否还有补充”的明确回答“没有、无其他补充”为 clear，问题空答为 missing。

【字段与实体规则】
案发地点按完整地点一次抽取，保留原文已有的省、市、区县、街道、社区或具体场所信息，不拆分为多个层级字段，也不补齐原文没有的行政区。连续经过保持事实顺序，不把不同问答中的无关内容拼成新情节。本域不生成联系、转账、取现或交付实体。

【禁止推断】
不得从报案地推断案发地，不得从户籍地或居住地推断操作地点。不得从总损失反推逐笔资金，不得从存在联系推断具体联系账号。不得把提问中的示例诈骗类型当成实际诈骗手法。
```

- [x] **Step 3: Replace `contact-channels.txt`**

```text
【本域目标】
只抽取首次联系渠道、首次联系标识、聊天工具使用与实名情况，以及后续联系人、账号或渠道切换过程。

【包含与排除】
包含合同列出的 contact 事实和 contact_switches 实体。诈骗经过、付款原因、资金金额、风险操作和证据材料由其他域抽取；本域只保留识别联系关系所需的信息。

【clarity 判定】
原文明示电话、短信、聊天软件、网址或其他渠道及其标识时为 clear；回答含糊、账号残缺或无法区分具体联系人时为 unclear；明确表示无法判断是否使用聊天工具或是否实名时为 unknown；没有提供该事项时为 missing。电话或短信号码本身就是有效联系标识，不得因没有聊天账号而标为缺失。

【字段与实体规则】
仅当原文明确使用聊天软件时 contact.chat_used 才为 true；明确未使用时为 false。每次联系人、账号或渠道发生切换都单独生成 contact_switches 实体，按原文顺序保留，不合并不同人员。important_information 同时承载账号、人员和关键联系详情，不新增 details 字段。

【禁止推断】
不得从存在电话号码推断使用过聊天软件，不得从聊天昵称推断账号实名，不得从同一平台推断前后联系人是同一人，不得从付款账户反推联系账号。
```

- [x] **Step 4: Replace `risk-and-evidence.txt`**

```text
【本域目标】
只抽取反诈宣传与预警劝阻、危险操作、远程控制、录音、聊天记录、转账材料及其他证据是否存在、留存和可提供。

【包含与排除】
包含合同列出的 prevention、warning、risk 和 evidence 事实。联系账号、诈骗经过和资金明细由其他域抽取；本域只记录风险行为及证据状态。

【clarity 判定】
明确回答“有、是、收到、无、否、未收到、没有留存”均为 clear，并按合同类型返回真实肯定或否定值。回答“好像、可能、不确定、记不清”时为 unclear；明确表示无法判断聊天工具是否实名、材料是否仍在或能否提供时为 unknown；没有回答对应问题时为 missing。录音问题空答必须为 missing。

【字段与实体规则】
区分一般反诈宣传、针对本案的预警和实际劝阻，不得混为一个事实。证据是否存在、是否留存、是否能提供分别按原文抽取；一种材料明确存在不代表其他材料存在。record_types 只列原文明示的材料类型。

【禁止推断】
不得从发生过通话推断存在录音，不得从使用过聊天软件推断聊天记录仍然留存，不得从知道反诈知识推断收到过本案预警，不得从公安已经取证推断被害人本人可以提供全部材料。
```

- [x] **Step 5: Replace `online-money.txt`**

```text
【本域目标】
只抽取线上资金是否发生、总额、笔数、操作人或操作方式、逐笔转账信息和返款汇总。

【包含与排除】
包含合同列出的 money、online_money 事实和 transfers 实体。联系渠道、诈骗经过、取现和线下交付由其他域抽取；本域不得把取现或购买实物记录当成线上转账。

【clarity 判定】
原文明示金额、笔数、时间、账户或支付方式时为 clear，即使不同位置的数值相互矛盾也必须保留原值，不得改成 unclear。数值表达本身含糊时为 unclear；原文明示无法确认是否发生或由谁操作时为 unknown；没有提供对应字段时为 missing。明确没有线上转账或没有返款是清晰否定。

【字段与实体规则】
每一笔线上转账单独生成 transfers 实体，保持原文笔数和顺序，不合并同日、同账户或同金额交易。time、amount、payment_method、payer_account、recipient_account 为核心明细；transaction_id 为辅助字段，缺失不影响其他字段。返款只抽取合同保留的 money.rebate_total，不生成返款实体数组。

【禁止推断】
不得从总损失反推转账笔数或逐笔金额，不得用逐笔金额之和覆盖原文明示总额，不得自动修正算术矛盾，不得从收款账户推断联系人身份，不得把提现、现金交付或购买黄金计入线上转账实体。
```

- [x] **Step 6: Replace `offline-delivery.txt`**

```text
【本域目标】
只抽取取现、现金或实物来源、线下交付、邮寄物流，以及逐次取现和逐次交付明细。

【包含与排除】
包含合同列出的 cash、offline 事实，以及 withdrawals 和 offline_handoffs 实体。线上转账、联系渠道和诈骗经过由其他域抽取。本域必须区分“取出财物”和“已经交付财物”两个事件。

【clarity 判定】
原文明示取现、购买实物、交付、邮寄或明确表示没有使用某种方式时为 clear；时间、地点、金额或接收对象表达含糊时为 unclear；明确表示无法确认是否交付或交给谁时为 unknown；没有提供对应事项时为 missing。明确没有邮寄、物流或线下交付是清晰否定，不得标为缺失。

【字段与实体规则】
每次取现单独生成 withdrawals 实体，每次现金、黄金或其他实物交付单独生成 offline_handoffs 实体，不合并不同事件。取现的 bank、branch、time、amount 为核心字段，address 为辅助字段；银行名称、网点和完整地点按合同分别抽取，网点描述足以定位时不得因没有门牌号否定整次取现。

【禁止推断】
不得从取现推断现金已经交付，不得从购买黄金推断黄金已经交给对方，不得从物流咨询或收到地址推断已经寄出，不得把线上转账生成线下交付实体，也不得用案发地点填充取现或交付地点。
```

- [x] **Step 7: Run focused tests to verify GREEN**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_domain_contracts.py backend\tests\test_template_extraction.py
```

Expected: all tests pass; no Schema snapshot, contract, retry, or extraction regression fails.

- [x] **Step 8: Verify the diff is prompt-only plus tests and plan**

Run:

```powershell
git diff --check
git diff --name-only
```

Expected changed implementation files: only the six domain `.txt` files. No changes under `backend/domain-contracts`, `backend/app`, `backend/template_rules.json`, or `frontend`.

- [x] **Step 9: Run one real fixture review**

Start the existing fixed-port services and submit `backend/test-fixtures/06-all-statuses-demo.docx`. Record task status, 34-result count, failed domains, schema retry count, and total/model timing. Do not repeat if the first healthy run completes.

- [ ] **Step 10: Commit the implementation**

```powershell
git add backend/tests/test_domain_contracts.py backend/prompt-templates/domains docs/superpowers/plans/2026-07-22-six-domain-prompt-templates.md
git commit -m "feat: strengthen six-domain extraction prompts"
```
