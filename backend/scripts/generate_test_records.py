from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


@dataclass(frozen=True)
class InquiryRecord:
    filename: str
    case_number: str
    inquiry_number: str
    start_time: str
    end_time: str
    location: str
    interviewers: str
    recorder: str
    identity: dict[str, str]
    notice: str
    questions: list[tuple[str, str]]
    closing: str


RECORDS = [
    InquiryRecord(
        filename="01-基本完整-电诈询问笔录.docx",
        case_number="TEST-2026-0716-001",
        inquiry_number="第1次",
        start_time="2026年7月16日09时00分",
        end_time="2026年7月16日11时10分",
        location="测试市公安局反诈中心第一询问室（虚构）",
        interviewers="测试民警甲、测试民警乙（虚构，编号TEST-P001、TEST-P002）",
        recorder="测试记录员甲（虚构，编号TEST-R001）",
        identity={
            "姓名": "张测试",
            "性别": "男",
            "出生日期": "1990年2月3日",
            "身份证号码": "110101199002030017",
            "联系电话": "13800000001",
            "职业": "测试科技有限公司项目专员（虚构）",
            "户籍地址": "测试省测试市演示区验证路1号（虚构）",
            "现住址": "测试省测试市演示区样例街10号101室（虚构）",
        },
        notice="询问人已向被询问人出示工作证件，并依法告知其如实陈述、申请回避、核对笔录等权利义务。被询问人表示已经听清，不申请回避，自愿接受询问。",
        questions=[
            ("请说明你的姓名、性别、出生日期、身份证号码、联系电话、住址和工作单位。", "我叫张测试，男，1990年2月3日出生，身份证号码110101199002030017，手机号13800000001，现住测试省测试市演示区样例街10号101室，在测试科技有限公司担任项目专员。以上均为虚构测试信息。"),
            ("你是否已经听清权利义务告知，是否申请询问人员回避？", "我已经听清，不申请回避。"),
            ("请按时间顺序讲述事情经过。", "2026年7月15日19时32分，我在家中使用手机浏览短视频时看到兼职广告，随后添加对方微信。对方让我下载名为优选任务的APP并以刷单返利为由转账。我在20时18分至21时06分之间共转账三笔，之后对方要求继续缴纳解冻费，我意识到可能被骗并于21时25分报警。"),
            ("对方通过哪些平台联系你，双方账号分别是什么？", "最初在短视频平台联系，对方平台账号为video_test_001；后来使用微信联系，对方微信号wx_service_test_001，我的微信号wx_test_20260716_a；APP登录账号为app_user_test_001，绑定手机号13800000001。"),
            ("聊天记录和相关账号资料是否保存？", "全部聊天记录、账号主页截图和二维码截图都已保存在我的测试手机中，文件目录为case001_chat_test，未进行删除。"),
            ("APP名称、下载来源、链接、安装时间和当前状态是什么？", "APP名称为优选任务测试版，下载链接为https://download.example.test/app/case001，2026年7月15日19时55分安装，安装包文件名task-demo-001.apk，当前仍可打开，版本号1.0.1-test。"),
            ("请说明你用于转账的银行卡和支付账户。", "我使用的测试银行卡为工商银行测试卡6222020200001234567，开户名张测试；支付宝测试账号pay_test_001，绑定手机号13800000001。"),
            ("请逐笔说明第一笔转账的时间、金额、收款账户和流水号。", "第一笔于2026年7月15日20时18分转账1000元，收款测试卡号6222020200007654321，户名王演示，流水号：TEST202607150001。"),
            ("请逐笔说明第二笔转账的时间、金额、收款账户和流水号。", "第二笔于2026年7月15日20时42分转账3000元，收款测试卡号6222020200007654321，户名王演示，流水号：TEST202607150002。"),
            ("请逐笔说明第三笔转账的时间、金额、收款账户和流水号。", "第三笔于2026年7月15日21时06分转账5000元，支付宝收款测试账号merchant_test_001，交易单号：PAY-TEST-20260715-003。"),
            ("三笔转账合计损失多少，是否收到返利？", "三笔共计转出9000元。2026年7月15日20时25分收到200元测试返利，返利进入支付宝账号pay_test_001，因此实际损失8800元。返利流水号：REBATE-TEST-001。"),
            ("对方是否要求寄递银行卡、手机卡、现金或其他物品？", "没有，对方没有要求寄递任何物品。"),
            ("是否有朋友、同事或其他人员向你推荐该项目？", "没有，我是自行看到广告后联系对方的。"),
            ("你能否提供设备、网络和电子证据情况？", "使用的是测试手机TEST-PHONE-001，设备IMEI测试值860000000000001，案发时连接家庭测试网络，公网IP记录值198.51.100.11。聊天截图、银行流水和APK安装包均可提交。"),
            ("以上陈述是否真实，是否还有需要补充的情况？", "以上内容均为本次系统测试所使用的虚构事实，我已经完整陈述，没有其他需要补充的内容。"),
        ],
        closing="询问结束后，被询问人已逐页核对笔录，确认记录内容与其陈述一致，并同意签名确认。",
    ),
    InquiryRecord(
        filename="02-明确漏问-电诈询问笔录.docx",
        case_number="TEST-2026-0716-002",
        inquiry_number="第1次",
        start_time="2026年7月16日13时40分",
        end_time="2026年7月16日14时35分",
        location="测试市公安局演示派出所第二询问室（虚构）",
        interviewers="测试民警丙、测试民警丁（虚构，编号TEST-P003、TEST-P004）",
        recorder="测试记录员乙（虚构，编号TEST-R002）",
        identity={
            "姓名": "李样例",
            "性别": "女",
            "出生日期": "1988年6月18日",
            "身份证号码": "110101198806180022",
            "联系电话": "13900000002",
            "职业": "测试商贸有限公司财务人员（虚构）",
            "户籍地址": "测试省测试市演示区规范路2号（虚构）",
            "现住址": "测试省测试市演示区格式街20号202室（虚构）",
        },
        notice="本文件用于验证系统识别未询问事项。询问开始时仅核对了被询问人身份，笔录正文中未记录权利义务告知及回避申请情况。",
        questions=[
            ("请说明你的姓名、身份证号码、联系电话和住址。", "我叫李样例，身份证号码110101198806180022，手机号13900000002，现住测试省测试市演示区格式街20号202室。以上均为虚构测试信息。"),
            ("发生了什么事情？", "2026年7月15日中午，我收到一个QQ好友申请，对方说可以协助办理低息贷款。我按对方要求填写资料并转了两笔钱，后来发现无法联系对方。"),
            ("对方使用的QQ账号是什么？", "对方QQ测试账号为qq_test_20260716_b，昵称贷款顾问测试号，我的QQ测试账号为qq_user_test_002。"),
            ("你使用哪张银行卡转账，收款卡号是什么？", "我使用建设银行测试卡6222020200002234568，开户名李样例，向收款测试卡6222020200008765432转账，收款户名赵模拟。"),
            ("其中一笔转账的情况是什么？", "2026年7月15日12时36分转账5000元，流水号：TEST202607150101。另一笔只记得金额是8000元。"),
            ("总共损失多少？", "共转出13000元，没有收到任何返款。"),
            ("聊天记录是否还在？", "QQ聊天记录仍保存在测试手机TEST-PHONE-002内，我截取了部分页面，但没有导出完整聊天记录。"),
            ("是否还有其他情况？", "对方后来让我继续支付保证金，我没有再转账。除此之外没有补充。"),
        ],
        closing="本笔录有意保留未询问事项，仅用于测试明确遗漏和回答不完整状态，不代表真实办案笔录质量。",
    ),
    InquiryRecord(
        filename="03-复杂场景-APP返利询问笔录.docx",
        case_number="TEST-2026-0716-003",
        inquiry_number="第2次",
        start_time="2026年7月16日15时10分",
        end_time="2026年7月16日17时45分",
        location="测试市公安局反诈中心第三询问室（虚构）",
        interviewers="测试民警戊、测试民警己（虚构，编号TEST-P005、TEST-P006）",
        recorder="测试记录员丙（虚构，编号TEST-R003）",
        identity={
            "姓名": "周演示",
            "性别": "男",
            "出生日期": "1993年11月9日",
            "身份证号码": "110101199311090035",
            "联系电话": "13700000003",
            "职业": "测试物流有限公司调度员（虚构）",
            "户籍地址": "测试省测试市演示区流程路3号（虚构）",
            "现住址": "测试省测试市演示区节点街30号303室（虚构）",
        },
        notice="询问人已出示工作证件并告知权利义务。被询问人表示听清告知内容，不申请回避，同意就APP刷单返利、转账及相关人员情况接受询问。",
        questions=[
            ("请核对你的身份、电话、住址和职业。", "我叫周演示，男，1993年11月9日出生，身份证号码110101199311090035，手机号13700000003，现住测试省测试市演示区节点街30号303室，在测试物流有限公司担任调度员。以上均为虚构测试信息。"),
            ("是否听清权利义务告知，是否申请回避？", "已经听清，不申请回避。"),
            ("是谁向你介绍这个兼职项目的？", "测试同事孙案例通过企业微信推荐给我，他的企业微信测试账号为workwx_test_003，手机号13600000004。"),
            ("孙案例如何获得这个项目，对方真实身份是什么？", "我不知道。孙案例只说是在一个测试群里看到的，没有告诉我发布人的真实姓名。"),
            ("你后来与对方通过哪些账号联系？", "我使用微信测试账号wx_user_test_003联系对方微信wx_service_test_003，又加入QQ群TEST-GROUP-003，群主QQ账号qq_owner_test_003。"),
            ("使用的APP名称和登录账号是什么？", "APP名称为云商助手测试版，登录账号app_test_20260716_c，绑定手机号13700000003，邀请码INVITE-TEST-003。"),
            ("APP从哪里下载，链接和安装包是否保存？", "通过微信收到链接https://download.example.test/app/case003，安装包文件名cloud-shop-test-003.apk，SHA256测试值TESTSHA256CASE003000000000000000000000000000000000000000000000，安装包仍保存在测试手机中。"),
            ("APP当前是否可用，最后登录时间和网络地址是什么？", "APP当前还能打开，最后登录时间为2026年7月16日08时20分，测试服务地址api.example.test，登录日志中的保留IP为198.51.100.23。"),
            ("请说明你的付款银行卡和支付账号。", "我使用农业银行测试卡6222020200003234569，开户名周演示；支付宝测试账号pay_test_003；数字钱包测试账号wallet_test_003。"),
            ("第一笔付款的时间、金额、收款信息和流水号是什么？", "2026年7月14日18时12分支付2000元，收款测试卡6222020200009765433，户名钱测试，流水号：TEST202607140301。"),
            ("第二笔付款的时间、金额、收款信息和流水号是什么？", "2026年7月14日19时05分支付6000元，支付宝商户测试账号merchant_test_003，交易单号：PAY-TEST-20260714-302。"),
            ("第三笔付款的时间、金额、收款信息和流水号是什么？", "2026年7月15日09时26分通过数字钱包支付12000元，钱包收款测试账号wallet_receiver_test_003，流水号：WALLET-TEST-303。"),
            ("返利和提现情况如何？", "第一笔任务后返利300元，于2026年7月14日18时25分进入支付宝账号pay_test_003，返利流水号：REBATE-TEST-003。之后APP显示可提现26000元，但要求先交认证金，我没有实际提现成功。"),
            ("三笔付款及返利后的实际损失是多少？", "共支付20000元，收到返利300元，实际损失19700元。"),
            ("是否寄递过银行卡、电话卡、现金或设备？", "对方要求寄送一张电话卡，我通过测试快递寄出空白测试卡片，测试快递公司为示例速运，测试单号TEST-EXPRESS-003，寄件时间2026年7月15日14时10分，收件人为吴模拟，测试电话13500000005，地址为测试省测试市样例区收件路88号。"),
            ("你是否清楚收件人吴模拟与对方的关系？", "我不知道。我只在APP客服消息中看到这个收件姓名。"),
            ("现有电子证据包括哪些？", "包括微信和QQ群聊天记录、APP安装包、APP页面录屏、三笔支付凭证、返利记录、快递电子面单和测试手机TEST-PHONE-003。所有材料均存放在case003_evidence_test目录。"),
            ("是否还有其他相关人员或账号？", "孙案例后来也表示无法提现，他的测试手机号13600000004。除此之外没有发现其他人员。"),
            ("以上内容是否经过核对？", "我已经核对，除我明确无法确认的两项外，其余账号、卡号、时间、金额和流水号均按本次虚构测试材料完整陈述。"),
        ],
        closing="询问结束后，被询问人核对笔录并确认：文中账号、卡号、流水号、IP、链接及人员信息均为虚构测试值。",
    ),
]


