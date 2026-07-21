import re

NAME = "提取HTTP/HTTPS路径"
CATEGORY = "网络数据"
DESC = "从杂乱文本中提取URL，并支持去重/清洗/去协议"

META = {
    "params": [
        {
            "name": "dedupe",
            "type": "checkbox",
            "label": "结果去重",
            "default": True
        },
        {
            "name": "clean_tail",
            "type": "checkbox",
            "label": "去除尾部脏字符",
            "default": True
        },
        {
            "name": "strip_scheme",
            "type": "checkbox",
            "label": "去掉协议，仅保留路径",
            "default": False
        }
    ]
}


URL_PATTERN = re.compile(
    r"https?://[^\s\"\'<>\)\]]+",
    re.IGNORECASE
)


def clean_tail_chars(url: str) -> str:
    # 常见脏结尾符号
    return url.rstrip('\'\"),.;]}>`')


def strip_scheme(url: str) -> str:
    return re.sub(r"^https?://", "", url, flags=re.IGNORECASE)


def run(data: str, config: dict) -> str:
    dedupe = config.get("dedupe", True)
    clean_tail = config.get("clean_tail", True)
    strip = config.get("strip_scheme", False)

    urls = URL_PATTERN.findall(data)

    results = []

    for u in urls:
        if clean_tail:
            u = clean_tail_chars(u)

        if strip:
            u = strip_scheme(u)

        results.append(u)

    if dedupe:
        results = list(dict.fromkeys(results))

    return "\n".join(results)