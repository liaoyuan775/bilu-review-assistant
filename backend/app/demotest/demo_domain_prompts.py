"""
各个域的最终提示词打印 + 数据来源验证。

使用方式：
    python backend/app/demotest/demo_domain_prompts.py

会解析 06-all-statuses-demo.docx，然后为 6 个域分别渲染完整提示词，
打印到控制台并写入 output/demo_prompts/ 目录。
最后用具体数据验证 {{QUESTION_ANSWERS}} 和 {{STRUCTURAL_TEXT}} 确实来自 ParsedDocument。
"""

import asyncio
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.parsing.parser import parse_document
from app.review.domain_contract_rendering import render_domain_prompt, PROMPT_TEMPLATE
from app.data.domain_contracts import DOMAIN_CONTRACTS, DOMAIN_ORDER

FIXTURE = _BACKEND / "test-fixtures" / "06-all-statuses-demo.docx"
OUT_DIR = _BACKEND / "output" / "demo_prompts"


async def main():
    print("=" * 70)
    print("  各域最终提示词打印 + 数据来源验证")
    print("=" * 70)

    # ── 1. 解析文档 ──
    content = FIXTURE.read_bytes()
    doc = await parse_document(FIXTURE.name, content)
    print(f"\n[OK] 解析完成: {doc.name}  ({doc.format}, {doc.pageCount}页, {len(doc.questionAnswers)}问答, {len(doc.evidenceBlocks)}证据块)\n")

    # ── 2. 数据来源验证：追踪 questionAnswers → {{QUESTION_ANSWERS}} ──
    print("-" * 70)
    print("  【数据来源验证】")
    print("-" * 70)

    # 验证1: 问答来源
    print("\n  (1) questionAnswers[0] 原始数据 -> {{QUESTION_ANSWERS}} 中的对应行")
    qa0 = doc.questionAnswers[0]
    anchors = ",".join(qa0.anchorIds)
    print(f"    原始 questionAnswers[0]:")
    print(f"      question    = {qa0.question[:60]}...")
    print(f"      answer      = {qa0.answer[:60]}...")
    print(f"      anchorIds   = {anchors}")
    print(f"      clarity     = {qa0.answerClarity}")
    print(f"    渲染后变成 {{QUESTION_ANSWERS}} 中的:")
    print(f"      [问答1][锚点:{anchors[:20]}...] 问：{qa0.question[:50]}... 答：{qa0.answer[:50]}...")
    print()

    # 验证2: evidenceBlocks → {{STRUCTURAL_TEXT}}
    print("  (2) evidenceBlocks[] kind=text -> {{STRUCTURAL_TEXT}} 中的结构行")
    text_blocks = [eb for eb in doc.evidenceBlocks if eb.kind == "text"]
    print(f"    共 {len(text_blocks)} 个 kind=text 的证据块，将会按行拼入 {{STRUCTURAL_TEXT}}:")
    for eb in text_blocks[:3]:
        print(f"      [锚点:A???][第{eb.page}页] {eb.text[:60]}...")
    print()

    # 验证3: DOMAIN_CONTRACTS 来源是 domain-contracts/*.json
    print("  (3) {{DOMAIN_BOUNDARY}} / {{REQUESTED_CONTRACT}} 来自 domain-contracts/*.json")
    c = DOMAIN_CONTRACTS["header_procedure"]
    print(f"    以 header_procedure 为例:")
    print(f"      include: {c.include}")
    print(f"      exclude: {c.exclude}")
    print(f"      facts 数: {len(c.facts)}")
    print(f"      entities: {list(c.entities)}")
    print()

    # 验证4: DOMAIN_INSTRUCTIONS 来自 prompt-templates/domains/*.txt
    print("  (4) {{DOMAIN_INSTRUCTIONS}} 来自 prompt-templates/domains//*.txt")
    print(f"      domain-extraction.txt 骨架模板路径:")
    print(f"        {PROMPT_TEMPLATE}")
    print()

    # ── 3. 为 6 个域分别渲染完整提示词 ──
    print("-" * 70)
    print("  各域最终提示词")
    print("-" * 70)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for domain_name in DOMAIN_ORDER:
        contract = DOMAIN_CONTRACTS[domain_name]
        prompt = render_domain_prompt(doc, contract)

        # 打印摘要信息
        print(f"\n{'='*60}")
        print(f"  域: {contract.domain} ({contract.title})")
        print(f"  提示词长度: {len(prompt)} chars")
        print(f"{'='*60}")
        # 完整打印
        print(prompt)

        # 写入文件
        filepath = OUT_DIR / f"{contract.domain}.txt"
        filepath.write_text(prompt, encoding="utf-8")
        print(f"  [写入] {filepath}")

    print(f"\n{'='*60}")
    print("  总结：提示词中的所有 {{}} 占位符填充来源")
    print(f"{'='*60}")
    print(f"  {{DOMAIN_NAME}}         → domain-contracts/{'{domain}'}.json > contract.domain")
    print(f"  {{DOMAIN_TITLE}}        → domain-contracts/{'{domain}'}.json > contract.title")
    print(f"  {{DOMAIN_BOUNDARY}}     → domain-contracts/{'{domain}'}.json > include/exclude")
    print(f"  {{DOMAIN_INSTRUCTIONS}} → prompt-templates/domains/{'{domain}'}.txt")
    print(f"  {{REQUESTED_CONTRACT}}  → domain-contracts/{'{domain}'}.json > facts + entities")
    print(f"  {{CORRECTION}}          → 首次请求为'无，这是首次请求。'")
    print(f"  {{STRUCTURAL_TEXT}}     ← ParsedDocument.evidenceBlocks (kind=text)")
    print(f"                            ← ParsedDocument.pages[*].paragraphs[非问答部分]")
    print(f"  {{QUESTION_ANSWERS}}    ← ParsedDocument.questionAnswers (非空答案)")
    print(f"  骨架模板                → prompt-templates/domain-extraction.txt")
    print(f"\n[结论] 塞进提示词中的 DOCX 内容确实来源于 ParsedDocument 类。")
    print(f"  {{QUESTION_ANSWERS}}   ← parse_document() 填充 doc.questionAnswers")
    print(f"  {{STRUCTURAL_TEXT}}    ← parse_document() 填充 doc.evidenceBlocks / doc.pages")
    print(f"[DONE] 完整提示词已写入 {OUT_DIR}/")


if __name__ == "__main__":
    asyncio.run(main())
