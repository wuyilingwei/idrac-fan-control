# PyInstaller 配置 — PLAN §1.2 / §10。
#
# 用法:
#   pip install pyinstaller
#   pyinstaller build.spec
#
# 产物:
#   dist/idrac-fan-control(.exe)
#
# UPX 注意 (PLAN §12):
#   macOS 需测试; 若 UPX 破坏加载, 改 upx=False 重打。
#   ARM mac / Apple Silicon 上 UPX 通常不可用 — 已默认 OFF macOS。
#
# 桌面入口 (默认): app/desktop.py — 启动核心服务 + 开 pywebview 窗口。
# 无头入口: 改 entry = "app/__main__.py" 后重打。
import sys
from pathlib import Path

block_cipher = None
ROOT = Path(".").resolve()
ENTRY = "app/desktop.py"  # 桌面默认; 改 app/__main__.py 出 headless 二进制

# 静态资源 (Vue build 产物)
datas = []
static_dir = ROOT / "app" / "static"
if static_dir.exists():
    datas.append((str(static_dir), "app/static"))

# 隐藏 import — pyghmi/starlette/uvicorn 有动态 import 路径
hiddenimports = [
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan.on",
    "uvicorn.loops.asyncio",
    "uvicorn.logging",
    "pyghmi.ipmi.command",
    "pyghmi.ipmi.private",
]

# UPX: mac 默认关 (易破坏 dylib); Linux/Windows 默认开
upx = sys.platform != "darwin"

a = Analysis(
    [ENTRY],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "test", "unittest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="idrac-fan-control",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=upx,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 桌面: 不开终端;改 True 出无头/CLI 版本
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
