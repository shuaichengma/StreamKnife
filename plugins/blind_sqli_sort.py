import re

NAME = "盲注结果排序"
CATEGORY = "SQL注入"
DESC = "解析 BurpSuite Intruder 盲注爆破结果，自动识别 payload 列，按 payload1 排序后提取 payload2 并转为字符串"

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
        },
        {
            "name": "auto_col",
            "type": "checkbox",
            "label": "自动识别 payload 列（兼容不同复制格式）",
            "default": True
        }
    ]
}

_HEADER_PATTERN = re.compile(r"payload\s*(\d+)", re.IGNORECASE)


def _parse_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_rows(data: str) -> list:
    rows = []

    for raw in data.splitlines():
        line = raw.replace("\ufeff", "").rstrip("\r")

        if not line.strip():
            continue

        # Burp 复制结果默认用制表符分隔；按 \t 拆分可保留空列，避免列位置整体前移
        if "\t" in line:
            fields = [field.strip() for field in line.split("\t")]
        else:
            fields = line.split()

        rows.append(fields)

    return rows


def _find_header(rows):
    """识别带表头的复制结果，返回 (表头行号, payload1 列, payload2 列)。"""
    for row_index, fields in enumerate(rows):
        positions = {}

        for col, field in enumerate(fields):
            match = _HEADER_PATTERN.search(field)

            if match:
                positions[match.group(1)] = col

        if "1" in positions and "2" in positions and positions["1"] != positions["2"]:
            return row_index, positions["1"], positions["2"]

    return None


def _collect(rows, pos_col, val_col):
    entries = {}
    parsed = 0

    for fields in rows:
        if len(fields) <= pos_col or len(fields) <= val_col:
            continue

        pos = _parse_int(fields[pos_col])
        val = fields[val_col].strip()

        if pos is None or not val:
            continue

        parsed += 1

        if pos not in entries:
            entries[pos] = val

    return entries, parsed


def _decode_char(val, is_char):
    if is_char:
        return val

    code = _parse_int(val)

    if code is None:
        return f"[?{val}]"

    try:
        return chr(code)
    except (ValueError, OverflowError):
        return f"[?{val}]"


def _text_ratio(entries, is_char):
    values = [entries[pos] for pos in sorted(entries)]

    if not values:
        return 0.0

    good = 0.0

    for val in values:
        if is_char:
            good += 1.0 if val.isprintable() else 0.0
            continue

        code = _parse_int(val)

        if code is None:
            continue

        if 32 <= code <= 126 or code in (9, 10, 13):
            good += 1.0
        elif 0 <= code <= 255 and chr(code).isprintable():
            # 128-255 可能是 UTF-8 字节，按半有效计算
            good += 0.5

    ratio = good / len(values)

    # 整列为同一个值通常说明选错了列（真正的结果一般会变化）
    if len(values) > 2 and len(set(values)) == 1:
        ratio *= 0.3

    return ratio


def _quality(entries, parsed, total, is_char):
    """评估列选择的可靠程度：解析覆盖率 + 结果是可读文本的比例。"""
    if not entries:
        return -1.0

    coverage = parsed / total if total else 0.0
    return coverage * 2 + _text_ratio(entries, is_char) * 3


def _detect_columns(rows, is_char):
    """在列布局与预期不一致时，自动寻找 position/value 两列。"""
    total = len(rows)

    if total < 2:
        return None

    max_cols = min(max(len(fields) for fields in rows), 16)
    best = None
    best_non_monotonic = None

    for pos_col in range(max_cols):
        pos_values = []
        valid = True

        for fields in rows:
            if pos_col >= len(fields):
                valid = False
                break

            pos = _parse_int(fields[pos_col])

            if pos is None or pos < 0:
                valid = False
                break

            pos_values.append(pos)

        if not valid or len(set(pos_values)) < 2:
            continue

        span = max(pos_values) - min(pos_values) + 1
        density = len(set(pos_values)) / span if span else 0.0
        smallness = 1.0 / (1.0 + max(pos_values) / 100.0)

        for val_col in range(max_cols):
            if val_col == pos_col:
                continue

            entries, parsed = _collect(rows, pos_col, val_col)

            if not entries or parsed < total * 0.6:
                continue

            quality = _quality(entries, parsed, total, is_char)

            if quality < 0:
                continue

            ordered_values = [entries[pos] for pos in sorted(entries)]
            ordered_ints = [_parse_int(value) for value in ordered_values]
            monotonic = (
                len(ordered_ints) > 2
                and all(value is not None for value in ordered_ints)
                and all(
                    ordered_ints[i] <= ordered_ints[i + 1]
                    for i in range(len(ordered_ints) - 1)
                )
            )

            score = quality + density + smallness
            score += 0.5 if val_col == pos_col + 1 else 0.0
            score -= 1.5 if monotonic else 0.0

            if best is None or score > best[0]:
                best = (score, pos_col, val_col, monotonic)

            # 值列随位置单调递增通常说明选到了另一个序号列（如 # -> payload1）
            if not monotonic and (
                best_non_monotonic is None or score > best_non_monotonic[0]
            ):
                best_non_monotonic = (score, pos_col, val_col, monotonic)

    chosen = best_non_monotonic or best

    return (chosen[1], chosen[2], chosen[3]) if chosen else None


def run(data: str, config: dict) -> str:
    pos_col_str = str(config.get("pos_col", "") or "").strip()
    val_col_str = str(config.get("val_col", "") or "").strip()
    is_char = config.get("is_char", False)
    auto_col = config.get("auto_col", True)

    # 解析列号
    try:
        pos_col = int(pos_col_str) - 1 if pos_col_str else 1
        val_col = int(val_col_str) - 1 if val_col_str else 2
    except ValueError:
        return "[错误] 列号必须为整数"

    if pos_col < 0 or val_col < 0:
        return "[错误] 列号必须大于 0"

    rows = _parse_rows(data)

    if not rows:
        return "[提示] 未解析到有效数据，请检查输入格式"

    header = _find_header(rows)

    if header:
        header_index, header_pos, header_val = header
        rows = rows[:header_index] + rows[header_index + 1:]
        pos_col, val_col = header_pos, header_val
    elif auto_col and not pos_col_str and not val_col_str:
        total = len(rows)
        entries, parsed = _collect(rows, pos_col, val_col)
        quality = _quality(entries, parsed, total, is_char)

        # 列位置对不上时（常见于 Burp 少复制/多复制了首列），自动重新定位
        if quality < 4.2:
            detected = _detect_columns(rows, is_char)

            if detected:
                detected_pos, detected_val, monotonic = detected
                detected_entries, detected_parsed = _collect(
                    rows, detected_pos, detected_val
                )
                detected_quality = _quality(
                    detected_entries, detected_parsed, total, is_char
                )

                if (
                    not monotonic
                    and detected_quality >= 4.0
                    and detected_quality > quality + 0.5
                ):
                    pos_col, val_col = detected_pos, detected_val

    entries, _ = _collect(rows, pos_col, val_col)

    if not entries:
        return (
            "[提示] 未解析到有效数据，请确认输入中包含 payload1/payload2 两列，"
            "或手动填写列号（默认第 2、3 列）"
        )

    # 按位置排序，拼接结果
    sorted_positions = sorted(entries.keys())
    result_parts = []

    for pos in sorted_positions:
        result_parts.append(_decode_char(entries[pos], is_char))

    return "".join(result_parts)
