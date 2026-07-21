NAME = "盲注结果排序"
CATEGORY = "SQL注入"
DESC = "解析 BurpSuite Intruder 盲注爆破结果，按 payload1 排序后提取 payload2 并转为字符串"

META = {
    "params": [
        {
            "name": "pos_col",
            "type": "input",
            "label": "payload1（位置）所在列",
            "placeholder": "默认第 2 列"
        },
        {
            "name": "val_col",
            "type": "input",
            "label": "payload2（ASCII/字符值）所在列",
            "placeholder": "默认第 3 列"
        },
        {
            "name": "is_char",
            "type": "checkbox",
            "label": "payload2 已是字符（勾选=直接拼接，不勾选=ASCII转字符）",
            "default": False
        }
    ]
}


def run(data: str, config: dict) -> str:
    pos_col_str = config.get("pos_col", "2").strip()
    val_col_str = config.get("val_col", "3").strip()
    is_char = config.get("is_char", False)

    # 解析列号
    try:
        pos_col = int(pos_col_str) - 1 if pos_col_str else 1
        val_col = int(val_col_str) - 1 if val_col_str else 2
    except ValueError:
        return "[错误] 列号必须为整数"

    if pos_col < 0 or val_col < 0:
        return "[错误] 列号必须大于 0"

    # 解析每一行
    entries = {}  # position -> value
    for line in data.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = line.split()
        if len(parts) <= max(pos_col, val_col):
            continue

        try:
            pos = int(parts[pos_col].strip())
            val = parts[val_col].strip()
        except (ValueError, IndexError):
            continue

        if pos not in entries:
            entries[pos] = val

    if not entries:
        return "[提示] 未解析到有效数据，请检查列号及输入格式"

    # 按位置排序，拼接结果
    sorted_positions = sorted(entries.keys())
    result_parts = []
    for pos in sorted_positions:
        val = entries[pos]
        if not is_char:
            try:
                ch = chr(int(val))
            except (ValueError, TypeError):
                ch = f"[?{val}]"
        else:
            ch = val
        result_parts.append(ch)

    return "".join(result_parts)
