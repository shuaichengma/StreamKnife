NAME = "生成社工密码本"
CATEGORY = "文件制作"
DESC = "根据目标个人信息（姓名、生日、电话、地址、身份证号、微信号、QQ号、邮箱等）生成社工密码字典"

META = {
    "hide_input": True,
    "params": [
        {"name": "username", "type": "input", "label": "目标账户名"},
        {"name": "name", "type": "input", "label": "姓名"},
        {"name": "birthday", "type": "input", "label": "生日（如 19900101）"},
        {"name": "age", "type": "input", "label": "年龄"},
        {"name": "phone", "type": "input", "label": "电话"},
        {"name": "address", "type": "input", "label": "家庭住址"},
        {"name": "id_number", "type": "input", "label": "身份证号"},
        {"name": "wechat", "type": "input", "label": "微信号"},
        {"name": "qq", "type": "input", "label": "QQ号"},
        {"name": "email", "type": "input", "label": "邮箱号"},
        {"name": "custom_words", "type": "input", "label": "自定义关键词（空格分隔）"},
    ]
}

# ---------- 常用后缀 ----------
_COMMON_SUFFIXES = [
    "123", "123456", "12345", "1234", "1230",
    "@123", "@123456",
    "!", "@", "#", ".", "_",
    "1", "0", "00", "000",
    "888", "666", "520", "1314",
    "2024", "2025", "2026",
]


def _non_empty(*values: str):
    """返回所有非空字符串的列表"""
    return [v.strip() for v in values if v and v.strip()]


def _birthday_variants(birthday: str):
    """从生日生成常见变体 19900101 → 19900101, 900101, 0101, 1990, 90, 90101"""
    b = birthday.strip()
    if len(b) < 6:
        return [b]
    variants = [b]
    if len(b) == 8:  # YYYYMMDD
        variants += [b[2:], b[2:6], b[4:], b[:4], b[2:4]]
    elif len(b) == 6:  # YYMMDD
        variants += [b[2:], b[:4]]
    return list(dict.fromkeys(variants))


def _phone_variants(phone: str):
    """从手机号生成常见变体：全号、后4/6/8位"""
    p = phone.strip()
    variants = [p]
    for n in (4, 6, 8):
        if len(p) >= n:
            variants.append(p[-n:])
    return list(dict.fromkeys(variants))


def _add_suffixes(items: list, suffixes: list):
    """为每个 item 拼接常用后缀"""
    result = []
    for item in items:
        result.append(item)
        for suffix in suffixes:
            result.append(f"{item}{suffix}")
    return result


def _pair_combine(list_a: list, list_b: list):
    """两个列表的笛卡尔拼接"""
    result = []
    for a in list_a:
        for b in list_b:
            result.append(f"{a}{b}")
    return result


def run(data: str, config: dict) -> str:
    username = config.get("username", "").strip()
    name = config.get("name", "").strip()
    birthday = config.get("birthday", "").strip()
    age = config.get("age", "").strip()
    phone = config.get("phone", "").strip()
    address = config.get("address", "").strip()
    id_number = config.get("id_number", "").strip()
    wechat = config.get("wechat", "").strip()
    qq = config.get("qq", "").strip()
    email = config.get("email", "").strip()
    custom_words = config.get("custom_words", "").strip()

    pwd_set = set()

    # ---- 1. 各字段原始值及后缀 ----
    raw_fields = _non_empty(
        username, name, age, phone, wechat, qq,
        *(custom_words.split() if custom_words else []),
    )
    pwd_set.update(_add_suffixes(raw_fields, _COMMON_SUFFIXES))

    # 邮箱：取 @ 前部分
    email_prefix = ""
    if email and "@" in email:
        email_prefix = email.split("@")[0]
        pwd_set.update(_add_suffixes([email_prefix], _COMMON_SUFFIXES))

    # ---- 2. 姓名拼音首字母 ----
    name_parts = name.split() if name else []
    if len(name_parts) >= 2:
        initials = "".join(p[0].lower() for p in name_parts if p)
        pwd_set.update(_add_suffixes([initials], _COMMON_SUFFIXES))
        # 姓全拼 + 名首字母
        if len(name_parts[0]) > 0:
            last_full = name_parts[0].lower()
            first_init = name_parts[1][0].lower() if len(name_parts) > 1 and name_parts[1] else ""
            combo = f"{last_full}{first_init}"
            pwd_set.update(_add_suffixes([combo], _COMMON_SUFFIXES))

    # ---- 3. 生日变体 ----
    if birthday:
        bday_variants = _birthday_variants(birthday)
        pwd_set.update(bday_variants)
        pwd_set.update(_add_suffixes(bday_variants, _COMMON_SUFFIXES))

    # ---- 4. 电话变体 ----
    if phone:
        phone_vars = _phone_variants(phone)
        pwd_set.update(phone_vars)
        pwd_set.update(_add_suffixes(phone_vars, _COMMON_SUFFIXES))

    # ---- 5. 身份证号片段 ----
    if id_number and len(id_number) >= 12:
        pwd_set.add(id_number)
        # 后 6 位（出生日期部分）
        pwd_set.add(id_number[6:14])
        # 后 4 位
        pwd_set.add(id_number[-4:])
        # 前 6 位 + 后 4 位
        pwd_set.add(id_number[:6] + id_number[-4:])

    # ---- 6. 字段组合（姓名/用户 + 生日/电话/年龄） ----
    base_names = _non_empty(username, name, *(custom_words.split() if custom_words else []))
    numeric_segments = _non_empty(
        age,
        *(_birthday_variants(birthday) if birthday else []),
        *(_phone_variants(phone) if phone else []),
    )

    if base_names and numeric_segments:
        pwd_set.update(_pair_combine(base_names, numeric_segments))
        # 再加一遍后缀
        combos = _pair_combine(base_names, numeric_segments)
        pwd_set.update(_add_suffixes(combos, _COMMON_SUFFIXES))

    # ---- 7. 大小写变体 ----
    cased = set()
    for pwd in pwd_set:
        if any(c.isalpha() for c in pwd):
            cased.add(pwd.upper())
            cased.add(pwd.lower())
            cased.add(pwd.capitalize())
    pwd_set.update(cased)

    # ---- 8. 去重 + 排序 ----
    passwords = sorted(pwd_set)

    if not passwords:
        return "未填写任何信息，无法生成密码本"

    return "\n".join(passwords)
