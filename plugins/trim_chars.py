NAME = "去除行首尾无用字符"
CATEGORY = "文本处理"
DESC = "去除每一行开头和结尾的指定字符，留空则默认去除空格"

META = {
    "params": [
        {
            "name": "chars",
            "type": "input",
            "label": "需要去除的字符",
            "placeholder": "如: @#$ 或空格+逗号等，留空默认去除空格"
        }
    ]
}


def run(data: str, config: dict) -> str:
    chars = config.get("chars", "")

    if not chars:
        chars = " "

    result = []
    for line in data.splitlines():
        result.append(line.strip(chars))

    return "\n".join(result)
