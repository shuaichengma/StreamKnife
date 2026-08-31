import itertools
import re

NAME = "生成区间数"
CATEGORY = "内容生成"
DESC = "展开数字区间，并保留区间之外的原始格式"

META = {"params": []}

_RANGE_PATTERN = re.compile(r"(\d+)\s*-\s*(\d+)")


def _expand_range(start_text: str, end_text: str) -> list[str]:
    start = int(start_text)
    end = int(end_text)
    step = 1 if start <= end else -1

    # 输入包含前导零时保留数字宽度，如 001-003。
    padded = (
        (len(start_text) > 1 and start_text.startswith("0"))
        or (len(end_text) > 1 and end_text.startswith("0"))
    )
    width = max(len(start_text), len(end_text)) if padded else 0

    return [
        str(value).zfill(width) if width else str(value)
        for value in range(start, end + step, step)
    ]


def _expand_expression(expression: str) -> list[str]:
    parts: list[list[str]] = []
    position = 0

    for match in _RANGE_PATTERN.finditer(expression):
        if match.start() > position:
            parts.append([expression[position:match.start()]])
        parts.append(_expand_range(match.group(1), match.group(2)))
        position = match.end()

    if not parts:
        raise ValueError("未找到有效区间，请使用“起始值-结束值”格式")

    if position < len(expression):
        parts.append([expression[position:]])

    return ["".join(values) for values in itertools.product(*parts)]


def run(data: str, config: dict) -> str:
    expressions = [line.strip() for line in data.splitlines() if line.strip()]
    if not expressions:
        return "[错误] 请输入需要生成的区间，例如：1-10"

    results: list[str] = []
    for line_number, expression in enumerate(expressions, start=1):
        try:
            results.extend(_expand_expression(expression))
        except ValueError as exc:
            return f"[错误] 第 {line_number} 行：{exc}"

    return "\n".join(results)
