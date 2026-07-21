NAME = "匹配裁剪"
CATEGORY = "文本处理"
DESC = "移除被指定字符成对包裹的内容（含包裹字符本身），支持指定剔除次数"

META = {
    "params": [
        {
            "name": "delimiter",
            "type": "input",
            "label": "包裹字符",
            "placeholder": "如: /"
        },
        {
            "name": "times",
            "type": "input",
            "label": "剔除次数",
            "placeholder": "正整数，默认 1 次（输入 0 表示全部剔除）"
        }
    ]
}


def _cut_once(data: str, delimiter: str) -> str:
    """剔除一对包裹内容，返回 (结果, 是否发生了剔除)"""
    first = data.find(delimiter)
    if first == -1:
        return data

    second = data.find(delimiter, first + 1)
    if second == -1:
        return data

    return data[:first] + data[second + 1:]


def run(data: str, config: dict) -> str:
    delimiter = config.get("delimiter", "")

    if not delimiter or len(delimiter) != 1:
        return "[错误] 包裹字符必须为单个字符，如 /"

    times_str = config.get("times", "1").strip()
    try:
        times = int(times_str) if times_str else 1
    except ValueError:
        return "[错误] 剔除次数必须为整数"

    # 检查是否存在至少一对
    first = data.find(delimiter)
    if first == -1:
        return data
    second = data.find(delimiter, first + 1)
    if second == -1:
        return data

    result = data
    count = 0
    max_rounds = times if times > 0 else float("inf")

    while count < max_rounds:
        prev = result
        result = _cut_once(result, delimiter)
        if result == prev:
            break
        count += 1

    return result
