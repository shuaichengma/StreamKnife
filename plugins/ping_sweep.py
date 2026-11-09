import ipaddress
import locale
import platform
import re
import shutil
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

NAME = "内网主机探活"
CATEGORY = "运维管理"
DESC = "批量 Ping 测试主机存活，支持单个 IP、CIDR（如 192.168.10.0/24）和范围（如 192.168.10.1-200），多网卡可指定源地址"

MAX_HOSTS = 65536
MAX_WORKERS = 256
IF_TYPE_SOFTWARE_LOOPBACK = 24
LATENCY_PATTERN = re.compile(r"([=<])\s*(\d+(?:\.\d+)?)\s*ms", re.IGNORECASE)


def _windows_ipv4_adapters() -> list:
    """通过 GetAdaptersInfo 枚举本机网卡的 IPv4 地址，返回 [(网卡名称, IP), ...]。"""
    import ctypes
    from ctypes import wintypes

    class IP_ADDR_STRING(ctypes.Structure):
        pass

    IP_ADDR_STRING._fields_ = [
        ("Next", ctypes.POINTER(IP_ADDR_STRING)),
        ("IpAddress", ctypes.c_char * 16),
        ("IpMask", ctypes.c_char * 16),
        ("Context", wintypes.DWORD),
    ]

    class IP_ADAPTER_INFO(ctypes.Structure):
        pass

    IP_ADAPTER_INFO._fields_ = [
        ("Next", ctypes.POINTER(IP_ADAPTER_INFO)),
        ("ComboIndex", wintypes.DWORD),
        ("AdapterName", ctypes.c_char * 260),
        ("Description", ctypes.c_char * 132),
        ("AddressLength", wintypes.UINT),
        ("Address", ctypes.c_ubyte * 8),
        ("Index", wintypes.DWORD),
        ("Type", wintypes.UINT),
        ("DhcpEnabled", wintypes.UINT),
        ("CurrentIpAddress", ctypes.POINTER(IP_ADDR_STRING)),
        ("IpAddressList", IP_ADDR_STRING),
        ("GatewayList", IP_ADDR_STRING),
        ("DhcpServer", IP_ADDR_STRING),
        ("HaveWlanSupport", wintypes.BOOL),
    ]

    size = wintypes.ULONG(0)
    ctypes.windll.iphlpapi.GetAdaptersInfo(None, ctypes.byref(size))

    if size.value == 0:
        return []

    buffer = ctypes.create_string_buffer(size.value)
    adapters_ptr = ctypes.cast(buffer, ctypes.POINTER(IP_ADAPTER_INFO))

    if ctypes.windll.iphlpapi.GetAdaptersInfo(adapters_ptr, ctypes.byref(size)) != 0:
        return []

    adapters = []
    current = adapters_ptr

    while current:
        info = current.contents
        name = info.Description.decode("mbcs", errors="ignore").strip()

        if info.Type != IF_TYPE_SOFTWARE_LOOPBACK:
            entry_ptr = ctypes.pointer(info.IpAddressList)

            while entry_ptr:
                ip = entry_ptr.contents.IpAddress.decode("ascii", errors="ignore").strip()

                if ip and ip != "0.0.0.0" and not ip.startswith("127.") and not ip.startswith("169.254."):
                    adapters.append((name, ip))

                entry_ptr = entry_ptr.contents.Next

        current = info.Next

    return adapters


def _local_ipv4_addresses() -> list:
    if platform.system().lower() == "windows":
        try:
            return _windows_ipv4_adapters()
        except Exception:
            pass

    addresses = []

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.append(("", info[4][0]))
    except OSError:
        pass

    return addresses


def get_source_options() -> list:
    """供下拉框使用的源地址选项。"""
    options = [("自动（系统默认）", "")]
    seen = {""}

    for name, ip in _local_ipv4_addresses():
        if ip in seen:
            continue

        seen.add(ip)
        options.append((f"{ip}（{name}）" if name else ip, ip))

    return options


