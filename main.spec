# -*- mode: python ; coding: utf-8 -*-
import os
import sys

# 执行 spec 时把项目根目录加入 sys.path，否则下一行 import 不到 plugins 包，
# collect_submodules 会静默返回空列表，插件 import 的标准库都不会被打包
project_root = os.path.dirname(os.path.abspath(SPEC))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['json', 'importlib', 'plugins']
# 插件是运行时用 SourceFileLoader 从数据文件加载的，PyInstaller 无法静态分析，
# 必须显式加入 hiddenimports，让它们 import 的模块进入打包结果
hiddenimports += collect_submodules('plugins')
hiddenimports += ['platform', 'concurrent.futures', 'ctypes']


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('plugins', 'plugins')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='StreamKnife',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,

    icon='assets/app.ico'
)
