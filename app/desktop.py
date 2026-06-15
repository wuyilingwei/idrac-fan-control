"""pywebview 桌面入口 — PLAN §1.1 / §10。

桌面端(Win/macOS)启动流程:
    1. 启动核心服务(Starlette + Uvicorn,后台线程 / 子进程二选一)
    2. 等待 :8080 端口可用
    3. 打开 pywebview 窗口指向 http://127.0.0.1:8080/

无头(Linux)不走这里 — 用 `python -m app` 拉核心服务(systemd 拉 service),浏览器访问。

容错:
    - 若服务已在跑(端口被占),直接打开窗口(共享同一服务)。
    - pywebview 未安装时给清晰指引,不静默崩。
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Optional


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
DEFAULT_CONFIG = Path("config.json")


def _port_in_use(host: str, port: int, timeout: float = 0.5) -> bool:
    """端口是否已被监听。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            return False


def _wait_port(host: str, port: int, max_wait_s: float = 15.0) -> bool:
    deadline = time.monotonic() + max_wait_s
    while time.monotonic() < deadline:
        if _port_in_use(host, port):
            return True
        time.sleep(0.2)
    return False


def _start_service_in_thread(host: str, port: int, cfg_path: Path) -> threading.Thread:
    """后台线程启动 Uvicorn + Starlette。"""
    import uvicorn  # noqa: WPS433 — 仅桌面入口需要

    from app.main import build_app
    from app.service import ServiceContainer

    static_dir = str((Path(__file__).parent / "static").resolve())
    container = ServiceContainer(cfg_path)
    app = build_app(container, static_dir=static_dir)

    def _run() -> None:
        config = uvicorn.Config(
            app, host=host, port=port, log_level="info", access_log=False
        )
        server = uvicorn.Server(config)
        server.run()

    t = threading.Thread(target=_run, daemon=True, name="uvicorn-core")
    t.start()
    return t


def _open_window(url: str, title: str) -> None:
    try:
        import webview  # type: ignore
    except ImportError:
        print(
            "ERROR: pywebview not installed. Run:\n"
            "    pip install pywebview\n"
            "  Then re-run this entry point.",
            file=sys.stderr,
        )
        sys.exit(2)
    webview.create_window(title, url, width=1100, height=720)
    webview.start()


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="idrac-fan-control-desktop",
        description="iDRAC Fan Control 桌面入口 (pywebview)。",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="config.json 路径 (默认: 当前目录 config.json)。",
    )
    parser.add_argument(
        "--no-service",
        action="store_true",
        help="不启动核心服务 (假设外部已在 host:port 运行)。",
    )
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="只启动核心服务,不开窗口 (等同 `python -m app`)。",
    )
    args = parser.parse_args(argv)

    started_here = False
    if not args.no_service and not _port_in_use(args.host, args.port):
        _start_service_in_thread(args.host, args.port, args.config)
        started_here = True
        if not _wait_port(args.host, args.port):
            print(
                f"ERROR: core service did not become ready on "
                f"{args.host}:{args.port} within 15s",
                file=sys.stderr,
            )
            return 1

    url = f"http://{args.host}:{args.port}/"
    if args.no_window:
        print(f"core service running at {url}; --no-window set, sleeping forever")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0

    _open_window(url, "iDRAC Fan Control")
    # 窗口关闭后,主线程返回;若服务由本进程拉起,daemon=True 会随退出收尾
    _ = started_here
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
