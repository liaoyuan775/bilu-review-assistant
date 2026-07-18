from app.services.victim_profile import extract_victim_profile


def test_extracts_explicit_victim_profile_fields():
    text = (
        "问：请说明个人情况。答：我叫陈某，女，38岁，汉族，"
        "身份证号码4301**********1234，工作单位某商贸公司，"
        "住址某市某区某街道，联系电话138****5678。"
    )

    profile = extract_victim_profile(text)

    assert profile is not None
    assert profile.model_dump() == {
        "name": "陈某",
        "gender": "女",
        "age": 38,
        "ethnicity": "汉族",
        "idNumber": "4301**********1234",
        "employer": "某商贸公司",
        "address": "某市某区某街道",
        "contact": "138****5678",
    }


def test_keeps_partial_profile_without_inferring_missing_fields():
    profile = extract_victim_profile("问：你叫什么名字？答：我叫李某。")

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
    assert extract_victim_profile("问：事情经过？答：我在家中收到一条短信。") is None


def test_extracts_explicit_fields_from_docx_table_text():
    text = (
        "姓名 | 赵测试 | 性别 | 女\n"
        "年龄 | 68岁 | 民族 | 汉族\n"
        "身份证号码 | 110101195804120048\n"
        "联系电话 | 13600000006 | 工作单位 | 测试市示范小学退休教师（虚构）\n"
        "现住址 | 测试省测试市演示区银龄街40号401室（虚构）"
    )

    profile = extract_victim_profile(text)

    assert profile is not None
    assert profile.model_dump() == {
        "name": "赵测试",
        "gender": "女",
        "age": 68,
        "ethnicity": "汉族",
        "idNumber": "110101195804120048",
        "employer": "测试市示范小学退休教师（虚构）",
        "address": "测试省测试市演示区银龄街40号401室（虚构）",
        "contact": "13600000006",
    }


def test_does_not_infer_age_or_employer_from_birth_date_and_occupation():
    profile = extract_victim_profile(
        "姓名 | 李样例 | 出生日期 | 1988年6月18日 | 职业 | 财务人员"
    )

    assert profile is not None
    assert profile.name == "李样例"
    assert profile.age is None
    assert profile.employer is None
