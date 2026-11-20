import importlib.util
import os
import sys

FUNCTIONS = {}

# 加载失败的插件：key -> 错误说明，便于界面/调试时定位问题
LOAD_ERRORS = {}

# 非致命问题（如插件显示名重复），启动时提示
LOAD_WARNINGS = []


def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.abspath(".")


def _load_module(key, file_path):
    """从文件路径加载插件模块（不依赖已废弃的 load_module()）。"""
    spec = importlib.util.spec_from_file_location(key, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法为 {file_path} 创建模块加载器")

    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(key, None)
        raise
    return module


def load_plugins():
    base_path = get_base_path()
    plugin_dir = os.path.join(base_path, "plugins")

    FUNCTIONS.clear()
    LOAD_ERRORS.clear()
    LOAD_WARNINGS.clear()

    for file in sorted(os.listdir(plugin_dir)):
        if not file.endswith(".py") or file == "__init__.py":
            continue

        key = file[:-3]
        file_path = os.path.join(plugin_dir, file)

        # 单个插件损坏只跳过该插件，不影响其它插件和程序启动
        try:
            module = _load_module(key, file_path)
        except Exception as exc:
            LOAD_ERRORS[key] = f"{type(exc).__name__}: {exc}"
            print(f"[StreamKnife] 插件加载失败：{file} -> {exc}", file=sys.stderr)
            continue

        if not hasattr(module, "run"):
            LOAD_ERRORS[key] = "缺少 run() 函数"
            print(f"[StreamKnife] 插件加载失败：{file} -> 缺少 run() 函数", file=sys.stderr)
            continue

        FUNCTIONS[key] = {
            "name": getattr(module, "NAME", key),
            "category": getattr(module, "CATEGORY", "uncategorized"),
            "desc": getattr(module, "DESC", ""),
            "func": module.run,
            "meta": getattr(module, "META", {"params": []})
        }

    # 检测显示名重复：界面以 NAME 作为查找 key，重名会静默互相覆盖
    names = {}
    for key, meta in FUNCTIONS.items():
        name = meta["name"]
        if name in names:
            warning = (
                f"插件显示名重复：「{name}」({names[name]}, {key})，"
                f"列表中同名插件会互相覆盖"
            )
            LOAD_WARNINGS.append(warning)
            print(f"[StreamKnife] {warning}", file=sys.stderr)
        else:
            names[name] = key
