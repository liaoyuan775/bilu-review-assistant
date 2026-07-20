from app.core.models import DocumentPage, DocumentParagraph, EvidenceBlock, ParsedDocument, SourceType
from app.parsing.question_answer import reconstruct_evidence_blocks, reconstruct_question_answers


def _paragraph(block_id: str, text: str) -> DocumentParagraph:
    return DocumentParagraph(id=block_id, text=text, sourceType=SourceType.NATIVE_TEXT)


def test_evidence_block_model_defaults_and_serializes():
    block = EvidenceBlock(
        id="qa-1",
        kind="qa",
        text="问：问题\n答：答案",
        paragraphIds=["p1", "p2"],
        page=1,
        paragraph=2,
    )

    assert block.kind == "qa"
    assert block.paragraphIds == ["p1", "p2"]
    assert ParsedDocument().evidenceBlocks == []


def test_reconstructs_multiple_question_answers_from_one_paragraph():
    pages = [DocumentPage(
        page=1,
        paragraphs=[_paragraph("b1", "问：是否收到风险提示？答：收到。问:是否挂失？答:已经挂失。")],
    )]

    blocks = reconstruct_question_answers(pages)

    assert [(block.question, block.answer) for block in blocks] == [
        ("是否收到风险提示？", "收到。"),
        ("是否挂失？", "已经挂失。"),
    ]
    assert [block.anchorIds for block in blocks] == [["b1"], ["b1"]]
    assert all(block.answerClarity == "clear" for block in blocks)


def test_carries_an_answer_across_paragraphs_until_the_next_question():
    pages = [DocumentPage(
        page=1,
        paragraphs=[
            _paragraph("q1", "问：请描述转账经过？"),
            _paragraph("a1", "答：第一笔通过测试银行转出。"),
            _paragraph("a2", "第二笔通过测试支付平台转出。"),
            _paragraph("q2", "问：是否留存记录？"),
            _paragraph("a3", "答：有。"),
        ],
    )]

    blocks = reconstruct_question_answers(pages)

    assert blocks[0].answer == "第一笔通过测试银行转出。 第二笔通过测试支付平台转出。"
    assert blocks[0].anchorIds == ["q1", "a1", "a2"]
    assert blocks[1].answer == "有。"


def test_carries_an_open_answer_across_pages():
    pages = [
        DocumentPage(
            page=1,
            paragraphs=[
                _paragraph("q1", "问：请描述联系渠道？"),
                _paragraph("a1", "答：先通过测试短视频平台联系，"),
            ],
        ),
        DocumentPage(
            page=2,
            paragraphs=[
                _paragraph("a2", "随后切换到测试聊天软件。"),
                _paragraph("q2", "问：是否还有其他渠道？"),
                _paragraph("a3", "答：没有。"),
            ],
        ),
    ]

    blocks = reconstruct_question_answers(pages)

    assert blocks[0].answer == "先通过测试短视频平台联系， 随后切换到测试聊天软件。"
    assert blocks[0].anchorIds == ["q1", "a1", "a2"]


def test_marks_an_explicitly_blank_answer_as_blank():
    pages = [DocumentPage(
        page=1,
        paragraphs=[
            _paragraph("q1", "问：是否接受过反诈宣传？"),
            _paragraph("a1", "答："),
            _paragraph("q2", "问：是否下载反诈应用？"),
        ],
    )]

    blocks = reconstruct_question_answers(pages)

    assert [(block.answer, block.answerClarity) for block in blocks] == [
        ("", "blank"),
        ("", "blank"),
    ]
    assert blocks[0].anchorIds == ["q1", "a1"]


def test_moves_parenthetical_template_instructions_out_of_case_facts():
    pages = [DocumentPage(
        page=1,
        paragraphs=[
            _paragraph("q1", "问：讲一下基本情况？（需录入姓名、职业等信息）"),
            _paragraph("a1", "答：（此处由民警根据实际情况填写）"),
        ],
    )]

    block = reconstruct_question_answers(pages)[0]

    assert block.question == "讲一下基本情况？"
    assert block.answer == ""
    assert block.guidance == ["需录入姓名、职业等信息", "此处由民警根据实际情况填写"]
    assert block.answerClarity == "blank"


def test_marks_an_unknown_response_as_unclear_not_blank():
    pages = [DocumentPage(
        page=1,
        paragraphs=[
            _paragraph("q1", "问：具体转账时间是什么？"),
            _paragraph("a1", "答：我记不清了。"),
        ],
    )]

    block = reconstruct_question_answers(pages)[0]

    assert block.answer == "我记不清了。"
    assert block.answerClarity == "unclear"


def test_question_continuation_before_answer_is_preserved_in_one_block():
    pages = [DocumentPage(
        page=1,
        paragraphs=[
            _paragraph("q1", "问：请说明对方如何联系你，"),
            _paragraph("q2", "以及之后使用了哪些应用？"),
            _paragraph("a1", "答：先打电话，之后使用测试应用。"),
        ],
    )]

    qa = reconstruct_question_answers(pages)[0]
    evidence = reconstruct_evidence_blocks(pages)

    assert qa.question == "请说明对方如何联系你， 以及之后使用了哪些应用？"
    assert len(evidence) == 1
    assert evidence[0].kind == "qa"
    assert evidence[0].paragraphIds == ["q1", "q2", "a1"]
    assert "问：请说明对方如何联系你， 以及之后使用了哪些应用？" in evidence[0].text
    assert "答：先打电话，之后使用测试应用。" in evidence[0].text


def test_non_qa_text_stays_in_order_before_a_qa_block():
    pages = [DocumentPage(
        page=1,
        paragraphs=[
            _paragraph("p1", "询问地点：测试派出所"),
            _paragraph("q1", "问：是否清楚？"),
            _paragraph("a1", "答：清楚。"),
        ],
    )]

    evidence = reconstruct_evidence_blocks(pages)

    assert [block.kind for block in evidence] == ["text", "qa"]
    assert evidence[0].text == "询问地点：测试派出所"
    assert evidence[0].paragraphIds == ["p1"]


def test_one_qa_has_one_stable_evidence_block_id():
    pages = [DocumentPage(
        page=1,
        paragraphs=[
            _paragraph("q1", "问：问题？"),
            _paragraph("a1", "答：答案。"),
        ],
    )]

    first = reconstruct_evidence_blocks(pages)
    second = reconstruct_evidence_blocks(pages)

    assert len(first) == 1
    assert first[0].id == second[0].id
