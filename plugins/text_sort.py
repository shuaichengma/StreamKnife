NAME = "文本排序"
CATEGORY = "文本处理"
DESC = "按字典序或数值大小对文本行排序，支持升序/降序；字符串模式支持按字符或按空格分词排序"

META = {
    "params": [
        {
            "name": "mode",
            "type": "radio",
            "label": "排序模式",
            "options": ["字符串排序", "数值排序"],
            "default": "字符串排序"
        },
        {
            "name": "order",
            "type": "radio",
            "label": "排序方向",
            "options": ["升序", "降序"],
            "default": "升序"
        },
        {
            "name": "sort_by_word",
            "type": "checkbox",
            "label": "按词排序",
            "default": False,
            "visible_when": {
                "param": "mode",
                "equals": "字符串排序"
            }
        }
    ]
}


def _is_number(s: str) -> bool:
    """判断字符串是否为有效数值（整数或浮点数）"""
    try:
        float(s)
        return True
    except ValueError:
        return False


def _try_number(s: str):
    """尝试将字符串转为数字用于比较，失败返回原字符串"""
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return s


def _sort_key(item, numeric: bool):
    if numeric:
        return _try_number(item)
    return item.lower() if isinstance(item, str) else item


def run(data: str, config: dict) -> str:
    mode = config.get("mode", "字符串排序")
    order = config.get("order", "升序")
    sort_by_word = config.get("sort_by_word", False)

    numeric = (mode == "数值排序")
    reverse = (order == "降序")
    lines = data.splitlines()

    # 数值模式：先校验所有 token 均为合法数值
    if numeric:
        invalid = []
        for line in lines:
            for token in line.split():
                if not _is_number(token):
                    invalid.append(token)

        if invalid:
            shown = invalid[:10]
            suffix = f" ... 等共 {len(invalid)} 项" if len(invalid) > 10 else ""
            return (
                f"[错误] 数值排序模式下不允许包含非数值内容，"
                f"检测到以下无效项：\n"
                + "\n".join(shown)
                + suffix
            )

    processed = []
    for line in lines:
        # 数值模式始终按空格分词，避免字符级排序把 "10" 拆成 "01"
        if numeric or sort_by_word:
            words = line.split()
            words.sort(key=lambda w: _sort_key(w, numeric), reverse=reverse)
            processed.append(" ".join(words))
        else:
            chars = sorted(line, key=lambda c: _sort_key(c, numeric), reverse=reverse)
            processed.append("".join(chars))

    processed.sort(key=lambda s: _sort_key(s.strip(), numeric), reverse=reverse)

    return "\n".join(processed)
