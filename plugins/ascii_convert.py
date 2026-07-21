NAME = "ASCII编码转换"
CATEGORY = "编码处理"
DESC = "字符与ASCII码互转，支持2/8/10/16进制"

META = {
    "params": [
        {
            "name": "mode",
            "type": "radio",
            "label": "转换模式",
            "options": [
                "字符→ASCII",
                "ASCII→字符"
            ]
        },
        {
            "name": "base",
            "type": "radio",
            "label": "输入进制",
            "options": [
                "2进制",
                "8进制",
                "10进制",
                "16进制"
            ]
        }
    ]
}


def encode_char(ch: str, base: int) -> str:
    value = ord(ch)
    if base == 2:
        return bin(value)[2:]
    if base == 8:
        return oct(value)[2:]
    if base == 16:
        return hex(value)[2:]

    return str(value)

def decode_ascii(value: str, base: int) -> str:
    return chr(int(value, base))

def run(data: str, config: dict) -> str:
    mode = config.get("mode", "字符→ASCII")
    base_text = config.get("base", "10进制")

    base_map = {
        "2进制": 2,
        "8进制": 8,
        "10进制": 10,
        "16进制": 16
    }

    base = base_map.get(base_text, 10)
    result = []

    if mode == "字符→ASCII":
        for line in data.splitlines():
            values = []
            for ch in line:
                values.append(
                    encode_char(ch, base)
                )
            result.append(
                " ".join(values)
            )
    else:
        for line in data.splitlines():
            chars = []
            for value in line.split():
                try:
                    chars.append(
                        decode_ascii(value, base)
                    )
                except Exception:
                    chars.append("?")
            result.append(
                "".join(chars)
            )

    return "\n".join(result)