NAME = "字符串去重"
CATEGORY = "文本处理"
DESC = "按行去重或按空格分词去重，保留首次出现、保持原始顺序"

META = {
    "params": [
        {
            "name": "mode",
            "type": "radio",
            "label": "去重模式",
            "options": ["按行去重", "按词去重"],
            "default": "按行去重"
        }
    ]
}


def run(data: str, config: dict) -> str:
    mode = config.get("mode", "按行去重")

    if mode == "按词去重":
        tokens = data.split()
        seen = set()
        result = []
        for token in tokens:
            if token not in seen:
                seen.add(token)
                result.append(token)
        return " ".join(result)

    # 按行去重
    lines = data.splitlines()
    seen = set()
    result = []
    for line in lines:
        clean = line.strip()
        if clean not in seen:
            seen.add(clean)
            result.append(clean)

    return "\n".join(result)
