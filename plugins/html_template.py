NAME = "生成HTML模板"
CATEGORY = "文件制作"
DESC = "生成标准HTML5模板并将内容包裹到body标签中"

META = {
    "params": [
        {
            "name": "title",
            "type": "input",
            "label": "网页标题(title)"
        }
    ]
}


def run(data: str, config: dict) -> str:
    title = config.get("title", "").strip()

    if not title:
        title = "Document"

    body_content = []

    for line in data.splitlines():
        line = line.strip()

        if not line:
            continue

        body_content.append(f"    {line}")

    body_html = "\n".join(body_content)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
</head>
<body>
{body_html}
</body>
</html>"""

    return html