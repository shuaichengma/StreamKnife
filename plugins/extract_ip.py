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
            "default": False
        },
        {
            "name": "ip_sort",
            "type": "checkbox",
            "label": "IP地址排序",
            "default": False
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


def ip_sort_key(ip_text: str) -> tuple:
    """IP 排序键：按四段整数元组升序排列。"""
    return tuple(int(part) for part in ip_text.split("."))


def run(data: str, config: dict) -> str:
    dedupe = config.get("dedupe", True)
    clean_tail = config.get("clean_tail", True)
    extract_ports = config.get("extract_ports", False)
    sort_ips = config.get("ip_sort", False)

    # 记录每一次匹配，未勾选“结果去重”时据此保留重复项
    occurrences = []

    for match in IP_PATTERN.finditer(data):
        ip_text = match.group("ip")

        if clean_tail:
            ip_text = clean_tail_chars(ip_text + match.group("tail"))

        try:
            ip_text = str(ipaddress.IPv4Address(ip_text))
        except ipaddress.AddressValueError:
            continue

        port_text = None

        if extract_ports and match.group("port") is not None:
            port = int(match.group("port"))

            if 0 <= port <= 65535:
                port_text = str(port)

        occurrences.append((ip_text, port_text))

    # 仅提取 IP 时直接逐行输出地址，避免生成 ``IP：`` 前缀和空行。
    if not extract_ports:
        results = [ip_text for ip_text, _ in occurrences]

        if dedupe:
            results = list(dict.fromkeys(results))

        if sort_ips:
            results.sort(key=ip_sort_key)

        return "\n".join(results)

    if dedupe:
        # 按 IP 分组，端口去重，保持首次出现顺序
        grouped = {}

        for ip_text, port_text in occurrences:
            ports = grouped.setdefault(ip_text, [])

            if port_text is not None and port_text not in ports:
                ports.append(port_text)

        blocks = list(grouped.items())
    else:
        # 不去重：每次出现各输出一个 IP 块，保留重复地址和端口
        blocks = [
            (ip_text, [port_text] if port_text is not None else [])
            for ip_text, port_text in occurrences
        ]

    if sort_ips:
        blocks.sort(key=lambda item: ip_sort_key(item[0]))

    lines = []

    for index, (ip_text, ports) in enumerate(blocks):
        if index:
            lines.append("")

        lines.append(f"IP：{ip_text}")
        lines.extend(ports)

    return "\n".join(lines)