META = {
    "params": [
        {
            "name": "source_ip",
            "type": "select",
            "label": "源地址（多网卡时选择网卡）",
            "options": get_source_options,
            "default": ""
        },
        {
            "name": "timeout",
            "type": "input",
            "label": "单机超时（毫秒）",
            "placeholder": "默认 800，范围 100-10000"
        },
        {
            "name": "count",
            "type": "input",
            "label": "探测次数",
            "placeholder": "默认 1，范围 1-5"
        },
        {
            "name": "workers",
            "type": "input",
            "label": "并发数",
            "placeholder": "默认 128，范围 1-256"
        },
        {
            "name": "alive_only",
            "type": "checkbox",
            "label": "仅显示存活主机",
            "default": False
        },
        {
            "name": "show_latency",
            "type": "checkbox",
            "label": "显示延迟",
            "default": True
        }
    ]
}


def _config_int(config: dict, name: str, default: int, minimum: int, maximum: int) -> int:
    raw = str(config.get(name, "") or "").strip()

    if not raw:
        return default

    try:
        value = int(raw)
    except ValueError:
        return default

    return max(minimum, min(maximum, value))


def _expand_line(line: str) -> list:
    """把一行输入展开为 IPv4 地址列表。"""
    if "/" in line:
        try:
            network = ipaddress.ip_network(line, strict=False)
        except ValueError:
            raise ValueError("无效的 IP 网段")

        if network.version != 4:
            raise ValueError("仅支持 IPv4")

        if network.num_addresses > MAX_HOSTS:
            raise ValueError(f"单个网段超过 {MAX_HOSTS} 个地址")

        return [str(host) for host in network.hosts()]

    if "-" in line:
        start_text, _, end_text = line.partition("-")
        start_text = start_text.strip()
        end_text = end_text.strip()

        try:
            start_ip = ipaddress.IPv4Address(start_text)
        except ipaddress.AddressValueError:
            raise ValueError("范围起始地址无效")

        if not end_text:
            raise ValueError("范围缺少结束地址")

        if end_text.isdigit():
            last_octet = int(end_text)

            if not 0 <= last_octet <= 255:
                raise ValueError("范围结束地址无效")

            prefix = str(start_ip).rsplit(".", 1)[0]
            end_ip = ipaddress.IPv4Address(f"{prefix}.{last_octet}")
        else:
            try:
                end_ip = ipaddress.IPv4Address(end_text)
            except ipaddress.AddressValueError:
                raise ValueError("范围结束地址无效")

        start = int(start_ip)
        end = int(end_ip)

        if end < start:
            raise ValueError("结束地址小于起始地址")

        if end - start + 1 > MAX_HOSTS:
            raise ValueError(f"单个范围超过 {MAX_HOSTS} 个地址")

        return [str(ipaddress.IPv4Address(value)) for value in range(start, end + 1)]

    try:
        return [str(ipaddress.IPv4Address(line))]
    except ipaddress.AddressValueError:
        raise ValueError("不是有效的 IPv4 地址、CIDR 或地址范围")


def _parse_targets(data: str):
    """解析每行一个的 IP / CIDR / 范围，返回去重后的目标列表和错误信息。"""
    targets = []
    seen = set()
    errors = []

    for line_no, raw in enumerate(data.splitlines(), 1):
        line = raw.strip()

        if not line or line.startswith("#"):
            continue

        try:
            expanded = _expand_line(line)
        except ValueError as exc:
            errors.append(f"第 {line_no} 行：{exc}（{line}）")
            continue

        for ip in expanded:
            if ip in seen:
                continue

            seen.add(ip)
            targets.append(ip)

        if len(targets) > MAX_HOSTS:
            raise ValueError(f"目标总数超过上限 {MAX_HOSTS}，请拆分后分批探测")

    return targets, errors


