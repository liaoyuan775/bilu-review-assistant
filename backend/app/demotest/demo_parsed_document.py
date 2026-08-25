"""
ParsedDocument 解析结果演示脚本。

直接运行即可：
    python backend/app/demotest/demo_parsed_document.py

会依次解析 DOCX 和 PDF 两份文件，打印 ParsedDocument 的完整结构。
硬编码指向 test-fixtures/06-all-statuses-demo.docx/PDF。
"""

import asyncio
import json
import sys
from pathlib import Path

# ── 确保能找到 backend 包 ──────────────────────────────────────────
# 无论从项目根目录还是直接右键运行，都能正确 import
_HERE = Path(__file__).resolve().parent  # backend/app/demotest/
_BACKEND = _HERE.parent.parent  # backend/
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.parsing.parser import parse_document


# ── 固定路径 ──────────────────────────────────────────────────────
FIXTURES = Path(_BACKEND) / "test-fixtures"
DOCX_PATH = FIXTURES / "06-all-statuses-demo.docx"
PDF_PATH = FIXTURES / "06-all-statuses-demo.pdf"

def _compact(obj):
    """把 Pydantic 模型递归转成纯 Python 对象，便于 json.dumps 输出。"""
    if hasattr(obj, "model_dump"):
        return _compact(obj.model_dump())
    if isinstance(obj, dict):
        return {k: _compact(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_compact(v) for v in obj]
    return obj


def _print_anchor_map(doc, label: str):
    """打印锚点别名 ↔ SHA256 paragraph_id ↔ 文本片段 映射表。"""
    from app.review.domain_contract_rendering import evidence_anchor_aliases

    aliases = evidence_anchor_aliases(doc)
    print(f"\n{'='*70}")
    print(f" [ANCHOR MAP] {label} — 锚点映射表（内存计算，非 DB）")
    print(f"{'='*70}")
    print(f"  格式: 短别名 <-> SHA256[:24] -> 文本前 80 字")
    print(f"  计算公式: paragraph.id = SHA256(文档指纹:页码:段序:来源:文本)[:24]")
    print(f"  短别名按 EvidenceBlock/Paragraph 顺序编号: A001, A002 ...")
    print()

    if doc.evidenceBlocks:
        blocks = doc.evidenceBlocks
    else:
        # 无证据块时，用所有段落
        class _FakeBlock:
            pass
        blocks = []
        for page in doc.pages:
            for p in page.paragraphs:
                fb = _FakeBlock()
                fb.id = p.id
                fb.text = p.text
                fb.page = page.page
                blocks.append(fb)

    for block in blocks:
        alias = aliases.get(block.id, "???")
        short_text = block.text[:80].replace("\n", " ")
        print(f"  {alias} <-> {block.id} -> {short_text}")
    print()


def _print_model_input(doc, label: str):
    """打印喂给模型时的格式化文本（与 render_domain_prompt 一致）。"""
    from app.review.domain_contract_rendering import evidence_anchor_aliases

    aliases = evidence_anchor_aliases(doc)
    print(f"\n{'='*70}")
    print(f" [MODEL INPUT] {label} — 喂给模型的格式化文本")
    print(f"{'='*70}")

    # ── {{STRUCTURAL_TEXT}} 对应的格式化文本 ──
    print(f"\n  --- STRUCTURAL_TEXT ({len(doc.evidenceBlocks)} 块) ---")
    qa_ids = {b.id for b in doc.questionAnswers} if doc.evidenceBlocks else set()

    if doc.evidenceBlocks:
        # 结构化正文段落（非 QA 的证据块）
        lines = []
        for block in doc.evidenceBlocks:
            alias = aliases.get(block.id, "???")
            if block.kind == "qa" and block.id in qa_ids:
                continue  # Q&A 块进 EXCHANGES
            lines.append(f"[锚点:{alias}][第{block.page or 1}页] {block.text}")
        print("\n".join(lines) if lines else "(无结构化段落)")
    else:
        # 无 evidenceBlocks 时：段落 - 问答锚点
        qa_anchor_ids = {
            a for qa in doc.questionAnswers for a in qa.anchorIds
        }
        lines = []
        for page in doc.pages:
            for p in page.paragraphs:
                if p.id not in qa_anchor_ids:
                    alias = aliases.get(p.id, "???")
                    lines.append(f"[锚点:{alias}][第{page.page}页] {p.text}")
        print("\n".join(lines) if lines else "(无结构化段落)")

    # ── {{QUESTION_ANSWERS}} 对应的格式化文本 ──
    print(f"\n  --- QUESTION_ANSWERS ({len(doc.questionAnswers)} 问答对) ---")
    if doc.evidenceBlocks:
        qa_by_id = {b.id: b for b in doc.questionAnswers}
        lines = []
        idx = 0
        for block in doc.evidenceBlocks:
            if block.kind != "qa":
                continue
            qa = qa_by_id.get(block.id)
            if qa is None or qa.answerClarity == "blank":
                continue
            alias = aliases.get(block.id, "???")
            idx += 1
            lines.append(f"[问答{idx}][锚点:{alias}] {block.text}")
        print("\n".join(lines) if lines else "(无问答)")
    else:
        qa_anchor_ids = {
            a for qa in doc.questionAnswers for a in qa.anchorIds
        }
        lines = []
        for idx, qa in enumerate(doc.questionAnswers, 1):
            if qa.answerClarity == "blank":
                continue
            aliases_str = ",".join(aliases.get(a, "???") for a in qa.anchorIds)
            lines.append(f"[问答{idx}][锚点:{aliases_str}] 问：{qa.question} 答：{qa.answer}")
        print("\n".join(lines) if lines else "(无问答)")

    print()


def _print_full(doc, label: str):
    """完整打印 ParsedDocument 的所有层级，无截断。"""
    print(f"\n{'='*70}")
    print(f" [FILE] {label}")
    print(f"{'='*70}")
    print(f"  文件名       : {doc.name}")
    print(f"  格式         : {doc.format}")
    print(f"  逻辑页数     : {doc.pageCount}")
    print(f"  总段落数     : {sum(len(p.paragraphs) for p in doc.pages)}")
    print(f"  总字符数     : {len(doc.text)}")
    print(f"  问答对数     : {len(doc.questionAnswers)}")
    print(f"  证据块数     : {len(doc.evidenceBlocks)}")
    print(f"  警告数       : {len(doc.warnings)}")
    print()

    # ── 全部问答对 ──
    print(f"  【全部 {len(doc.questionAnswers)} 个问答对】")
    for idx, qa in enumerate(doc.questionAnswers, 1):
        anchors = ",".join(qa.anchorIds) if qa.anchorIds else "(无)"
        print(f"  [{idx}] clarity={qa.answerClarity} 锚点={anchors}")
        print(f"    问: {qa.question}")
        print(f"    答: {qa.answer}")
        if qa.guidance:
            print(f"    移除的模板说明: {qa.guidance}")
    print()

    # ── 全部证据块 ──
    print(f"  【全部 {len(doc.evidenceBlocks)} 个证据块】")
    for idx, eb in enumerate(doc.evidenceBlocks, 1):
        print(f"  [{idx}] kind={eb.kind}  page={eb.page}")
        print(f"    text: {eb.text}")
    print()

    # ── 每页完整段落 ──
    print(f"  【全部页面段落】")
    for page in doc.pages:
        print(f"\n  --- 第{page.page}页 ({len(page.paragraphs)} 段) ---")
        for p in page.paragraphs:
            print(f"    [{p.id}] {p.text}")
    print()

    # ── 警告 ──
    if doc.warnings:
        print(f"  【{len(doc.warnings)} 个警告】")
        for w in doc.warnings:
            print(f"    {w}")
        print()


async def main():
    print("=" * 70)
    print("  ParsedDocument 解析结果演示")
    print("=" * 70)

    # ── 1. 解析 DOCX ──
    print("\n>> 正在解析 DOCX ...")
    content_docx = DOCX_PATH.read_bytes()
    doc_docx = await parse_document(DOCX_PATH.name, content_docx)
    _print_full(doc_docx, "DOCX — 06-all-statuses-demo.docx")
    _print_anchor_map(doc_docx, "DOCX")
    _print_model_input(doc_docx, "DOCX")

    # ── 2. 解析 PDF ──
    print("\n>> 正在解析 PDF ...")
    content_pdf = PDF_PATH.read_bytes()
    doc_pdf = await parse_document(PDF_PATH.name, content_pdf)
    _print_full(doc_pdf, "PDF — 06-all-statuses-demo.pdf")
    _print_anchor_map(doc_pdf, "PDF")
    _print_model_input(doc_pdf, "PDF")

    # ── 3. DOCX vs PDF 差异对比 ──
    print("=" * 70)
    print("  DOCX vs PDF 差异对比")
    print("=" * 70)
    print(f"  页数      : DOCX={doc_docx.pageCount}  vs  PDF={doc_pdf.pageCount}")
    print(f"  段落数    : DOCX={sum(len(p.paragraphs) for p in doc_docx.pages)}  vs  PDF={sum(len(p.paragraphs) for p in doc_pdf.pages)}")
    print(f"  问答对数  : DOCX={len(doc_docx.questionAnswers)}  vs  PDF={len(doc_pdf.questionAnswers)}")
    print(f"  证据块数  : DOCX={len(doc_docx.evidenceBlocks)}  vs  PDF={len(doc_pdf.evidenceBlocks)}")
    print(f"  总字符数  : DOCX={len(doc_docx.text)}  vs  PDF={len(doc_pdf.text)}")
    print()

    # ── 4. 导出完整 JSON ──
    print(">> 导出完整 JSON 到 output/demo_parsed_document.json ...")
    output_dir = _BACKEND / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    export = {
        "docx": _compact(doc_docx),
        "pdf": _compact(doc_pdf),
    }
    (output_dir / "demo_parsed_document.json").write_text(
        json.dumps(export, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("  [OK] 已导出到:", output_dir / "demo_parsed_document.json")
    print("\n[DONE] 演示完成。")


if __name__ == "__main__":
    asyncio.run(main())
