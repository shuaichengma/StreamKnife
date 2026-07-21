import re

NAME = "HEX按字节格式化"
CATEGORY = "编码处理"
DESC = "将连续HEX字符串按2位分组，并转换为0x??格式输出"

def run(data: str) -> str:
    data = data.strip()

    # 提取纯hex字符（避免混入0x、空格等）
    hex_str = re.sub(r'[^0-9a-fA-F]', '', data)

    # 长度不足直接返回
    if len(hex_str) < 2:
        return ""

    # 如果是奇数长度，前面补0（避免断字节）
    if len(hex_str) % 2 != 0:
        hex_str = "0" + hex_str

    result = []

    for i in range(0, len(hex_str), 2):
        byte = hex_str[i:i+2]
        result.append(f"0x{byte.lower()}")

    return " ".join(result)