import csv
import io

NAME = "制作CSV"
CATEGORY = "文件制作"
DESC = "按指定行列数将空格分隔的文本转换为CSV，第一行为列名"

META = {
    "params": [
        {
            "name": "row_count",
            "type": "input",
            "label": "数据行数（不含第一行列名）",
            "placeholder": "请输入大于或等于 0 的整数"
        },
        {
            "name": "column_count",
            "type": "input",
            "label": "列数",
            "placeholder": "请输入大于 0 的整数"
        }
    ]
}


def normalize_row(values: list[str], column_count: int) -> list[str]:
    values = values[:column_count]
    return values + ["null"] * (column_count - len(values))


def run(data: str, config: dict) -> str:
    try:
        row_count = int(config.get("row_count", ""))
        column_count = int(config.get("column_count", ""))
    except (TypeError, ValueError):
        return "[错误] 行数和列数必须是整数"

    if row_count < 0:
        return "[错误] 数据行数必须是大于或等于 0 的整数"

    if column_count <= 0:
        return "[错误] 列数必须是大于 0 的整数"

    input_lines = data.splitlines()
    header_values = input_lines[0].split() if input_lines else []
    data_lines = input_lines[1:]

    rows = [normalize_row(header_values, column_count)]

    for index in range(row_count):
        values = data_lines[index].split() if index < len(data_lines) else []
        rows.append(normalize_row(values, column_count))

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(rows)
    return output.getvalue().rstrip("\n")
