import struct

NAME = "进制/字符转换"
CATEGORY = "编码处理"
DESC = (
    "支持二进制、八进制、十进制、十六进制、字符串之间批量转换；"
    "字符串可按UTF-8字节流或Unicode码点转十六进制，十进制可按IEEE754内存编码输出"
)

META = {
    "params": [
        {
            "name": "from_base",
            "type": "radio",
            "label": "原始类型",
            "options": [
                ("二进制", "binary"),
                ("八进制", "oct"),
                ("十进制", "decimal"),
                ("十六进制", "hex"),
                ("字符串", "string")
            ]
        },
        {
            "name": "to_base",
            "type": "radio",
            "label": "目标类型",
            "options": [
                ("二进制", "binary"),
                ("八进制", "oct"),
                ("十进制", "decimal"),
                ("十六进制", "hex"),
                ("字符串", "string")
            ]
        },
        {
            "name": "string_encoding",
            "type": "radio",
            "label": "字符串转十六进制方式",
            "options": [
                ("UTF-8字节流", "utf8"),
                ("Unicode码点", "unicode")
            ],
            "default": "utf8",
            "visible_when": [
                {"param": "from_base", "equals": "string"},
                {"param": "to_base", "equals": "hex"}
            ]
        },
        {
            "name": "add_prefix",
            "type": "checkbox",
            "label": "十六进制添加0x前缀",
            "default": True,
            "visible_when": [
                {"param": "from_base", "equals": "string"},
                {"param": "to_base", "equals": "hex"}
            ]
        },
        {
            "name": "ieee754",
            "type": "checkbox",
            "label": "按IEEE754内存编码输出（float）",
            "default": False,
            "visible_when": [
                {"param": "from_base", "equals": "decimal"},
                {"param": "to_base", "equals": "hex"}
            ]
        },
        {
            "name": "remove_spaces",
            "type": "checkbox",
            "label": "去除字符间空格",
            "default": False
        }
    ]
}


def decimal_fraction_to_base(frac, base, max_digits=16):
    """
    小数部分转换
    0.28125 -> 01001
    """
    result = []

    count = 0

    while frac > 0 and count < max_digits:
        frac *= base

        digit = int(frac)

        if digit < 10:
            result.append(str(digit))
        else:
            result.append(chr(ord('A') + digit - 10))

        frac -= digit
        count += 1

    return ''.join(result)


def decimal_to_base(number, base):
    """
    十进制 -> 任意进制（支持浮点）
    """

    digits = "0123456789ABCDEF"

    sign = ""

    if number < 0:
        sign = "-"
        number = abs(number)

    integer_part = int(number)
    fraction_part = number - integer_part

    # 整数部分
    if integer_part == 0:
        int_str = "0"
    else:
        int_result = []

        while integer_part:
            int_result.append(digits[integer_part % base])
            integer_part //= base

        int_str = ''.join(reversed(int_result))

    # 小数部分
    if fraction_part > 0:
        frac_str = decimal_fraction_to_base(
            fraction_part,
            base
        )

        return f"{sign}{int_str}.{frac_str}"

    return f"{sign}{int_str}"


def base_to_decimal(token, from_base):

    token = token.strip()

    # 单独处理符号，避免小数部分丢失负号（如 -1.1 二进制 → -1.5）
    sign = 1
    if token[:1] in ("+", "-"):
        if token[0] == "-":
            sign = -1
        token = token[1:]

    if '.' not in token:
        return sign * int(token, from_base)

    int_part, frac_part = token.split('.', 1)

    result = int(int_part, from_base)

    for idx, ch in enumerate(frac_part, start=1):

        value = int(ch, 16)

        # 校验数位是否属于当前进制，如二进制中出现 9 应报错
        if value >= from_base:
            raise ValueError(
                f"invalid digit {ch!r} for base {from_base}"
            )

        result += value / (from_base ** idx)

    return sign * result


def float_to_mem_hex(value):
    """float -> IEEE754 大端十六进制，如 1.5 -> 0x3fc00000"""
    packed = struct.pack('<f', float(value))
    return '0x' + ''.join(f'{b:02x}' for b in packed[::-1])


def string_to_hex_units(token, encoding):
    """字符串按 UTF-8 字节流或 Unicode 码点拆成十六进制单元"""
    if encoding == "unicode":
        return [f"{ord(ch):x}" for ch in token]
    return [f"{b:02x}" for b in token.encode("utf-8")]


def run(data: str, config: dict) -> str:

    from_base = config.get("from_base", "decimal")
    to_base = config.get("to_base", "decimal")
    remove_spaces = config.get("remove_spaces", False)
    string_encoding = config.get("string_encoding", "utf8")
    add_prefix = config.get("add_prefix", True)
    ieee754 = config.get("ieee754", False)

    tokens = data.strip().split()
    separator = "" if remove_spaces else " "

    results = []

    def convert_value(value):
        """把数值按 to_base 转成输出字符串。

        负数按「符号 + 绝对值」输出，如 -1 十六进制 → -0x1。
        """

        if to_base == "decimal":
            return str(value)

        if to_base == "binary":
            if isinstance(value, float) and not value.is_integer():
                return decimal_to_base(value, 2)
            sign = "-" if value < 0 else ""
            return sign + bin(abs(int(value)))[2:].zfill(8)

        if to_base == "oct":
            if isinstance(value, float) and not value.is_integer():
                return decimal_to_base(value, 8)
            sign = "-" if value < 0 else ""
            return sign + oct(abs(int(value)))[2:].zfill(3)

        if to_base == "hex":
            sign = "-" if value < 0 else ""
            if isinstance(value, float) and not value.is_integer():
                return sign + "0x" + decimal_to_base(abs(value), 16)
            return sign + "0x" + hex(abs(int(value)))[2:].upper()

        if to_base == "string":
            return chr(int(value))

        return None

    for token in tokens:

        try:

            # =========================
            # STRING -> STRING
            # =========================
            if from_base == "string" and to_base == "string":
                results.append(token)
                continue

            # =========================
            # STRING -> HEX
            # =========================
            if from_base == "string" and to_base == "hex":

                for unit in string_to_hex_units(token, string_encoding):
                    results.append(("0x" + unit) if add_prefix else unit)
                continue

            # =========================
            # HEX -> STRING
            # =========================
            if from_base == "hex" and to_base == "string":

                token = token.lower()

                if token.startswith("0x"):
                    token = token[2:]

                if len(token) % 2:
                    token = "0" + token

                text = bytes.fromhex(token).decode(
                    "latin1",
                    errors="ignore"
                )

                results.append(text)
                continue

            # =========================
            # 解析输入
            # =========================

            if from_base == "binary":
                value = base_to_decimal(token, 2)

            elif from_base == "oct":
                value = base_to_decimal(token, 8)

            elif from_base == "decimal":
                value = float(token) if "." in token else int(token)

            elif from_base == "hex":

                token = token.lower()

                if token.startswith("0x"):
                    token = token[2:]

                value = base_to_decimal(token, 16)

            elif from_base == "string":

                # 字符串 token 的每个字符单独转换，支持 "AB" 这类整段输入
                for ch in token:
                    results.append(convert_value(ord(ch)))
                continue

            else:
                results.append(f"[ERR:{token}]")
                continue

            # =========================
            # 输出转换
            # =========================

            if ieee754 and from_base == "decimal" and to_base == "hex":
                results.append(float_to_mem_hex(value))
                continue

            converted = convert_value(value)
            results.append(
                converted if converted is not None else f"[ERR:{token}]"
            )

        except Exception:

            results.append(f"[ERR:{token}]")

    return separator.join(results)