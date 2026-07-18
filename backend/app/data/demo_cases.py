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
DEMO_DOCUMENT_ROOT = REPOSITORY_ROOT / "output" / "doc"


@dataclass(frozen=True)
class DemoCase:
    """一个演示样例的定义。

    Attributes:
        id:             唯一标识（如 "case-01-basic-complete"）
        filename:       DOCX 文件名
        intent:         用例意图描述
        executionMode:  "mock"=模拟结果 / "qwen"=完整模型审查
    """
    id: str
    filename: str
    intent: str
    executionMode: Literal["mock", "qwen"]

    @property
    def path(self) -> Path:
        """返回样例文件的完整磁盘路径。"""
        return DEMO_DOCUMENT_ROOT / self.filename


DEMO_CASES = [
    DemoCase("case-01-basic-complete", "01-基本完整-电诈询问笔录.docx", "基本完整 · 快速演示", "mock"),
    DemoCase("case-02-explicit-omissions", "02-明确漏问-电诈询问笔录.docx", "明确漏问", "qwen"),
    DemoCase("case-03-app-rebate", "03-复杂场景-APP返利询问笔录.docx", "APP 返利复杂场景", "qwen"),
    DemoCase("case-04-fake-prosecutor-atm", "04-冒充公检法-老年人ATM询问笔录.docx", "冒充公检法 · ATM", "qwen"),
    DemoCase("case-05-investment-crypto", "05-投资交友-数字货币询问笔录.docx", "投资交友 · 数字货币", "qwen"),
    DemoCase("case-06-fake-service-remote-control", "06-冒充客服-远程控制询问笔录.docx", "冒充客服 · 远程控制", "qwen"),
    DemoCase("case-07-cash-gold-delivery", "07-线下取现-寄递黄金询问笔录.docx", "线下取现 · 寄递黄金", "qwen"),
]


def get_demo_case(case_id: str) -> DemoCase | None:
    """根据 ID 查找演示样例。"""
    return next((case for case in DEMO_CASES if case.id == case_id), None)


async def load_demo_document(case: DemoCase) -> ParsedDocument:
    """加载演示样例的 DOCX 文件并解析为 ParsedDocument。"""
    return await parse_document(case.filename, case.path.read_bytes())
