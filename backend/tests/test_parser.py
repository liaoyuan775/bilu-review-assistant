from app.parsing.parser import _native_blocks


def test_native_pdf_lines_merge_into_complete_question_answer_pairs():
    blocks = _native_blocks(
        """页眉
03
问：请按时间顺序讲述事情经过。
答：2026年7月15日19时32分，我在家中看到广告，随后添加对
方微信。对方让我下载APP并转账，我在20时18分至21时06分之
间共转账三笔，之后意识到被骗并报警。
04
问：对方通过哪些平台联系你？
答：对方先通过短视频平台联系，后来添加微信。"""
    )

    assert [block.text for block in blocks] == [
        "页眉",
        "03 问：请按时间顺序讲述事情经过。 "
        "答：2026年7月15日19时32分，我在家中看到广告，随后添加对"
        "方微信。对方让我下载APP并转账，我在20时18分至21时06分之"
        "间共转账三笔，之后意识到被骗并报警。",
        "04 问：对方通过哪些平台联系你？ 答：对方先通过短视频平台联系，后来添加微信。",
    ]


def test_native_pdf_question_pair_stops_before_closing_and_signatures():
    blocks = _native_blocks(
        """15
问：以上内容是否确认？
答：我确认以上内容无误。
询问结束后，被询问人逐页核对笔录。
被询问人签名：张测试
核对结果：与陈述一致
本文件全部信息均为虚构。"""
    )

    assert [block.text for block in blocks] == [
        "15 问：以上内容是否确认？ 答：我确认以上内容无误。",
        "询问结束后，被询问人逐页核对笔录。",
        "被询问人签名：张测试",
        "核对结果：与陈述一致",
        "本文件全部信息均为虚构。",
    ]
