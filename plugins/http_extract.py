import re

NAME = "提取网络服务路径"
CATEGORY = "网络数据"
DESC = "从杂乱文本中提取 HTTP/HTTPS/FTP/MySQL/Redis 等网络服务地址，以及不带协议头的 主机:端口/路径"

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

# 主机部分：宽松匹配四段数字（兼容 1227.0.0.1 这类异常写法）、域名或 localhost
_HOST_PATTERN = (
    r"(?:\d{1,4}(?:\.\d{1,4}){3}"
    r"|(?:[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}"
    r"|localhost)"
)

SERVICE_PATTERN = re.compile(
    # 带协议头的地址：http/https/ftp/mysql/redis 等任意协议
    r"(?<![A-Za-z0-9+.\-])[A-Za-z][A-Za-z0-9+.\-]*://[^\s\"'<>)\]]+"
    # 无协议头的 主机[:端口]/路径
    r"|(?<![A-Za-z0-9._\-/@])(?:" + _HOST_PATTERN + r")(?::\d{1,5})?/[^\s\"'<>)\]]*"
    # 无协议头的 主机:端口
    r"|(?<![A-Za-z0-9._\-/@])(?:" + _HOST_PATTERN + r"):\d{1,5}(?![\w/])",
    re.IGNORECASE,
)

# 逗号/分号后重新出现完整服务地址时，视为一条新的路径
_SERVICE_START_PATTERN = re.compile(
    r"(?:[A-Za-z][A-Za-z0-9+.\-]*://"
    r"|(?:" + _HOST_PATTERN + r")(?::\d{1,5})?(?:/|$))",
    re.IGNORECASE,
)


def clean_tail_chars(url: str) -> str:
    # 常见脏结尾符号
    return url.rstrip('\'\"),.;]}>`')


def strip_scheme(url: str) -> str:
    return re.sub(r"^[A-Za-z][A-Za-z0-9+.\-]*://", "", url)


def split_services(token: str) -> list:
    """把逗号/分号分隔的多条服务地址拆开，避免误切查询参数中的逗号。"""
    parts = []
    start = 0

    for separator in re.finditer(r"[,;]", token):
        if not _SERVICE_START_PATTERN.match(token[separator.end():]):
            continue

        parts.append(token[start:separator.start()])
        start = separator.end()

    parts.append(token[start:])

    return [part for part in parts if part]


def run(data: str, config: dict) -> str:
    dedupe = config.get("dedupe", True)
    clean_tail = config.get("clean_tail", True)
    strip = config.get("strip_scheme", False)

    results = []

    for token in SERVICE_PATTERN.findall(data):
        for part in split_services(token):
            if clean_tail:
                part = clean_tail_chars(part)

            if not part:
                continue

            if strip:
                part = strip_scheme(part)

            results.append(part)

    if dedupe:
        results = list(dict.fromkeys(results))

    return "\n".join(results)
