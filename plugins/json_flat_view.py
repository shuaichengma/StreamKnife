import json

NAME = "JSON层级格式去除"
CATEGORY = "JSON数据处理"
DESC = "将JSON格式化为层级键值行展示，可快速转为赋值语句"

META = {
    "params": [
        {
            "name": "keep_quote",
            "type": "checkbox",
            "label": "保留引号",
            "default": True
        },
        {
            "name": "sep",
            "type": "input",
            "label": "替换冒号为（留空保留:）"
        }
    ]
}

def format_json(obj, indent, keep_quote, sep, lines):
    tab = "    " * indent
    colon = ":" if not sep else sep

    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f'"{k}"' if keep_quote else k

            if isinstance(v, (dict, list)):
                lines.append(f"{tab}{key}{colon}")
                format_json(v, indent + 1, keep_quote, sep, lines)
            else:
                val = json.dumps(v, ensure_ascii=False)
                if not keep_quote and isinstance(v, str):
                    val = v
                lines.append(f"{tab}{key}{colon} {val}")

    elif isinstance(obj, list):
        for item in obj:
            format_json(item, indent, keep_quote, sep, lines)

def split_json_blocks(text: str):
    """
    从文本中自动切分出多个 JSON 对象
    通过大括号配对实现，适配日志拼接场景
    """
    blocks = []
    brace = 0
    start = None

    for i, ch in enumerate(text):
        if ch == "{":
            if brace == 0:
                start = i
            brace += 1
        elif ch == "}":
            brace -= 1
            if brace == 0 and start is not None:
                blocks.append(text[start:i+1])
                start = None

    return blocks

def run(data: str, config: dict) -> str:
    keep_quote = config.get("keep_quote", True)
    sep = config.get("sep", "")

    json_blocks = split_json_blocks(data)

    if not json_blocks:
        return "未检测到JSON数据"

    all_lines = []

    for block in json_blocks:
        try:
            parsed = json.loads(block)
        except Exception:
            continue

        lines = []
        format_json(parsed, 0, keep_quote, sep, lines)
        all_lines.extend(lines)
        all_lines.append("")  # 多个JSON之间空行

    return "\n".join(all_lines)