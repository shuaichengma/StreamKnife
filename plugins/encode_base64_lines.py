import base64

NAME = "逐行Base64编码"
CATEGORY = "编码处理"
DESC = "将输入内容逐行进行标准Base64编码，结果逐行输出"


def run(data: str, config: dict) -> str:
    result = []

    for line in data.splitlines():
        try:
            encoded = base64.b64encode(line.encode("utf-8")).decode("ascii")
            result.append(encoded)
        except Exception:
            result.append(line)

    return "\n".join(result)
