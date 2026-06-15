"""M1 主链路 CLI 验证 — argparse 子命令 sensors | manual | set <pct> | auto | verify-all。

凭据从 agents/test-target.json 读 (json.load 后 host/user/password 直接传 connect)。
绝不打印 password。

用法:
    python -m app.cli.m1_verify sensors
    python -m app.cli.m1_verify manual
    python -m app.cli.m1_verify set 30
    python -m app.cli.m1_verify auto
    python -m app.cli.m1_verify verify-all   # 单 Command 跑完整序列, 省 BMC session

退出码: 0 成功, 1 错误。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict

from app.idrac import ipmi

# 凭据文件相对项目根
_DEFAULT_CREDS = Path("agents/test-target.json")


def _load_creds(path: Path) -> Dict[str, str]:
    """读 host/user/password。绝不打印 password。"""
    with path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    missing = [k for k in ("host", "user", "password") if k not in data]
    if missing:
        raise KeyError(f"credentials file missing keys: {missing}")
    return data


def _print_sensors(report: Dict[str, Any]) -> None:
    temps = report.get("temps", [])
    fans = report.get("fans", [])
    print(f"=== Temperatures ({len(temps)}) ===")
    for t in temps:
        print(f"  {t['name']:<32}  {t['value_c']:>6.1f} °C")
    print(f"=== Fans ({len(fans)}) ===")
    for f in fans:
        print(f"  {f['name']:<32}  {f['rpm']:>7.0f} RPM")


def _cmd_sensors(args: argparse.Namespace) -> int:
    creds = _load_creds(args.creds)
    cmd = ipmi.connect(creds["host"], creds["user"], creds["password"])
    report = ipmi.read_sensors(cmd)
    _print_sensors(report)
    return 0


def _cmd_manual(args: argparse.Namespace) -> int:
    creds = _load_creds(args.creds)
    cmd = ipmi.connect(creds["host"], creds["user"], creds["password"])
    rsp = ipmi.set_manual_mode(cmd)
    print(f"manual mode set: code={rsp.get('code')}, data={bytes(rsp.get('data') or b'').hex()}")
    return 0


def _cmd_set(args: argparse.Namespace) -> int:
    creds = _load_creds(args.creds)
    cmd = ipmi.connect(creds["host"], creds["user"], creds["password"])
    rsp = ipmi.set_fan_percent(cmd, args.pct)
    print(
        f"fan percent set to {args.pct}%: "
        f"code={rsp.get('code')}, data={bytes(rsp.get('data') or b'').hex()}"
    )
    return 0


def _cmd_auto(args: argparse.Namespace) -> int:
    creds = _load_creds(args.creds)
    cmd = ipmi.connect(creds["host"], creds["user"], creds["password"])
    rsp = ipmi.set_auto_mode(cmd)
    print(f"auto mode set: code={rsp.get('code')}, data={bytes(rsp.get('data') or b'').hex()}")
    return 0


def _fan_summary(report: Dict[str, Any]) -> str:
    """风扇 RPM 概况摘要(min/avg/max + 计数), 不打印逐项也不打印凭据。"""
    fans = report.get("fans", [])
    if not fans:
        return "fans=0"
    rpms = [f["rpm"] for f in fans]
    return (
        f"fans={len(fans)} "
        f"min={min(rpms):.0f} "
        f"avg={sum(rpms) / len(rpms):.0f} "
        f"max={max(rpms):.0f} RPM"
    )


def _temp_summary(report: Dict[str, Any]) -> str:
    """温度概况(min/avg/max + 计数)。"""
    temps = report.get("temps", [])
    if not temps:
        return "temps=0"
    vals = [t["value_c"] for t in temps]
    return (
        f"temps={len(temps)} "
        f"min={min(vals):.1f} "
        f"avg={sum(vals) / len(vals):.1f} "
        f"max={max(vals):.1f} °C"
    )


def _cmd_verify_all(args: argparse.Namespace) -> int:
    """完整序列, 共享单一 Command 避免顺序 connect() 撞 iDRAC8 4 路 session 上限。

    序列:
        sensors → manual → set 30 → sleep 8s → sensors → auto → sensors
    每步打印命令名 + 关键返回 (code / 风扇 RPM 概况); 不打印密码 / 完整 traceback。
    """
    creds = _load_creds(args.creds)
    print(f"[verify-all] connect host={creds['host']} user={creds['user']} keepalive=False")
    # keepalive=False: 单一短链路, 不参与 pyghmi 后台 keepalive, 减轻 BMC session 占用
    cmd = ipmi.connect(
        creds["host"], creds["user"], creds["password"], keepalive=False
    )

    print("[verify-all] step 1/7: read_sensors (baseline)")
    report = ipmi.read_sensors(cmd)
    _print_sensors(report)
    print(f"  summary: {_temp_summary(report)} | {_fan_summary(report)}")

    print("[verify-all] step 2/7: set_manual_mode")
    rsp = ipmi.set_manual_mode(cmd)
    print(f"  code={rsp.get('code')}")

    print("[verify-all] step 3/7: set_fan_percent(30)")
    rsp = ipmi.set_fan_percent(cmd, 30)
    print(f"  code={rsp.get('code')}")

    print("[verify-all] step 4/7: sleep 8s (BMC 风扇响应时间)")
    time.sleep(8)

    print("[verify-all] step 5/7: read_sensors (after manual 30%)")
    report = ipmi.read_sensors(cmd)
    _print_sensors(report)
    print(f"  summary: {_temp_summary(report)} | {_fan_summary(report)}")

    print("[verify-all] step 6/7: set_auto_mode")
    rsp = ipmi.set_auto_mode(cmd)
    print(f"  code={rsp.get('code')}")

    print("[verify-all] step 7/7: read_sensors (after auto restored)")
    report = ipmi.read_sensors(cmd)
    _print_sensors(report)
    print(f"  summary: {_temp_summary(report)} | {_fan_summary(report)}")

    print("[verify-all] OK")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="m1_verify",
        description="M1 pyghmi 主链路验证 CLI (R730 IPMI raw).",
    )
    p.add_argument(
        "--creds",
        type=Path,
        default=_DEFAULT_CREDS,
        help="凭据 JSON 路径 (默认 agents/test-target.json)。",
    )
    sub = p.add_subparsers(dest="subcommand", required=True)

    sub.add_parser("sensors", help="读取并打印 SDR 温度/转速。").set_defaults(func=_cmd_sensors)
    sub.add_parser("manual", help="进入手动控制模式 (raw 01 00)。").set_defaults(func=_cmd_manual)

    sp_set = sub.add_parser("set", help="设转速 N%% (0-100)。")
    sp_set.add_argument("pct", type=int, help="目标转速百分比 (0-100)。")
    sp_set.set_defaults(func=_cmd_set)

    sub.add_parser("auto", help="恢复 Dell 自动控制 (raw 01 01)。").set_defaults(func=_cmd_auto)

    sub.add_parser(
        "verify-all",
        help="共享单一 Command 跑完整序列 (省 BMC session)。",
    ).set_defaults(func=_cmd_verify_all)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # 顶层兜底, 不泄露 traceback 给生产, M1 阶段还是显示
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
