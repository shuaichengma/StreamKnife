NAME = "进制/字符转换"
CATEGORY = "编码处理"
DESC = "支持二进制、八进制、十进制、十六进制、字符串之间批量转换"

META = {
    "params": [
        {
            "name": "from_base",
            "type": "radio",
            "label": "原始类型",
            "options": ["binary", "oct", "decimal", "hex", "string"]
        },
        {
            "name": "to_base",
            "type": "radio",
            "label": "目标类型",
            "options": ["binary", "oct", "decimal", "hex", "string"]
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

    if '.' not in token:
        return int(token, from_base)

    int_part, frac_part = token.split('.', 1)

    result = int(int_part, from_base)

    for idx, ch in enumerate(frac_part, start=1):

        value = int(ch, 16)

        result += value / (from_base ** idx)

    return result


def run(data: str, config: dict) -> str:

    from_base = config.get("from_base", "decimal")
    to_base = config.get("to_base", "decimal")

    tokens = data.strip().split()

    results = []

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

                hex_str = ''.join(
                    f"{ord(c):02X}"
                    for c in token
                )

                results.append("0x" + hex_str)
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

                if len(token) != 1:
                    results.append(f"[ERR:{token}]")
                    continue

                value = ord(token)

            else:
                results.append(f"[ERR:{token}]")
                continue

            # =========================
            # 输出转换
            # =========================

            if to_base == "decimal":
                results.append(str(value))

            elif to_base == "binary":

                if isinstance(value, float) and not value.is_integer():
                    results.append(decimal_to_base(value, 2))
                else:
                    results.append(
                        bin(int(value))[2:].zfill(8)
                    )

            elif to_base == "oct":

                if isinstance(value, float) and not value.is_integer():
                    results.append(decimal_to_base(value, 8))
                else:
                    results.append(
                        oct(int(value))[2:].zfill(3)
                    )

            elif to_base == "hex":

                if isinstance(value, float) and not value.is_integer():
                    results.append(
                        "0x" + decimal_to_base(value, 16)
                    )
                else:
                    results.append(
                        "0x" + hex(int(value))[2:].upper()
                    )

            elif to_base == "string":

                results.append(chr(int(value)))

            else:

                results.append(f"[ERR:{token}]")

        except Exception:

            results.append(f"[ERR:{token}]")

    return " ".join(results)