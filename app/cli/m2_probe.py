"""M2 能力探测 + 默认 Config 输出 CLI。

子命令:
    probe         : 读 agents/test-target.json, 跑 probe(), 打印 DeviceInfo
                    (不打印 password)。
    dump-default  : 打印 PLAN.md §2 的默认 Config JSON。

凭据安全 (与 M1 一致):
    - 读 JSON 后 dict 直接传 probe(), 不打印 password。
    - 顶层 except 不暴露 traceback 给生产, M2 阶段仍打类型+消息便于排错。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from app.config import Config, default_settings
from app.idrac.probe import probe


_DEFAULT_CREDS = Path("agents/test-target.json")


def _load_creds(path: Path) -> Dict[str, str]:
    """读 host/user/password。绝不打印 password。"""
    with path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    missing = [k for k in ("host", "user", "password") if k not in data]
    if missing:
        raise KeyError(f"credentials file missing keys: {missing}")
    return data


def _cmd_probe(args: argparse.Namespace) -> int:
    creds = _load_creds(args.creds)
    verify_tls = bool(creds.get("verify_tls", False))
    print(f"[probe] host={creds['host']} user={creds['user']} verify_tls={verify_tls}")
    info = probe(
        host=creds["host"],
        user=creds["user"],
        password=creds["password"],
        verify_tls=verify_tls,
    )
    payload = info.to_dict()
    # 不会出现 password 字段 — DeviceInfo 不含。再保险一道:
    payload.pop("password", None)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_dump_default(_args: argparse.Namespace) -> int:
    cfg = Config(
        version=2,
        devices=[],
        curves=[],
        assignments={},
        settings=default_settings(),
        notifiers=[],
    )
    print(json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="m2_probe",
        description="M2 能力探测 / 默认 Config 输出 CLI。",
    )
    p.add_argument(
        "--creds",
        type=Path,
        default=_DEFAULT_CREDS,
        help="凭据 JSON 路径 (默认 agents/test-target.json)。",
    )
    sub = p.add_subparsers(dest="subcommand", required=True)

    sub.add_parser(
        "probe",
        help="对真机做一次能力探测, 打印 DeviceInfo。",
    ).set_defaults(func=_cmd_probe)

    sub.add_parser(
        "dump-default",
        help="打印 PLAN.md §2 默认 Config JSON。",
    ).set_defaults(func=_cmd_dump_default)

    return p


def main(argv: Any = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
