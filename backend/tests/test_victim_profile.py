import asyncio
from pathlib import Path

import pytest

from app.core.models import (
    DocumentPage,
    DocumentParagraph,
    ParsedDocument,
    QuestionAnswerBlock,
    SourceType,
)
from app.review.victim import extract_victim_profile


def _document(
    *body: str,
    question_answers: list[tuple[str, str]] | None = None,
    header: str | None = None,
    footer: str | None = None,
) -> ParsedDocument:
    paragraphs = []
    if header:
        paragraphs.append(DocumentParagraph(text=header, sourceType=SourceType.HEADER))
    paragraphs.extend(DocumentParagraph(text=text) for text in body)
    if footer:
        paragraphs.append(DocumentParagraph(text=footer, sourceType=SourceType.FOOTER))
    return ParsedDocument(
        pages=[DocumentPage(page=1, paragraphs=paragraphs)],
        text="\n".join(paragraph.text for paragraph in paragraphs),
        questionAnswers=[
            QuestionAnswerBlock(question=question, answer=answer)
            for question, answer in (question_answers or [])
        ],
    )


def test_extracts_explicit_victim_profile_fields():
    document = _document(
        "问：请说明个人情况。",
        "答：我叫陈某，女，38岁，汉族，身份证号码4301**********1234。",
        question_answers=[(
            "请说明个人情况。",
            "我叫陈某，女，38岁，汉族，身份证号码4301**********1234，"
            "工作单位某商贸公司，住址某市某区某街道，联系电话138****5678。",
        )],
    )

    profile = extract_victim_profile(document)

    assert profile is not None
    assert profile.model_dump() == {
        "name": "陈某",
        "gender": "女",
        "age": 38,
        "birthDate": None,
        "ethnicity": "汉族",
        "idNumber": "4301**********1234",
        "occupation": None,
        "education": None,
        "employer": "某商贸公司",
        "address": "某市某区某街道",
        "registeredAddress": None,
        "contact": "138****5678",
        "isNpcRepresentative": None,
    }


def test_keeps_partial_profile_without_inferring_missing_fields():
    profile = extract_victim_profile(_document("被询问人 李某", "问：事情经过？"))

    assert profile is not None
    assert profile.name == "李某"
    assert profile.gender is None
    assert profile.age is None
    assert profile.ethnicity is None
    assert profile.idNumber is None
    assert profile.employer is None
    assert profile.address is None
    assert profile.contact is None


def test_returns_none_when_identity_is_not_stated():
    document = _document(
        "问：事情经过？",
        "答：我在家中收到一条短信。",
        question_answers=[("事情经过？", "我叫案件联系人李某。")],
    )

    assert extract_victim_profile(document) is None


def test_extracts_explicit_fields_from_docx_table_text():
    text = (
        "姓名 | 赵测试 | 性别 | 女\n"
        "年龄 | 68岁 | 民族 | 汉族\n"
        "身份证号码 | 110101195804120048\n"
        "联系电话 | 13600000006 | 工作单位 | 测试市示范小学退休教师（虚构）\n"
        "现住址 | 测试省测试市演示区银龄街40号401室（虚构）"
    )

    profile = extract_victim_profile(_document(text, "问：事情经过？"))

    assert profile is not None
    assert profile.model_dump() == {
        "name": "赵测试",
        "gender": "女",
        "age": 68,
        "birthDate": None,
        "ethnicity": "汉族",
        "idNumber": "110101195804120048",
        "occupation": None,
        "education": None,
        "employer": "测试市示范小学退休教师（虚构）",
        "address": "测试省测试市演示区银龄街40号401室（虚构）",
        "registeredAddress": None,
        "contact": "13600000006",
        "isNpcRepresentative": None,
    }


def test_does_not_infer_age_or_employer_from_birth_date_and_occupation():
    profile = extract_victim_profile(_document(
        "姓名 | 李样例 | 出生日期 | 1988年6月18日 | 职业 | 财务人员",
        "问：事情经过？",
    ))

    assert profile is not None
    assert profile.name == "李样例"
    assert profile.age is None
    assert profile.birthDate == "1988年6月18日"
    assert profile.occupation == "财务人员"
    assert profile.employer is None


def test_uses_victim_header_and_only_basic_information_qa_to_fill_missing_fields():
    document = _document(
        "询问人 测试民警 工作单位 新城区公安分局（测试）",
        "被询问人 测试甲 | 性别 女 | 年龄 34岁 | 出生日期 1992年3月15日",
        "身份证号码 110000199203150028 | 是否人大代表 否",
        "联系方式 15500000018 | 民族 汉族 | 文化程度 本科",
        "工作单位 某测试科技有限公司",
        "现住址 测试省测试市新城区测试路18号",
        "户籍所在地 测试省测试市安宁区测试乡测试村18号",
        "问：讲一下你的基本情况？",
        header="工作单位 页眉机关单位",
        footer="记录人 工作单位 页脚机关单位",
        question_answers=[
            ("讲一下你的基本情况？", "我的职业是软件工程师。"),
            ("事情经过？", "对方自称在错误公司工作。"),
        ],
    )

    profile = extract_victim_profile(document)

    assert profile is not None
    assert profile.name == "测试甲"
    assert profile.birthDate == "1992年3月15日"
    assert profile.occupation == "软件工程师"
    assert profile.education == "本科"
    assert profile.employer == "某测试科技有限公司"
    assert profile.registeredAddress == "测试省测试市安宁区测试乡测试村18号"
    assert profile.isNpcRepresentative is False


def test_unrelated_question_answer_cannot_fill_profile_fields():
    document = _document(
        "被询问人 李某",
        "问：事情经过？",
        question_answers=[(
            "事情经过？",
            "我联系了某案件科技有限公司，职业是客服，户籍所在地某案件地址。",
        )],
    )

    profile = extract_victim_profile(document)

    assert profile is not None
    assert profile.name == "李某"
    assert profile.occupation is None
    assert profile.employer is None
    assert profile.registeredAddress is None


REAL_RECORD = Path(__file__).resolve().parents[1] / "基于原模板填写-冒充客服退款诈骗询问笔录.docx"


@pytest.mark.skipif(not REAL_RECORD.exists(), reason="approved local DOCX fixture is unavailable")
def test_approved_electronic_record_has_complete_profile_and_33_question_answers():
    from app.parsing.parser import parse_document

    parsed = asyncio.run(parse_document(REAL_RECORD.name, REAL_RECORD.read_bytes()))
    profile = extract_victim_profile(parsed)

    assert len(parsed.questionAnswers) == 33
    assert profile is not None
    assert profile.model_dump() == {
        "name": "测试甲",
        "gender": "女",
        "age": 34,
        "birthDate": "1992年3月15日",
        "ethnicity": "汉族",
        "idNumber": "110000199203150028",
        "occupation": "行政人员",
        "education": "本科",
        "employer": "某测试科技有限公司",
        "address": "测试省测试市新城区平安街道清风社区测试路18号",
        "registeredAddress": "测试省测试市安宁区测试乡测试村18号",
        "contact": "15500000018",
        "isNpcRepresentative": False,
    }
    assert parsed.warnings == []
