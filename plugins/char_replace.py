import re

NAME = "字符替换"
CATEGORY = "文本处理"
DESC = "将指定字符替换为另一个字符，或按集合匹配过滤行"

META = {
    "params": [
        {
            "name": "mode",
            "type": "radio",
            "label": "匹配模式",
            "options": ["普通替换", "集合过滤"],
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


def _match_line(line: str, targets: list, case_sensitive: bool) -> bool:
    """检查整行内容是否与任意一个匹配项完全相同。

    集合过滤按行匹配，避免匹配项 ``192.168.252.181`` 误命中
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

    # ---- 普通替换模式 ----
    if mode == "普通替换":
        if case_sensitive:
            return data.replace(old, new)

        pattern = re.compile(re.escape(old), re.IGNORECASE)
        return pattern.sub(new, data)

    # ---- 集合过滤模式 ----
    # 将匹配内容按行拆分为独立匹配项（去除空行和首尾空白）
    targets = [t.strip() for t in old.splitlines() if t.strip()]
    if not targets:
        return data

    result = []
    for line in data.splitlines():
        if _match_line(line, targets, case_sensitive):
            if new:
                # 替换为指定内容
                result.append(new)
            # 替换为空则移除该行
        else:
            result.append(line)

    return "\n".join(result)
