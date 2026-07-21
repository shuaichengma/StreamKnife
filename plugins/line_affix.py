NAME = "为每行头尾添加字符串"
CATEGORY = "文本处理"
DESC = "在每行头尾添加字符串，支持单行统一或多行一一对应，{} 自动替换为当前行"

META = {
    "params": [
        {
            "name": "mode",
            "type": "radio",
            "label": "添加模式",
            "options": ["单行内容（统一）", "多行内容（一一对应）"],
            "default": "单行内容（统一）"
        },
        {
            "name": "prefix",
            "type": "input",
            "label": "头部添加字符串",
            "placeholder": "如: reverse-sourcemap （多行模式每行对应一条）",
            "multiline": True
        },
        {
            "name": "suffix",
            "type": "input",
            "label": "尾部添加字符串",
            "placeholder": "如:  -o {} （{} 代表当前行内容）",
            "multiline": True
        }
    ]
}


def _pick(items: list, index: int):
    """取列表第 index 项，越界则复用最后一项"""
    if not items:
        return ""
    if index < len(items):
        return items[index]
    return items[-1]


def run(data: str, config: dict) -> str:
    mode = config.get("mode", "单行内容（统一）")
    prefix_raw = config.get("prefix", "")
    suffix_raw = config.get("suffix", "")

    multi = (mode == "多行内容（一一对应）")

    prefixes = prefix_raw.splitlines() if multi and prefix_raw else []
    suffixes = suffix_raw.splitlines() if multi and suffix_raw else []

    result = []
    for i, line in enumerate(data.splitlines()):
        if multi:
            p = _pick(prefixes, i)
            s = _pick(suffixes, i)
        else:
            p = prefix_raw
            s = suffix_raw

        # {} 占位符替换为当前行内容
        p = p.replace("{}", line)
        s = s.replace("{}", line)

        result.append(f"{p}{line}{s}")

    return "\n".join(result)
