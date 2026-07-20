"""
演示样例定义 — 服务端内置的脱敏询问笔录案例。

每个 DemoCase 包含一个本地 DOCX 文件路径和执行模式：
- "mock"：不调用模型，使用预置模拟结果，适合快速演示
- "qwen"：执行完整 Qwen 模型审查流程

路径说明：
  当前文件位于 backend/app/data/demo_cases.py
  __file__.parent.parent.parent = backend/（项目根）
  样例文件位于 backend/output/doc/ 目录
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.core.models import ParsedDocument
from app.parsing.parser import parse_document


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEMO_DOCUMENT_ROOT = REPOSITORY_ROOT / "test-fixtures"


@dataclass(frozen=True)
class DemoCase:
    """一个演示样例的定义。

    Attributes:
        id:             唯一标识（如 "case-01-baseline"）
        filename:       DOCX 文件名
        intent:         用例意图描述
        executionMode:  "mock"=模拟结果 / "qwen"=完整模型审查
    """
    id: str
    filename: str
    display_name: str
    intent: str
    executionMode: Literal["mock", "qwen"]

    @property
    def path(self) -> Path:
        """返回样例文件的完整磁盘路径。"""
        return DEMO_DOCUMENT_ROOT / self.filename


DEMO_CASES = [
    DemoCase("case-01-baseline", "01-baseline.docx", "01 基线样例｜基础完整笔录", "基线样例（快速模拟结果）", "mock"),
    DemoCase("case-02-line-breaks", "02-line-breaks.docx", "02 跨段问答样例", "跨段问答重建｜完整审查", "qwen"),
    DemoCase("case-03-blank-answer", "03-blank-answer.docx", "03 空答样例", "空答识别｜完整审查", "qwen"),
    DemoCase("case-04-long-answer", "04-long-answer.docx", "04 长文本样例", "长文本分页｜完整审查", "qwen"),
    DemoCase("case-05-table-and-symbols", "05-table-and-symbols.docx", "05 表格与符号样例", "表格和特殊字符｜完整审查", "qwen"),
    DemoCase("case-06-all-statuses-demo", "06-all-statuses-demo.docx", "06 五类结果演示笔录", "覆盖、遗漏、不清、矛盾、人工判断｜完整审查", "qwen"),
]


def get_demo_case(case_id: str) -> DemoCase | None:
    """根据 ID 查找演示样例。"""
    return next((case for case in DEMO_CASES if case.id == case_id), None)


async def load_demo_document(case: DemoCase) -> ParsedDocument:
    """加载演示样例的 DOCX 文件并解析为 ParsedDocument。"""
    return await parse_document(case.filename, case.path.read_bytes())
