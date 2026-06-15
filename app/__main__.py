"""无头核心服务入口 — `python -m app [--host ... --port ... --config ...]`。

PLAN §1.1:
  - 无头 Linux:systemd / 计划任务拉起本入口,浏览器访问。
  - 桌面 Win/macOS:通常走 `app.desktop`,该入口顺便起服务 + 开窗。

此入口纯阻塞跑 Uvicorn(不 daemon),适合 systemd Type=simple。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="idrac-fan-control",
        description="iDRAC Fan Control 核心服务 (headless)。",
    )
    # --host 默认 None,从 config.json settings.bind_host 读;CLI 显式给则覆盖配置
    parser.add_argument("--host", default=None,
                        help="监听地址(覆盖 config.json settings.bind_host)。默认从 config 读;空配置 fallback 127.0.0.1。")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.json"),
        help="config.json 路径 (默认: 当前目录 config.json)。",
    )
    parser.add_argument(
        "--log-level", default="info", choices=["critical", "error", "warning", "info", "debug"],
    )
    args = parser.parse_args(argv)

    import uvicorn

    from app.main import build_app
    from app.service import ServiceContainer, _default_backend_factory_with_cache

    static_dir = str((Path(__file__).parent / "static").resolve())
    container = ServiceContainer(
        args.config,
        backend_factory=_default_backend_factory_with_cache(),
    )
    app = build_app(container, static_dir=static_dir)

    # 决定监听地址:
    #   1. --host 显式给 → 用 CLI 值
    #   2. 否则从 config settings.bind_host 读
    #   3. 安全约束:无 master_password 时强制 127.0.0.1(可达地址列表)
    settings = container.cfg.settings
    bind_host = args.host or settings.bind_host or "127.0.0.1"
    LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
    if not settings.master_password and bind_host not in LOCAL_HOSTS:
        print(
            f"WARN: master_password 未设置,强制将 bind_host 从 {bind_host!r} 改为 127.0.0.1。\n"
            "      若要监听公网,先在 Settings 设置主密码再改 bind_host。",
            file=sys.stderr,
        )
        bind_host = "127.0.0.1"

    uvicorn.run(
        app,
        host=bind_host,
        port=args.port,
        log_level=args.log_level,
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
