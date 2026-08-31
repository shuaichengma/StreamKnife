import re

NAME = "字符替换"
CATEGORY = "文本处理"
DESC = "支持普通替换、逐项集合替换和整体替换"

META = {
    "params": [
        {
            "name": "mode",
            "type": "radio",
            "label": "匹配模式",
            "options": ["普通替换", "集合替换", "整体替换"],
            "default": "普通替换"
        },
        {
            "name": "old",
            "type": "input",
            "label": "匹配内容"
        },
        {
            "name": "new",
            "type": "input",
            "label": "替换为"
        },
        {
            "name": "case_sensitive",
            "type": "checkbox",
            "label": "区分大小写",
            "default": True
        }
    ]
}


def _match_line(line: str, targets: list[str], case_sensitive: bool) -> bool:
    """检查整行内容是否与任意一个匹配项完全相同。

    集合替换逐项按整行匹配，避免匹配项 ``192.168.252.181`` 误命中
    ``192.168.252.1812`` 这类仅包含该字符串的内容。
    """
    line = line.strip()
    if case_sensitive:
        return line in targets
    line_lower = line.lower()
    return any(line_lower == t.lower() for t in targets)


def run(data: str, config: dict) -> str:
    mode = config.get("mode", "普通替换")
    old = config.get("old", "")
    new = config.get("new", "")
    case_sensitive = config.get("case_sensitive", True)

    if not data:
        return data

    if not old:
        return data

    # 普通替换与整体替换都把匹配内容视为一个完整字符串。整体替换用于
    # 明确处理多行内容，同时保留普通替换的既有配置兼容性。
    if mode in ("普通替换", "整体替换"):
        if case_sensitive:
            return data.replace(old, new)

        pattern = re.compile(re.escape(old), re.IGNORECASE)
        return pattern.sub(new, data)

    # 集合替换：空格、制表符或换行用于分隔集合中的独立匹配项。
    # 每一项分别与用户输入中的每一行进行完整比对。
    targets = re.split(r"\s+", old.strip())
    if not targets:
        return data

    # 保留未匹配行原有的换行符及末尾换行；替换为空时移除整行。
    return "".join(
        (new + ending if new else "")
        if _match_line(line, targets, case_sensitive)
        else line + ending
        for line, ending in re.findall(r"(.*?)(\r\n|\n|\r|$)", data)
        if line or ending
    )
