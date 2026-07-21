import struct

NAME = "数值转换IEEE754内存编码"
CATEGORY = "编码处理"
DESC = "将输入的数转为内存编码IEEE754的表现形式"

def run(data: str, config: dict = None) -> str:
    try:
        num = float(data)
    except ValueError:
        return "输入不是有效浮点数"

    packed = struct.pack('<f', num)  # 小端序
    hex_num = '0x' + ''.join(f'{i:02x}' for i in packed[::-1])  # 大端序

    return hex_num