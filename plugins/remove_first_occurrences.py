NAME = "去除前X次出现的字符"
CATEGORY = "文本处理"
DESC = '去除前x次出现的字符y（当x为2,y为"时，"role" =  "user" -> role =  "user"）'

META = {
    "params": [
        {
            "name": "count",
            "type": "input",
            "label": "去除前几次（X）",
            "placeholder": "请输入大于 0 的整数"
        },
        {
            "name": "target",
            "type": "input",
            "label": "需要去除的字符（Y）"
        }
    ]
}


def run(data: str, config: dict) -> str:
    target = config.get("target", "")

    if not target:
        return data

    try:
        count = int(config.get("count", ""))
    except (TypeError, ValueError):
        return "[错误] 去除次数必须是大于 0 的整数"

    if count <= 0:
        return "[错误] 去除次数必须是大于 0 的整数"

    return data.replace(target, "", count)
