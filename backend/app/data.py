import json
from pathlib import Path

from app.models import DocumentPage, DocumentParagraph, ParsedDocument, SourceType


ROOT = Path(__file__).resolve().parent.parent
RULES: list[dict] = json.loads((ROOT / "rules.json").read_text(encoding="utf-8"))


def _demo(doc_id: str, name: str, pages: list[list[str]]) -> ParsedDocument:
    normalized = [
        DocumentPage(
            page=index + 1,
            paragraphs=[
                DocumentParagraph(text=paragraph, sourceType=SourceType.NATIVE_TEXT)
                for paragraph in paragraphs
            ],
        )
        for index, paragraphs in enumerate(pages)
    ]
    return ParsedDocument(
        id=doc_id,
        name=name,
        format="SAMPLE",
        pageCount=len(normalized),
        pages=normalized,
        text="\n".join(paragraph for page in pages for paragraph in page),
        sizeLabel="脱敏样例",
    )


DEMOS = [
    _demo("sample-covered", "样例一：基本合格笔录", [[
        "询问时间：2026年7月15日09时20分。询问地点：某公安机关询问室。",
        "问：请说明个人情况。答：我叫周某，男，1992年出生，身份证号码和手机号码已脱敏。",
        "问：已送达权利义务告知书，是否申请回避？答：不申请。",
        "问：请讲述事情经过。答：7月14日晚我在家收到微信消息，对方让我下载APP并转账。",
        "问：聊天记录？答：微信账号为wx_demo，聊天记录已保存。",
        "问：转账情况？答：21时转账4600元至银行卡尾号1234，流水号A001，总损失4600元。",
        "问：APP情况？答：名为云商助手，从对方链接下载，手机号登录，目前还能打开并保留安装包。",
    ]]),
    _demo("sample-missing", "样例二：存在明确漏问", [[
        "询问时间：2026年7月15日14时。",
        "问：你叫什么名字？答：我叫李某。",
        "问：发生了什么事情？答：有人让我把钱转到安全账户，我转了两次，一共两万多元。",
    ]]),
    _demo("sample-telecom", "样例三：电诈条件规则", [[
        "询问时间：2026年7月15日16时10分。询问地点：某派出所询问室。",
        "问：个人情况？答：我叫陈某，女，1988年出生，手机号码和身份证号码已脱敏。",
        "问：已送达权利义务告知书，是否申请回避？答：不申请。",
        "问：事情经过？答：我在家刷短视频看到兼职广告，添加对方QQ并下载优选商城APP。",
        "问：聊天记录？答：记录还在，但没有对方QQ号。",
        "问：是否转账？答：支付宝扫码三次，分别为1000元、3000元、5000元。",
        "问：是否返利？答：第一次收到200元返利。",
    ]]),
]

DEMO_INTENTS = ["基本合格", "明确漏问", "电诈条件规则"]
