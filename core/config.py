"""StreamKnife 集中配置管理模块

配置文件: <程序目录>/config/settings.json
支持 // 行注释，写入时自动生成文档注释头。
"""

import json
import os
import sys

# ── 默认值 ──────────────────────────────────────────────
DEFAULTS = {
    "close_action": "ask",                 # "ask" | "quit" | "minimize"
    "save_path": "",                       # "" 表示使用 exe/脚本所在目录
    "window_width": 800,
    "window_height": 600,
}

# 写入时附在 JSON 之前的注释头
_COMMENT_HEADER = """// StreamKnife 配置文件
// 修改后重启程序生效
//
// close_action  : "ask" (每次询问) | "quit" (直接退出) | "minimize" (最小化到托盘)
// save_path     : 快速保存目录，留空则保存到程序所在目录
// window_width  : 默认窗口宽度 (像素)
// window_height : 默认窗口高度 (像素)
"""


def _get_config_dir() -> str:
    """可写的配置目录：exe 所在目录（frozen）或脚本工作目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(".")


class ConfigManager:
    """集中配置管理器。

    >>> c = ConfigManager()
    >>> c.get("close_action")
    'ask'
    >>> c.set("close_action", "minimize")
    >>> c.save()
    """

    def __init__(self):
        config_dir = _get_config_dir()
        self._filepath = os.path.join(config_dir, "config", "settings.json")
        self._data = {}
        self._load()

    # ── 读写 ──────────────────────────────────────────

    def _load(self):
        """从 JSON 文件读取配置，过滤 // 注释行"""
        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # 去掉行首 // 注释，保留有效 JSON 行
            clean = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("//") or not stripped:
                    continue
                clean.append(line)

            self._data = json.loads("".join(clean))
        except Exception:
            self._data = {}

    def save(self):
        """将当前配置持久化到文件（含注释头）"""
        os.makedirs(os.path.dirname(self._filepath), exist_ok=True)

        # 合并 DEFAULTS 中用户未设置的项，保证文件自描述
        out = {}
        for key in DEFAULTS:
            out[key] = self._data.get(key, DEFAULTS[key])
        # 同时保留用户设置的、不在 DEFAULTS 中的自定义键
        for key in self._data:
            if key not in out:
                out[key] = self._data[key]

        json_body = json.dumps(out, ensure_ascii=False, indent=2)
        with open(self._filepath, "w", encoding="utf-8") as f:
            f.write(_COMMENT_HEADER + json_body + "\n")

    # ── API ────────────────────────────────────────────

    def get(self, key: str, default=None):
        """读取配置项。优先级：用户数据 > DEFAULTS > default 参数"""
        if key in self._data:
            return self._data[key]
        if key in DEFAULTS:
            return DEFAULTS[key]
        return default

    def set(self, key: str, value):
        """写入配置项（仅内存，需调用 save() 持久化）"""
        self._data[key] = value

    def reset(self, key: str = None):
        """重置配置项。key 为 None 时清空全部，下次 save() 恢复为默认值"""
        if key is None:
            self._data.clear()
        else:
            self._data.pop(key, None)

    @property
    def filepath(self) -> str:
        """配置文件完整路径（只读）"""
        return self._filepath

    def __repr__(self):
        return f"<ConfigManager file={self._filepath!r} keys={len(self._data)}>"
