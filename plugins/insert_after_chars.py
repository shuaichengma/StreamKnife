NAME = "给每个字符后添加内容"
CATEGORY = "文本处理"
DESC = "在每个字符后或每隔指定数量的字符后添加自定义内容"

META = {
    "params": [
        {
            "name": "mode",
            "type": "radio",
            "label": "添加方式",
            "options": ["每个字符后添加", "每隔指定字符数添加"],
            "default": "每个字符后添加"
        },
        {
            "name": "interval",
            "type": "input",
            "label": "间隔字符数",
            "placeholder": "请输入大于 0 的整数",
            "visible_when": {
                "param": "mode",
                "equals": "每隔指定字符数添加"
            }
        },
        {
            "name": "content",
            "type": "input",
            "label": "需要添加的内容"
        }
    ]
}


def run(data: str, config: dict) -> str:
    content = config.get("content", "")

    if not data or not content:
        return data

    mode = config.get("mode", "每个字符后添加")

    if mode == "每个字符后添加":
        interval = 1
    else:
        try:
            interval = int(config.get("interval", ""))
        except (TypeError, ValueError):
            return "[错误] 间隔字符数必须是大于 0 的整数"

        if interval <= 0:
            return "[错误] 间隔字符数必须是大于 0 的整数"

    parts = []

    for index, char in enumerate(data, start=1):
        parts.append(char)

        if index % interval == 0:
            parts.append(content)

    return "".join(parts)