def _ping_command(ip: str, timeout_ms: int, count: int, source_ip: str) -> list:
    system = platform.system().lower()
    source = ["-S", source_ip] if source_ip else []

    if system == "windows":
        return ["ping", "-n", str(count), "-w", str(timeout_ms)] + source + [ip]

    if system == "darwin":
        return ["ping", "-c", str(count), "-W", str(timeout_ms)] + source + [ip]

    # Linux 下 -W 的单位是秒，指定源地址使用 -I
    source = ["-I", source_ip] if source_ip else []
    return ["ping", "-c", str(count), "-W", str(max(1, (timeout_ms + 999) // 1000))] + source + [ip]


def _decode_output(raw: bytes) -> str:
    if not raw:
        return ""

    encoding = locale.getpreferredencoding(False) or "utf-8"

    try:
        return raw.decode(encoding, errors="ignore")
    except LookupError:
        return raw.decode("utf-8", errors="ignore")


def _ping(ip: str, timeout_ms: int, count: int, source_ip: str):
    """对单个地址执行 Ping，返回 (是否存活, 延迟文本)。"""
    kwargs = {}

    if platform.system().lower() == "windows":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    try:
        completed = subprocess.run(
            _ping_command(ip, timeout_ms, count, source_ip),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout_ms * count / 1000 + 3,
            **kwargs,
        )
    except (OSError, subprocess.SubprocessError):
        return False, None

    output = _decode_output(completed.stdout or b"")

    # 以 TTL 回显判断真实存活，避免部分系统在“目标不可达”时仍返回 0
    if completed.returncode != 0 or "ttl=" not in output.lower():
        return False, None

    match = LATENCY_PATTERN.search(output)

    if not match:
        return True, None

    return True, f"{match.group(1)}{match.group(2)}"


def run(data: str, config: dict) -> str:
    if not shutil.which("ping"):
        return "错误：未找到系统 ping 命令，无法执行主机探活。"

    timeout_ms = _config_int(config, "timeout", 800, 100, 10000)
    count = _config_int(config, "count", 1, 1, 5)
    workers = _config_int(config, "workers", 128, 1, MAX_WORKERS)
    alive_only = config.get("alive_only", False)
    show_latency = config.get("show_latency", True)
    source_ip = str(config.get("source_ip", "") or "").strip()

    if source_ip:
        try:
            source_ip = str(ipaddress.IPv4Address(source_ip))
        except ipaddress.AddressValueError:
            return f"错误：源地址 {source_ip} 不是有效的 IPv4 地址。"

    try:
        targets, parse_errors = _parse_targets(data)
    except ValueError as exc:
        return f"错误：{exc}"

    if not targets:
        if parse_errors:
            return "输入错误：\n" + "\n".join("  " + error for error in parse_errors)

        return (
            "请输入要探测的 IP 地址或范围，每行一个：\n"
            "  单个 IP：192.168.10.1\n"
            "  IP 网段：192.168.10.0/24\n"
            "  IP 范围：192.168.10.1-200"
        )

    started = time.monotonic()

    with ThreadPoolExecutor(max_workers=min(workers, len(targets))) as executor:
        results = list(
            executor.map(lambda ip: _ping(ip, timeout_ms, count, source_ip), targets)
        )

    elapsed = time.monotonic() - started

    lines = []

    if parse_errors:
        lines.append("输入错误（已跳过）：")
        lines.extend("  " + error for error in parse_errors)
        lines.append("")

    alive_count = sum(1 for alive, _ in results if alive)

    for ip, (alive, latency) in zip(targets, results):
        if alive:
            suffix = f"  {latency}ms" if show_latency and latency else ""
            lines.append(f"[+] {ip}{suffix}")
        elif not alive_only:
            lines.append(f"[-] {ip}")

    lines.append("")
    lines.append(
        f"源地址 {source_ip or '自动'}｜共 {len(targets)} 个目标｜存活 {alive_count} 个｜"
        f"不可达 {len(targets) - alive_count} 个｜耗时 {elapsed:.1f} 秒"
    )

    return "\n".join(lines)
