"""曲线评估 — PLAN §3.2 step / linear。

evaluate_curve(curve, temp) -> int:
    - points 内部按 temp 升序 sort(防上游乱序)。
    - 0 点 → ValueError;1 点 → 该点 pct(常量)。
    - 区间外 clamp 用首/尾点的 pct(信任用户,不抛错)。
    - step:落在区间 [a.temp, b.temp) 取下界 a.pct;
            最右端点 temp 严格落 == 末点时取末点 pct。
    - linear:[a.temp, b.temp] 线性插值 + round 到 int。
    - mode ∉ {"step", "linear"} → ValueError。

PLAN 决策:不在此层做 0–100 钳制(IPMI 层做),信任配置。
两点同 temp(异常配置)线性段除零保护 → 取下界 a.pct,不抛。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Curve


def evaluate_curve(curve: "Curve", temp: float) -> int:
    if curve.mode not in ("step", "linear"):
        raise ValueError(f"unsupported curve mode: {curve.mode!r}")
    points = sorted(curve.points, key=lambda p: p.temp)
    if not points:
        raise ValueError("curve has no points")
    if len(points) == 1:
        return int(points[0].pct)
    if temp <= points[0].temp:
        return int(points[0].pct)
    if temp >= points[-1].temp:
        return int(points[-1].pct)

    if curve.mode == "step":
        # half-open [a, b): temp == b 走下一对(取 b 段 pct),更直觉
        for a, b in zip(points, points[1:]):
            if a.temp <= temp < b.temp:
                return int(a.pct)
        return int(points[-1].pct)  # 防御 — 上面 clamp 应已覆盖

    # linear: closed [a, b] 插值
    for a, b in zip(points, points[1:]):
        if a.temp <= temp <= b.temp:
            if b.temp == a.temp:
                return int(a.pct)
            ratio = (temp - a.temp) / (b.temp - a.temp)
            return int(round(a.pct + ratio * (b.pct - a.pct)))
    return int(points[-1].pct)
