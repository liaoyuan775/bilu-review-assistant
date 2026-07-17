from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.models import ParsedDocument
from app.services.parser import parse_document


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEMO_DOCUMENT_ROOT = REPOSITORY_ROOT / "output" / "doc"


@dataclass(frozen=True)
class DemoCase:
    id: str
    filename: str
    intent: str
    executionMode: Literal["mock", "qwen"]

    @property
    def path(self) -> Path:
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
    return next((case for case in DEMO_CASES if case.id == case_id), None)


async def load_demo_document(case: DemoCase) -> ParsedDocument:
    return await parse_document(case.filename, case.path.read_bytes())
