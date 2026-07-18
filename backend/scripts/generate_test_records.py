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
            "年龄": "36岁",
            "民族": "汉族",
            "出生日期": "1990年2月3日",
            "身份证号码": "ID_TEST_CASE_01",
            "联系电话": "PHONE_TEST_01",
            "工作单位": "测试科技有限公司（虚构）",
            "户籍地址": "测试省测试市演示区验证路1号（虚构）",
            "现住址": "测试省测试市演示区样例街10号101室（虚构）",
        },
        notice="询问人已向被询问人出示工作证件，并依法告知其如实陈述、申请回避、核对笔录等权利义务。被询问人表示已经听清，不申请回避，自愿接受询问。",
        questions=[
            ("请说明你的姓名、性别、出生日期、身份证号码、联系电话、住址和工作单位。", "我叫张测试，男，1990年2月3日出生，身份证号码ID_TEST_CASE_01，手机号PHONE_TEST_01，现住测试省测试市演示区样例街10号101室，在测试科技有限公司担任项目专员。以上均为虚构测试信息。"),
            ("你是否已经听清权利义务告知，是否申请询问人员回避？", "我已经听清，不申请回避。"),
            ("请按时间顺序讲述事情经过。", "2026年7月15日19时32分，我在家中使用手机浏览短视频时看到兼职广告，随后添加对方微信。对方让我下载名为优选任务的APP并以刷单返利为由转账。我在20时18分至21时06分之间共转账三笔，之后对方要求继续缴纳解冻费，我意识到可能被骗并于21时25分报警。"),
            ("对方通过哪些平台联系你，双方账号分别是什么？", "最初在短视频平台联系，对方平台账号为video_test_001；后来使用微信联系，对方微信号wx_service_test_001，我的微信号ACCOUNT_WX_CASE_01；APP登录账号为app_user_test_001，绑定手机号PHONE_TEST_01。"),
            ("聊天记录和相关账号资料是否保存？", "全部聊天记录、账号主页截图和二维码截图都已保存在我的测试手机中，文件目录为case001_chat_test，未进行删除。"),
            ("APP名称、下载来源、链接、安装时间和当前状态是什么？", "APP名称为优选任务测试版，下载链接为URL_TEST_CASE_01，2026年7月15日19时55分安装，安装包文件名task-demo-001.apk，当前仍可打开，版本号1.0.1-test。"),
            ("请说明你用于转账的银行卡和支付账户。", "我使用的测试银行卡为工商银行测试卡CARD_TEST_03，开户名张测试；支付宝测试账号pay_test_001，绑定手机号PHONE_TEST_01。"),
            ("请逐笔说明第一笔转账的时间、金额、收款账户和流水号。", "第一笔于2026年7月15日20时18分转账1000元，收款测试卡号CARD_TEST_14，户名王演示，流水号：TEST202607150001。"),
            ("请逐笔说明第二笔转账的时间、金额、收款账户和流水号。", "第二笔于2026年7月15日20时42分转账3000元，收款测试卡号CARD_TEST_14，户名王演示，流水号：TEST202607150002。"),
            ("请逐笔说明第三笔转账的时间、金额、收款账户和流水号。", "第三笔于2026年7月15日21时06分转账5000元，支付宝收款测试账号merchant_test_001，交易单号：PAY-TEST-20260715-003。"),
            ("三笔转账合计损失多少，是否收到返利？", "三笔共计转出9000元。2026年7月15日20时25分收到200元测试返利，返利进入支付宝账号pay_test_001，因此实际损失8800元。返利流水号：REBATE-TEST-001。"),
            ("对方是否要求寄递银行卡、手机卡、现金或其他物品？", "没有，对方没有要求寄递任何物品。"),
            ("是否有朋友、同事或其他人员向你推荐该项目？", "没有，我是自行看到广告后联系对方的。"),
            ("你能否提供设备、网络和电子证据情况？", "使用的是测试手机TEST-PHONE-001，设备IMEI测试值860000000000001，案发时连接家庭测试网络，公网IP记录值IP_TEST_CASE_01。聊天截图、银行流水和APK安装包均可提交。"),
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
            "年龄": "38岁",
            "民族": "汉族",
            "出生日期": "1988年6月18日",
            "身份证号码": "ID_TEST_CASE_02",
            "联系电话": "PHONE_TEST_02",
            "工作单位": "测试商贸有限公司（虚构）",
            "户籍地址": "测试省测试市演示区规范路2号（虚构）",
            "现住址": "测试省测试市演示区格式街20号202室（虚构）",
        },
        notice="本文件用于验证系统识别未询问事项。询问开始时仅核对了被询问人身份，笔录正文中未记录权利义务告知及回避申请情况。",
        questions=[
            ("请说明你的姓名、身份证号码、联系电话和住址。", "我叫李样例，身份证号码ID_TEST_CASE_02，手机号PHONE_TEST_02，现住测试省测试市演示区格式街20号202室。以上均为虚构测试信息。"),
            ("发生了什么事情？", "2026年7月15日中午，我收到一个QQ好友申请，对方说可以协助办理低息贷款。我按对方要求填写资料并转了两笔钱，后来发现无法联系对方。"),
            ("对方使用的QQ账号是什么？", "对方QQ测试账号为ACCOUNT_QQ_CASE_02，昵称贷款顾问测试号，我的QQ测试账号为qq_user_test_002。"),
            ("你使用哪张银行卡转账，收款卡号是什么？", "我使用建设银行测试卡CARD_TEST_06，开户名李样例，向收款测试卡CARD_TEST_15转账，收款户名赵模拟。"),
            ("其中一笔转账的情况是什么？", "2026年7月15日12时36分转账5000元，流水号：TEST202607150101。另一笔只记得金额是8000元。"),
            ("总共损失多少？", "共转出13000元，没有收到任何返款。"),
            ("聊天记录是否还在？", "QQ聊天记录仍保存在测试手机TEST-PHONE-002内，我截取了部分页面，但没有导出完整聊天记录。"),
            ("是否还有其他情况？", "对方后来让我继续支付保证金，我没有再转账。除此之外没有补充。"),
        ],
        closing="本笔录有意保留未询问事项，仅用于测试提问遗漏和回答不完整状态，不代表真实办案笔录质量。",
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
            "年龄": "32岁",
            "民族": "土家族",
            "出生日期": "1993年11月9日",
            "身份证号码": "ID_TEST_CASE_03",
            "联系电话": "PHONE_TEST_03",
            "工作单位": "测试物流有限公司（虚构）",
            "户籍地址": "测试省测试市演示区流程路3号（虚构）",
            "现住址": "测试省测试市演示区节点街30号303室（虚构）",
        },
        notice="询问人已出示工作证件并告知权利义务。被询问人表示听清告知内容，不申请回避，同意就APP刷单返利、转账及相关人员情况接受询问。",
        questions=[
            ("请核对你的身份、电话、住址和职业。", "我叫周演示，男，1993年11月9日出生，身份证号码ID_TEST_CASE_03，手机号PHONE_TEST_03，现住测试省测试市演示区节点街30号303室，在测试物流有限公司担任调度员。以上均为虚构测试信息。"),
            ("是否听清权利义务告知，是否申请回避？", "已经听清，不申请回避。"),
            ("是谁向你介绍这个兼职项目的？", "测试同事孙案例通过企业微信推荐给我，他的企业微信测试账号为workwx_test_003，手机号PHONE_TEST_04。"),
            ("孙案例如何获得这个项目，对方真实身份是什么？", "我不知道。孙案例只说是在一个测试群里看到的，没有告诉我发布人的真实姓名。"),
            ("你后来与对方通过哪些账号联系？", "我使用微信测试账号wx_user_test_003联系对方微信wx_service_test_003，又加入QQ群TEST-GROUP-003，群主QQ账号qq_owner_test_003。"),
            ("使用的APP名称和登录账号是什么？", "APP名称为云商助手测试版，登录账号ACCOUNT_APP_CASE_03，绑定手机号PHONE_TEST_03，邀请码INVITE-TEST-003。"),
            ("APP从哪里下载，链接和安装包是否保存？", "通过微信收到链接URL_TEST_CASE_03，安装包文件名cloud-shop-test-003.apk，SHA256测试值TESTSHA256CASE003000000000000000000000000000000000000000000000，安装包仍保存在测试手机中。"),
            ("APP当前是否可用，最后登录时间和网络地址是什么？", "APP当前还能打开，最后登录时间为2026年7月16日08时20分，测试服务地址api.example.test，登录日志中的保留IP为IP_TEST_CASE_03。"),
            ("请说明你的付款银行卡和支付账号。", "我使用农业银行测试卡CARD_TEST_07，开户名周演示；支付宝测试账号pay_test_003；数字钱包测试账号wallet_test_003。"),
            ("第一笔付款的时间、金额、收款信息和流水号是什么？", "2026年7月14日18时12分支付2000元，收款测试卡CARD_TEST_16，户名钱测试，流水号：TEST202607140301。"),
            ("第二笔付款的时间、金额、收款信息和流水号是什么？", "2026年7月14日19时05分支付6000元，支付宝商户测试账号merchant_test_003，交易单号：PAY-TEST-20260714-302。"),
            ("第三笔付款的时间、金额、收款信息和流水号是什么？", "2026年7月15日09时26分通过数字钱包支付12000元，钱包收款测试账号wallet_receiver_test_003，流水号：WALLET-TEST-303。"),
            ("返利和提现情况如何？", "第一笔任务后返利300元，于2026年7月14日18时25分进入支付宝账号pay_test_003，返利流水号：REBATE-TEST-003。之后APP显示可提现26000元，但要求先交认证金，我没有实际提现成功。"),
            ("三笔付款及返利后的实际损失是多少？", "共支付20000元，收到返利300元，实际损失19700元。"),
            ("是否寄递过银行卡、电话卡、现金或设备？", "对方要求寄送一张电话卡，我通过测试快递寄出空白测试卡片，测试快递公司为示例速运，测试单号TEST-EXPRESS-003，寄件时间2026年7月15日14时10分，收件人为吴模拟，测试电话PHONE_TEST_05，地址为测试省测试市样例区收件路88号。"),
            ("你是否清楚收件人吴模拟与对方的关系？", "我不知道。我只在APP客服消息中看到这个收件姓名。"),
            ("现有电子证据包括哪些？", "包括微信和QQ群聊天记录、APP安装包、APP页面录屏、三笔支付凭证、返利记录、快递电子面单和测试手机TEST-PHONE-003。所有材料均存放在case003_evidence_test目录。"),
            ("是否还有其他相关人员或账号？", "孙案例后来也表示无法提现，他的测试手机号PHONE_TEST_04。除此之外没有发现其他人员。"),
            ("以上内容是否经过核对？", "我已经核对，除我明确无法确认的两项外，其余账号、卡号、时间、金额和流水号均按本次虚构测试材料完整陈述。"),
        ],
        closing="询问结束后，被询问人核对笔录并确认：文中账号、卡号、流水号、IP、链接及人员信息均为虚构测试值。",
    ),
    InquiryRecord(
        filename="04-冒充公检法-老年人ATM询问笔录.docx",
        case_number="TEST-2026-0716-004",
        inquiry_number="第1次",
        start_time="2026年7月16日08时35分",
        end_time="2026年7月16日11时25分",
        location="测试市公安局反诈中心第四询问室（虚构）",
        interviewers="测试民警庚、测试民警辛（虚构，编号TEST-P007、TEST-P008）",
        recorder="测试记录员丁（虚构，编号TEST-R004）",
        identity={
            "姓名": "赵测试",
            "性别": "女",
            "年龄": "68岁",
            "民族": "汉族",
            "出生日期": "1958年4月12日",
            "身份证号码": "ID_TEST_CASE_04",
            "联系电话": "PHONE_TEST_06",
            "工作单位": "测试市示范小学退休教师（虚构）",
            "户籍地址": "测试省测试市演示区平安路4号（虚构）",
            "现住址": "测试省测试市演示区银龄街40号401室（虚构）",
        },
        notice="询问人已出示工作证件，向被询问人告知如实陈述、申请回避、核对和更正笔录等权利义务。被询问人表示已经听清，不申请回避，并由其女儿测试家属甲陪同在等候区。",
        questions=[
            ("请说明你的姓名、性别、年龄、民族、身份证号码、工作单位、住址和联系电话。", "我叫赵测试，女，68岁，汉族，身份证号码ID_TEST_CASE_04，联系电话PHONE_TEST_06，是测试市示范小学退休教师，现住测试省测试市演示区银龄街40号401室。以上均为虚构测试信息。"),
            ("是否听清权利义务告知，是否申请回避？", "我已经听清，不申请回避。"),
            ("请从接到电话开始按时间顺序讲述事情经过。", "2026年7月13日9时18分，我独自在家使用测试手机TEST-PHONE-004接到号码PHONE_TEST_10的电话。对方自称测试市公安局刑侦支队民警，说我的银行卡涉及洗钱，随后让我通过会议软件接受视频询问，并要求我对家人保密。"),
            ("对方使用了什么身份、账号和联系方式？", "第一名男子自称陈警官，虚构警号TEST-J004，来电号码PHONE_TEST_10；第二名女子自称测试检察院刘检察官，会议账号meeting_police_test_004。两人都只在电话和视频中出现。"),
            ("对方向你展示了什么材料，提出了什么要求？", "对方通过视频展示带有我姓名和虚构编号WARRANT-TEST-004的通缉令截图，声称要把全部存款转到安全账户接受资金审查，并要求持续打开屏幕共享。"),
            ("你安装了什么软件，进行了哪些操作？", "我按短信链接URL_TEST_CASE_04下载会议协查测试版APP，安装包名meeting-test-004.apk，登录账号user_meeting_test_004，并开启屏幕共享和麦克风权限。"),
            ("第一次转账时你在哪里，当时有哪些人在场？", "2026年7月13日10时42分，我独自到测试银行和平支行ATM区，使用银行卡和手机操作。当时大厅有测试银行工作人员甲，工作人员问我用途，我按对方要求说是给亲属转账。"),
            ("请说明第一笔转账的付款卡、收款账户、金额和流水号。", "我使用测试银行借记卡CARD_TEST_10，于10时48分通过ATM转账60000元至测试收款卡CARD_TEST_01，户名高模拟，流水号：TEST202607130401。"),
            ("第二笔转账的具体情况是什么？", "11时16分，我仍在ATM区转账40000元至测试收款卡CARD_TEST_02，户名马会例，流水号：TEST202607130402。"),
            ("总损失、返还及止付冻结情况如何？", "两笔共转出100000元，没有返还。女儿发现后于15时52分联系测试银行，银行反馈第一账户已转出，第二账户测试性冻结20000元，止付编号STOP-TEST-004。"),
            ("涉案手机、银行卡和安装包目前在哪里，能否提取查验？", "测试手机TEST-PHONE-004和银行卡CARD_TEST_10都由我带来，可以依法提取查验；会议APP已经卸载，原安装包没有单独保存。"),
            ("通话、短信、视频和转账电子痕迹是否保存？", "两笔ATM凭条和银行短信还在。对方让我删除通话记录和会议聊天记录，我照做了，只保留女儿后来拍摄的短信截图，视频通话没有录屏。"),
            ("是否还有其他相关人员，他们与对方是什么关系？", "我不知道对方两人的真实身份和关系。测试银行工作人员甲只在ATM大厅劝问过我，女儿测试家属甲在事后发现转账，他们都没有参与对方的安排。"),
            ("你是怎样发现被骗并报案的？", "当天15时40分，女儿看到ATM凭条后拨打真实110核实，确认没有所谓安全账户。我们15时52分先联系银行止付，16时05分到测试市公安局报案。"),
            ("转账后对方是否继续联系或要求其他行为？", "对方在12时10分再次来电，要求我下午办理抵押贷款继续转账，我没有办理。发现被骗后该号码已无法接通。"),
            ("以上陈述和证据情况是否经过核对？", "我已核对。账号、卡号、警号、止付编号及案情均为虚构测试值，通话记录删除和电子证据不完整的情况属本材料设定。"),
        ],
        closing="被询问人已逐页核对笔录，确认ATM转账、所谓安全账户、电子痕迹删除和报案处置时间线记录无误。",
    ),
    InquiryRecord(
        filename="05-投资交友-数字货币询问笔录.docx",
        case_number="TEST-2026-0716-005",
        inquiry_number="第2次",
        start_time="2026年7月16日13时10分",
        end_time="2026年7月16日17时20分",
        location="测试市公安局反诈中心第五询问室（虚构）",
        interviewers="测试民警壬、测试民警癸（虚构，编号TEST-P009、TEST-P010）",
        recorder="测试记录员戊（虚构，编号TEST-R005）",
        identity={
            "姓名": "钱案例",
            "性别": "女",
            "年龄": "42岁",
            "民族": "回族",
            "出生日期": "1984年1月26日",
            "身份证号码": "ID_TEST_CASE_05",
            "联系电话": "PHONE_TEST_07",
            "工作单位": "测试文化传播有限公司（虚构）",
            "户籍地址": "测试省测试市演示区诚信路5号（虚构）",
            "现住址": "测试省测试市演示区星河街50号502室（虚构）",
        },
        notice="询问人已依法告知权利义务并说明本次系第二次询问，重点核对前次陈述中的转账笔数、数字货币去向和相关人员关系。被询问人表示听清，不申请回避。",
        questions=[
            ("请再次核对姓名、性别、年龄、民族、身份证号码、工作单位、住址和联系方式。", "我叫钱案例，女，42岁，回族，身份证号码ID_TEST_CASE_05，联系电话PHONE_TEST_07，在测试文化传播有限公司工作，现住测试省测试市演示区星河街50号502室。以上均为虚构测试信息。"),
            ("是否听清本次询问的权利义务告知？", "已经听清，不申请回避。"),
            ("你最初如何认识对方？", "2026年6月20日22时15分，我在测试交友平台收到账号heart_test_005的私信。对方自称林顾问，微信测试号wx_invest_test_005，之后每天与我聊天并以恋爱关系称呼我。"),
            ("对方如何引导你参与投资？", "聊天约一周后，对方称其舅舅掌握数字货币行情，让我加入稳健财富测试群，群号TEST-GROUP-005。群内导师账号mentor_test_005发布盈利截图，助理账号assistant_test_005指导充值。"),
            ("你使用了什么平台和账号？", "我通过链接URL_TEST_CASE_05下载星河资本测试版APP，登录账号invest_user_test_005，绑定手机号PHONE_TEST_07，APP内显示美元、黄金和USDT投资栏目。"),
            ("第一次付款的时间、金额和账户是什么？", "2026年6月28日10时12分，我使用测试银行借记卡CARD_TEST_11转账10000元至测试卡CARD_TEST_04，户名郑模拟，流水号：TEST202606280501。"),
            ("第二笔付款情况是什么？", "6月30日14时36分，我通过支付宝测试账号pay_test_005向商户账号merchant_test_005支付25000元，交易单号：PAY-TEST-20260630-502。"),
            ("第三笔数字货币交易如何完成？", "7月2日16时08分，我在合规测试交易页面用30000元购买约4200枚USDT，并按助理指令转至测试钱包地址TTestWallet005Receiver，链上测试流水号：CHAIN-TEST-00503。"),
            ("前次你说只有三笔85000元，本次为何出现第四笔？", "这是前后陈述需要更正的地方。我前次紧张，把7月5日通过手机银行转出的20000元漏算了；第四笔收款卡为CARD_TEST_05，户名孙样本，流水号：TEST202607050504。"),
            ("请最终核对付款总额、返利和实际损失。", "四次付款分别为10000元、25000元、30000元和20000元，共85000元。APP曾返还5000元到支付宝测试账号pay_test_005，因此实际损失80000元；我前次说三笔85000元是笔数错误，不是总额错误。"),
            ("为什么又提到105000元？", "APP页面显示的105000元是包含虚假盈利20000元后的账户余额，不是我的实际转出金额。我确认实际转出85000元。"),
            ("案发时你通常在哪里、使用什么设备，有无他人在场？", "前三次操作都在家中书房，使用测试手机TEST-PHONE-005，独自操作；第四次在单位午休时用办公电脑TEST-PC-005登录手机银行，同事测试证人乙在旁边但并不清楚具体内容。"),
            ("对方、导师、助理和群成员之间是什么关系？", "我不知道他们真实姓名和相互关系。表面上林顾问负责与我建立感情，导师发布指令，助理提供收款账户，群成员不断发送盈利截图。"),
            ("现有电子证据包括哪些？", "交友平台私信、微信聊天、群聊、APP录屏、四笔支付凭证、USDT链上记录和钱包地址均已导出到case005_evidence_test目录，测试手机和办公电脑都可提供查验。"),
            ("涉案APP和设备当前状态如何？", "APP仍安装在测试手机中但已经无法登录，安装包invest-test-005.apk仍在下载目录；手机、电脑和银行卡均由我控制，未恢复出厂或格式化。"),
            ("你何时发现被骗，采取了什么措施？", "7月8日9时20分申请提现时被要求再付认证金，我联系林顾问无回应，10时05分意识到被骗，10时18分联系银行和交易平台，11时02分到公安机关报案。"),
            ("止付冻结和资金返还情况如何？", "银行反馈第四笔收款卡测试性止付8000元，支付宝和链上转账未追回，除此前5000元返还外没有收到其他款项，止付编号STOP-TEST-005。"),
            ("以上更正是否为你的最终陈述？", "是。我确认四笔实际转出85000元、返还5000元、实际损失80000元；文中人物、账号、钱包和金额均为虚构测试数据。"),
        ],
        closing="本次笔录重点记录投资交友、群聊诱导、银行卡和数字货币流向，并对前后陈述中的笔数与APP余额作出明确校正。",
    ),
    InquiryRecord(
        filename="06-冒充客服-远程控制询问笔录.docx",
        case_number="TEST-2026-0716-006",
        inquiry_number="第1次",
        start_time="2026年7月17日09时05分",
        end_time="2026年7月17日12时30分",
        location="测试市公安局演示派出所第六询问室（虚构）",
        interviewers="测试民警子、测试民警丑（虚构，编号TEST-P011、TEST-P012）",
        recorder="测试记录员己（虚构，编号TEST-R006）",
        identity={
            "姓名": "孙模拟",
            "性别": "男",
            "年龄": "29岁",
            "民族": "苗族",
            "出生日期": "1997年3月15日",
            "身份证号码": "ID_TEST_CASE_06",
            "联系电话": "PHONE_TEST_08",
            "工作单位": "测试智能制造有限公司（虚构）",
            "户籍地址": "测试省测试市演示区守信路6号（虚构）",
            "现住址": "测试省测试市演示区云端街60号603室（虚构）",
        },
        notice="询问人已依法告知被询问人相关权利义务。被询问人表示听清，不申请回避，自愿就冒充客服退款、屏幕共享、远程控制和网贷资金转移过程接受询问。",
        questions=[
            ("请说明姓名、性别、年龄、民族、身份证号码、工作单位、现住址和联系电话。", "我叫孙模拟，男，29岁，苗族，身份证号码ID_TEST_CASE_06，联系电话PHONE_TEST_08，在测试智能制造有限公司工作，现住测试省测试市演示区云端街60号603室。以上均为虚构测试信息。"),
            ("是否听清权利义务告知，是否申请回避？", "已经听清，不申请回避。"),
            ("事情最初是怎样发生的？", "2026年7月16日18时22分，我在单位加班时接到号码PHONE_TEST_11的电话，对方自称测试电商平台客服，说我购买的耳机存在质量问题，要办理三倍退款。"),
            ("对方后来通过什么方式联系你？", "对方让我添加企业微信账号service_refund_test_006，又发送会议号MEETING-TEST-006，要求我下载云会议测试版和协助通远程控制软件。"),
            ("你为什么开启屏幕共享和远程控制？", "对方说需要核验退款账户。我在测试手机TEST-PHONE-006上开启屏幕共享，又在办公电脑TEST-PC-006安装remote-test-006.exe并允许远程控制。"),
            ("是否提供了验证码、密码或其他验证信息？", "我读出了两条短信验证码，验证码测试值分别为TEST-0618和TEST-0621。我没有主动说银行卡密码，但对方远程操作时能看到我输入手机银行登录信息。"),
            ("对方如何利用网贷？", "对方让我打开三个网贷测试APP，声称关闭错误开通的理赔通道，实际分别申请了20000元、30000元和15000元贷款，贷款到账我的测试银行卡CARD_TEST_12。"),
            ("第一笔资金转出情况是什么？", "19时06分，手机银行转账20000元至测试卡CARD_TEST_08，户名李模拟，流水号：TEST202607160601。"),
            ("第二笔资金转出情况是什么？", "19时18分，通过测试支付账号pay_test_006扫码支付30000元至商户merchant_test_006，交易单号：PAY-TEST-20260716-602。"),
            ("第三笔资金如何转出？", "19时31分，对方远程控制办公电脑将15000元转至测试卡CARD_TEST_09，户名吴案例，流水号：TEST202607160603。"),
            ("总损失和负债是多少？", "三笔共转出65000元，全部来自刚到账的网贷。我没有收到退款或返款，目前形成65000元测试贷款负债。"),
            ("当时有哪些人在场？", "开始时我独自在工位，19时20分同事测试证人丙回来，看到电脑被远程控制后提醒我停止操作。同事与对方没有关系。"),
            ("涉案设备、软件和银行卡目前状态如何？", "手机、办公电脑和银行卡均已断网保存，可以查验。云会议APP仍在，协助通软件已由公司网管隔离但未删除，安装包和系统日志均已保留。"),
            ("电子痕迹保存是否完整？", "企业微信聊天、会议号、短信验证码、银行流水、支付凭证和电脑远程日志已经保存；电话录音没有保存，第一通来电记录仍在。"),
            ("你怎样发现被骗并处置？", "同事提醒后我在19时36分拔掉电脑网线并挂断电话，19时42分联系银行止付，20时05分报警，20时28分将设备交公司网管封存。"),
            ("资金是否冻结或追回？", "测试银行反馈第一收款账户冻结5000元，其余未追回；三个网贷平台已登记争议，止付编号STOP-TEST-006。"),
            ("以上陈述是否经过核对？", "已经核对。远程控制、验证码、网贷、设备日志和账户信息均为本次系统测试设定，不对应真实案件。"),
        ],
        closing="被询问人确认笔录完整记录冒充客服话术、屏幕共享、远程控制、验证码泄露、网贷到账和资金转移时间线。",
    ),
    InquiryRecord(
        filename="07-线下取现-寄递黄金询问笔录.docx",
        case_number="TEST-2026-0716-007",
        inquiry_number="第1次",
        start_time="2026年7月17日14时00分",
        end_time="2026年7月17日15时35分",
        location="测试市公安局演示派出所第七询问室（虚构）",
        interviewers="测试民警寅、测试民警卯（虚构，编号TEST-P013、TEST-P014）",
        recorder="测试记录员庚（虚构，编号TEST-R007）",
        identity={
            "姓名": "吴样本",
            "性别": "男",
            "年龄": "55岁",
            "民族": "汉族",
            "出生日期": "1971年8月8日",
            "身份证号码": "ID_TEST_CASE_07",
            "联系电话": "PHONE_TEST_09",
            "工作单位": "测试建筑设计院（虚构）",
            "户籍地址": "测试省测试市演示区求实路7号（虚构）",
            "现住址": "测试省测试市演示区金桥街70号704室（虚构）",
        },
        notice="询问人已依法告知权利义务。该笔录为故意保留提问遗漏的测试材料，正文主要核对取现和购买黄金金额，未询问电子痕迹、收取人员身份关系及现物提取情况。",
        questions=[
            ("请说明姓名、性别、年龄、民族、身份证号码、工作单位、住址和联系电话。", "我叫吴样本，男，55岁，汉族，身份证号码ID_TEST_CASE_07，联系电话PHONE_TEST_09，在测试建筑设计院工作，现住测试省测试市演示区金桥街70号704室。以上均为虚构测试信息。"),
            ("是否听清权利义务告知？", "已经听清，不申请回避。"),
            ("请简单讲述事情经过。", "2026年7月15日，我接到自称平台风控人员的电话，对方说我的账户违规，让我把资金取成现金并购买黄金交给指定人员核验，否则影响征信。"),
            ("你使用哪张银行卡取现？", "我使用测试银行借记卡CARD_TEST_13，开户名吴样本。"),
            ("第一次取现的金额和凭证是什么？", "7月15日10时20分，我在测试银行中心支行柜台取现100000元，柜面流水号：TEST202607150701。"),
            ("第二次取现情况是什么？", "7月15日14时05分，我在测试银行东城支行取现50000元，柜面流水号：TEST202607150702。"),
            ("购买黄金的金额和凭证是什么？", "7月16日9时30分，我在测试金店购买投资金条100000元，交易单号：GOLD-TEST-20260716-703，使用同一银行卡刷卡支付。"),
            ("现金如何交付？", "我把150000元现金装入文件袋，7月15日16时在测试市演示区桥南路公交站交给一名戴口罩男子。"),
            ("黄金如何交付？", "7月16日11时，我把金条放入纸箱，通过对方安排的网约车寄递黄金，测试订单号RIDE-TEST-007，车辆测试号牌TEST-A007。"),
            ("总损失是多少？", "现金150000元、黄金100000元，合计损失250000元，没有收到任何返还。"),
            ("什么时候发现被骗并报案？", "7月16日18时，我向真实平台客服核实后发现被骗，18时20分联系银行，19时到公安机关报案。"),
            ("是否还记得其他情况？", "我只记得取现、购买黄金和交付的大概过程，接收现金人员的具体体貌和网约车司机情况没有进一步核对。"),
            ("以上内容是否确认？", "我确认金额和凭证编号无误。本次笔录故意未询问手机、通话账号、聊天记录、收取人员关系、现金袋和黄金包装现物去向，用于测试提问遗漏。"),
        ],
        closing="本笔录为虚构测试材料，故意保留电子现痕、涉案现物和人员关系等未询问事项，用于验证系统能否区分提问遗漏与回答不完整。",
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
    row_count = (len(items) + 1) // 2
    table = document.add_table(rows=row_count, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    widths = [Cm(2.2), Cm(5.2), Cm(2.2), Cm(6.3)]
    for row_index, row in enumerate(table.rows):
        for cell_index, cell in enumerate(row.cells):
            cell.width = widths[cell_index]
        left_label, left_value = items[row_index * 2]
        right_index = row_index * 2 + 1
        right_label, right_value = items[right_index] if right_index < len(items) else ("", "")
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
            _set_cell_margins(row.cells[index], top=40, start=120, bottom=40, end=120)
    _set_table_borders(table, color="AEB9C6", size="5")

    warning = document.add_paragraph()
    warning.alignment = WD_ALIGN_PARAGRAPH.CENTER
    warning.paragraph_format.space_before = Pt(4)
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