def _set_cell_shading(cell, fill: str) -> None:
    cell_properties = cell._tc.get_or_add_tcPr()
    shading = cell_properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        cell_properties.append(shading)
    shading.set(qn("w:fill"), fill)


def _set_cell_margins(cell, top=100, start=120, bottom=100, end=120) -> None:
    cell_properties = cell._tc.get_or_add_tcPr()
    margins = cell_properties.first_child_found_in("w:tcMar")
    if margins is None:
        margins = OxmlElement("w:tcMar")
        cell_properties.append(margins)
    for margin_name, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = margins.find(qn(f"w:{margin_name}"))
        if node is None:
            node = OxmlElement(f"w:{margin_name}")
            margins.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def _set_run_font(run, name="宋体", size=Pt(11), bold=False, color=None) -> None:
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    run.font.size = size
    run.font.bold = bold
    if color is not None:
        run.font.color.rgb = RGBColor(*color)


def _add_page_number(paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("第 ")
    _set_run_font(run, size=Pt(9), color=(100, 110, 125))
    field_begin = OxmlElement("w:fldChar")
    field_begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = " PAGE "
    field_end = OxmlElement("w:fldChar")
    field_end.set(qn("w:fldCharType"), "end")
    run._r.extend([field_begin, instruction, field_end])
    tail = paragraph.add_run(" 页")
    _set_run_font(tail, size=Pt(9), color=(100, 110, 125))


def _configure_document(document: Document, record: InquiryRecord) -> None:
    section = document.sections[0]
    section.top_margin = Cm(1.9)
    section.bottom_margin = Cm(1.8)
    section.left_margin = Cm(2.2)
    section.right_margin = Cm(2.2)
    section.header_distance = Cm(0.8)
    section.footer_distance = Cm(0.8)

    normal = document.styles["Normal"]
    normal.font.name = "宋体"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    normal.font.size = Pt(11)
    normal.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    normal.paragraph_format.space_after = Pt(4)

    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = header.add_run(f"虚构测试材料  |  {record.case_number}  |  禁止用于真实案件")
    _set_run_font(run, size=Pt(8), bold=True, color=(190, 45, 38))
    _add_page_number(section.footer.paragraphs[0])


def _set_table_borders(table, color="9AA8B8", size="6") -> None:
    table_properties = table._tbl.tblPr
    borders = table_properties.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        table_properties.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = borders.find(qn(f"w:{edge}"))
        if tag is None:
            tag = OxmlElement(f"w:{edge}")
            borders.append(tag)
        tag.set(qn("w:val"), "single")
        tag.set(qn("w:sz"), size)
        tag.set(qn("w:color"), color)


def _write_cell(cell, text: str, *, label=False) -> None:
    cell.text = ""
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    _set_cell_margins(cell)
    if label:
        _set_cell_shading(cell, "EAF1F8")
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.space_after = Pt(0)
    run = paragraph.add_run(text)
    _set_run_font(run, size=Pt(9.5), bold=label, color=(50, 64, 82) if label else None)


def _add_metadata_table(document: Document, record: InquiryRecord) -> None:
    table = document.add_table(rows=4, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    widths = [Cm(2.2), Cm(5.2), Cm(2.2), Cm(6.3)]
    for row in table.rows:
        for index, cell in enumerate(row.cells):
            cell.width = widths[index]
    values = [
        ("案件编号", record.case_number, "询问次数", record.inquiry_number),
        ("开始时间", record.start_time, "结束时间", record.end_time),
        ("询问地点", record.location, "记录人", record.recorder),
        ("询问人", record.interviewers, "材料性质", "虚构测试材料"),
    ]
    for row, row_values in zip(table.rows, values):
        for index, value in enumerate(row_values):
            _write_cell(row.cells[index], value, label=index % 2 == 0)
    _set_table_borders(table)


def _add_identity_table(document: Document, identity: dict[str, str]) -> None:
    heading = document.add_paragraph()
    heading.paragraph_format.space_before = Pt(10)
    heading.paragraph_format.space_after = Pt(5)
    run = heading.add_run("被询问人基本情况")
    _set_run_font(run, size=Pt(12), bold=True, color=(28, 63, 104))

    items = list(identity.items())
    table = document.add_table(rows=4, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    widths = [Cm(2.2), Cm(5.2), Cm(2.2), Cm(6.3)]
    for row_index, row in enumerate(table.rows):
        for cell_index, cell in enumerate(row.cells):
            cell.width = widths[cell_index]
        left_label, left_value = items[row_index * 2]
        right_label, right_value = items[row_index * 2 + 1]
        for index, value in enumerate((left_label, left_value, right_label, right_value)):
            _write_cell(row.cells[index], value, label=index % 2 == 0)
    _set_table_borders(table)


def _add_notice(document: Document, notice: str) -> None:
    table = document.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    cell = table.cell(0, 0)
    _set_cell_shading(cell, "F3F7FB")
    _set_cell_margins(cell, top=150, start=170, bottom=150, end=170)
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.space_after = Pt(0)
    label = paragraph.add_run("权利义务告知：")
    _set_run_font(label, size=Pt(10), bold=True, color=(28, 63, 104))
    content = paragraph.add_run(notice)
    _set_run_font(content, size=Pt(10))
    _set_table_borders(table, color="AFC2D6", size="5")


def _add_questions(document: Document, questions: list[tuple[str, str]]) -> None:
    heading = document.add_paragraph()
    heading.paragraph_format.space_before = Pt(10)
    heading.paragraph_format.space_after = Pt(4)
    run = heading.add_run("询问内容")
    _set_run_font(run, size=Pt(12), bold=True, color=(28, 63, 104))

    for index, (question, answer) in enumerate(questions, start=1):
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.left_indent = Cm(0)
        paragraph.paragraph_format.first_line_indent = Cm(0)
        paragraph.paragraph_format.space_before = Pt(3)
        paragraph.paragraph_format.space_after = Pt(4)
        paragraph.paragraph_format.keep_together = True
        number = paragraph.add_run(f"{index:02d}  ")
        _set_run_font(number, name="Consolas", size=Pt(9), bold=True, color=(100, 120, 143))
        q_run = paragraph.add_run(f"问：{question}")
        _set_run_font(q_run, size=Pt(11), bold=True)
        paragraph.add_run().add_break()
        indent = paragraph.add_run("     ")
        _set_run_font(indent, size=Pt(11))
        a_run = paragraph.add_run(f"答：{answer}")
        _set_run_font(a_run, size=Pt(11))


def _add_signatures(document: Document, record: InquiryRecord) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(10)
    paragraph.paragraph_format.space_after = Pt(8)
    run = paragraph.add_run(record.closing)
    _set_run_font(run, size=Pt(10), bold=True)

    table = document.add_table(rows=3, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    for row in table.rows:
        row.cells[0].width = Cm(8)
        row.cells[1].width = Cm(8)
    values = [
        (f"被询问人签名：{record.identity['姓名']}（虚构测试签名）", "日期：2026年7月16日"),
        (f"询问人签名：{record.interviewers.split('（')[0]}", "日期：2026年7月16日"),
        (f"记录人签名：{record.recorder.split('（')[0]}", "核对结果：与陈述一致"),
    ]
    for row, row_values in zip(table.rows, values):
        for index, value in enumerate(row_values):
            _write_cell(row.cells[index], value)
    _set_table_borders(table, color="AEB9C6", size="5")

    warning = document.add_paragraph()
    warning.alignment = WD_ALIGN_PARAGRAPH.CENTER
    warning.paragraph_format.space_before = Pt(12)
    warning.paragraph_format.space_after = Pt(0)
    run = warning.add_run("本文件全部信息均为虚构，仅用于笔录审查系统功能测试，禁止用于真实案件。")
    _set_run_font(run, size=Pt(9), bold=True, color=(190, 45, 38))


def _build_record(record: InquiryRecord, path: Path) -> None:
    document = Document()
    _configure_document(document, record)

    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_before = Pt(4)
    title.paragraph_format.space_after = Pt(2)
    run = title.add_run("询问笔录")
    _set_run_font(run, name="方正小标宋简体", size=Pt(22), bold=True)

    subtitle = document.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(10)
    run = subtitle.add_run("虚构测试材料 - 不得用于真实案件")
    _set_run_font(run, size=Pt(10), bold=True, color=(190, 45, 38))

    _add_metadata_table(document, record)
    _add_identity_table(document, record.identity)
    _add_notice(document, record.notice)
    _add_questions(document, record.questions)
    _add_signatures(document, record)

    document.core_properties.title = f"{record.case_number} 询问笔录（虚构测试材料）"
    document.core_properties.subject = "笔录审查助手上传测试"
    document.core_properties.author = "Bilu Test Data Generator"
    document.core_properties.comments = "All names, identifiers, accounts and events are fictional test data."
    document.save(path)


def generate_test_records(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    for record in RECORDS:
        path = output_dir / record.filename
        _build_record(record, path)
        generated.append(path)
    return generated


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate fictional DOCX inquiry records for Bilu review testing.")
    parser.add_argument("--output-dir", type=Path, default=Path("output/doc"))
    args = parser.parse_args()
    paths = generate_test_records(args.output_dir)
    for path in paths:
        print(path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
