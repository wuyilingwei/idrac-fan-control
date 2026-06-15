"""M3 曲线评估 CLI — 辅助验证用。

用法:
    python -m app.cli.m3_simulate simulate-curve --curve-id quiet --temp 45
    python -m app.cli.m3_simulate simulate-curve --config /path/config.json \\
        --curve-id quiet --temp 45

不连真机,纯函数;config 缺失/曲线缺失退出码 1。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import load
from app.curve import evaluate_curve


def _cmd_simulate_curve(args: argparse.Namespace) -> int:
    cfg = load(args.config)
    curve = next((c for c in cfg.curves if c.id == args.curve_id), None)
    if curve is None:
        print(
            f"ERROR: curve id {args.curve_id!r} not found in {args.config}",
            file=sys.stderr,
        )
        return 1
    try:
        pct = evaluate_curve(curve, args.temp)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"curve={args.curve_id} mode={curve.mode} "
        f"temp={args.temp} target_pct={pct}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="m3_simulate",
        description="M3 曲线评估 CLI (step/linear)。",
    )
    sub = p.add_subparsers(dest="subcommand", required=True)

    sp = sub.add_parser(
        "simulate-curve",
        help="读 config 中给定曲线,在指定 temp 评估 target_pct。",
    )
    sp.add_argument(
        "--config",
        type=Path,
        default=Path("config.json"),
        help="配置文件路径 (默认 config.json)。",
    )
    sp.add_argument("--curve-id", required=True, help="曲线 id。")
    sp.add_argument("--temp", required=True, type=float, help="目标温度 (°C)。")
    sp.set_defaults(func=_cmd_simulate_curve)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
