import ipaddress
import re

NAME = "提取IP地址"
CATEGORY = "网络数据"
DESC = "从杂乱文本中提取IPv4地址，支持结果去重、尾部清洗和端口号提取"

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
            "label": "去除尾部脏数据",
            "default": True
        },
        {
            "name": "extract_ports",
            "type": "checkbox",
            "label": "提取端口号",
            "default": True
        }
    ]
}


IP_PATTERN = re.compile(
    r"(?<![\d.])"
    r"(?P<ip>(?:\d{1,3}\.){3}\d{1,3})"
    r"(?::(?P<port>\d{1,5}))?"
    r"(?P<tail>['\"),.;\]}>`]*)"
    r"(?![\d.])"
)


def clean_tail_chars(value: str) -> str:
    return value.rstrip("'\"),.;]}>`")


def run(data: str, config: dict) -> str:
    dedupe = config.get("dedupe", True)
    clean_tail = config.get("clean_tail", True)
    extract_ports = config.get("extract_ports", True)

    addresses = {}

    for match in IP_PATTERN.finditer(data):
        ip_text = match.group("ip")

        if clean_tail:
            ip_text = clean_tail_chars(ip_text + match.group("tail"))

        try:
            ip_text = str(ipaddress.IPv4Address(ip_text))
        except ipaddress.AddressValueError:
            continue

        if ip_text not in addresses:
            addresses[ip_text] = []

        if not extract_ports or match.group("port") is None:
            continue

        port = int(match.group("port"))

        if not 0 <= port <= 65535:
            continue

        port_text = str(port)

        if not dedupe or port_text not in addresses[ip_text]:
            addresses[ip_text].append(port_text)

    lines = []

    for index, (ip_text, ports) in enumerate(addresses.items()):
        if index:
            lines.append("")

        lines.append(f"IP：{ip_text}")
        lines.extend(ports)

    return "\n".join(lines)
