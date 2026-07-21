from urllib.parse import quote, unquote

NAME = "URL编码/解码"
CATEGORY = "编码处理"
DESC = "对输入内容进行URL编码或解码，编码时支持全部编码或排除指定字符"

META = {
    "params": [
        {
            "name": "mode",
            "type": "radio",
            "label": "处理模式",
            "options": ["URL编码", "URL解码"],
            "default": "URL编码"
        },
        {
            "name": "encode_mode",
            "type": "radio",
            "label": "编码范围",
            "options": ["全部编码", "排除指定字符"],
            "default": "全部编码",
            "visible_when": {
                "param": "mode",
                "equals": "URL编码"
            }
        },
        {
            "name": "safe_chars",
            "type": "input",
            "label": "不编码的字符",
            "placeholder": "如: /:&= 表示这些字符保留原样不编码",
            "visible_when": {
                "param": "encode_mode",
                "equals": "排除指定字符"
            }
        }
    ]
}


def run(data: str, config: dict) -> str:
    mode = config.get("mode", "URL编码")
    result = []

    for line in data.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            if mode == "URL解码":
                result.append(unquote(line))
            else:
                encode_mode = config.get("encode_mode", "全部编码")
                if encode_mode == "排除指定字符":
                    safe = config.get("safe_chars", "")
                else:
                    safe = ""
                result.append(quote(line, safe=safe))

        except Exception:
            result.append(line)

    return "\n".join(result)
