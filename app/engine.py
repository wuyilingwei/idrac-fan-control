"""控制循环 + failsafe(B) — PLAN §3 / §4。

ControlLoop:
    - tick(): 对每个有 assignment 的设备 → 读温度 → 评估曲线 → 设转速 → failsafe 检查
    - run_forever(): while True: tick(); sleep(poll_interval_s);CancelledError 退出。
    - Backend Protocol: read_hottest_temp / set_fan_percent / set_auto_mode(同步接口,M5 注入实现)
    - notify_fn: 异步 fire-and-forget;asyncio.create_task + asyncio.wait_for 超时兜底;失败不阻塞 tick。

failsafe(B 方案,PLAN §4):
    temp ≥ failsafe_temp_c → 总发 overtemp_alert(无论开关)
    failsafe_enabled=True → 同时调 set_auto_mode + 发 failsafe_trip
    failsafe_enabled=False → 仅告警,不夺控制

事件类型(PLAN §7.2):
    overtemp_alert / failsafe_trip / connection_lost / command_failed
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol

from app.config import Config, Device

log = logging.getLogger(__name__)

NotifyFn = Callable[[str, Dict[str, Any]], Awaitable[None]]


class Backend(Protocol):
    """后端抽象 (PLAN §5.1)。M5 集成时注入 IpmiBackend / RedfishOemBackend。"""

    def read_hottest_temp(self, device: Device) -> float: ...
    def set_fan_percent(self, device: Device, pct: int) -> None: ...
    def set_auto_mode(self, device: Device) -> None: ...


BackendFactory = Callable[[Device], Backend]


async def _noop_notify(event: str, ctx: Dict[str, Any]) -> None:
    return None


def _default_backend_factory(device: Device) -> Backend:
    raise NotImplementedError(
        "M5 集成时注入 backend_factory(根据 device.backend 选 IpmiBackend / RedfishOemBackend)"
    )


@dataclass
class TickResult:
    """一次 tick 中单设备的结果。便于 testing / API 上报。"""

    device_id: str
    temp: Optional[float]
    target_pct: Optional[int]
    status: str
    # 取值: ok | failsafe_trip | overtemp_alert_only |
    #       connection_lost | command_failed |
    #       no_assignment | no_curve | no_points | bad_curve_mode


class ControlLoop:
    def __init__(
        self,
        cfg: Config,
        notify_fn: Optional[NotifyFn] = None,
        backend_factory: Optional[BackendFactory] = None,
        notify_timeout_s: float = 10.0,
    ) -> None:
        self.cfg = cfg
        self.notify_fn: NotifyFn = notify_fn or _noop_notify
        self.backend_factory: BackendFactory = (
            backend_factory or _default_backend_factory
        )
        self.notify_timeout_s = notify_timeout_s
        self._curves_by_id = {c.id: c for c in cfg.curves}
        self._notify_tasks: List[asyncio.Task[None]] = []

    def _notify(self, event: str, ctx: Dict[str, Any]) -> None:
        """fire-and-forget。超时由 wait_for 兜底;失败仅 log。"""

        async def _wrap() -> None:
            try:
                await asyncio.wait_for(
                    self.notify_fn(event, ctx), timeout=self.notify_timeout_s
                )
            except Exception as exc:  # pylint: disable=broad-except
                log.warning("notify failed: event=%s err=%s", event, exc)

        task = asyncio.create_task(_wrap())
        self._notify_tasks.append(task)
        self._notify_tasks = [t for t in self._notify_tasks if not t.done()]

    async def tick(self) -> Dict[str, TickResult]:
        from app.curve import evaluate_curve

        out: Dict[str, TickResult] = {}
        settings = self.cfg.settings
        for device in self.cfg.devices:
            curve_id = self.cfg.assignments.get(device.id)
            if curve_id is None:
                out[device.id] = TickResult(device.id, None, None, "no_assignment")
                continue
            curve = self._curves_by_id.get(curve_id)
            if curve is None:
                out[device.id] = TickResult(device.id, None, None, "no_curve")
                continue

            try:
                backend = self.backend_factory(device)
                temp = backend.read_hottest_temp(device)
            except Exception as exc:  # pylint: disable=broad-except
                self._notify(
                    "connection_lost",
                    {
                        "device_id": device.id,
                        "device_name": device.name,
                        "device_host": device.host,
                        "error": str(exc),
                    },
                )
                out[device.id] = TickResult(device.id, None, None, "connection_lost")
                continue

            try:
                target_pct = evaluate_curve(curve, temp)
            except ValueError as exc:
                log.warning("evaluate_curve failed device=%s: %s", device.id, exc)
                status_key = "bad_curve_mode" if "mode" in str(exc) else "no_points"
                out[device.id] = TickResult(device.id, temp, None, status_key)
                continue

            try:
                backend.set_fan_percent(device, target_pct)
            except Exception as exc:  # pylint: disable=broad-except
                self._notify(
                    "command_failed",
                    {
                        "device_id": device.id,
                        "device_name": device.name,
                        "device_host": device.host,
                        "command": "set_fan_percent",
                        "pct": target_pct,
                        "error": str(exc),
                    },
                )
                out[device.id] = TickResult(
                    device.id, temp, target_pct, "command_failed"
                )
                continue

            status = "ok"
            if temp >= settings.failsafe_temp_c:
                self._notify(
                    "overtemp_alert",
                    {
                        "device_id": device.id,
                        "device_name": device.name,
                        "device_host": device.host,
                        "temp": temp,
                        "threshold": settings.failsafe_temp_c,
                    },
                )
                if settings.failsafe_enabled:
                    try:
                        backend.set_auto_mode(device)
                        self._notify(
                            "failsafe_trip",
                            {
                                "device_id": device.id,
                                "device_name": device.name,
                                "device_host": device.host,
                                "temp": temp,
                                "threshold": settings.failsafe_temp_c,
                            },
                        )
                        status = "failsafe_trip"
                    except Exception as exc:  # pylint: disable=broad-except
                        self._notify(
                            "command_failed",
                            {
                                "device_id": device.id,
                                "device_name": device.name,
                                "device_host": device.host,
                                "command": "set_auto_mode",
                                "error": str(exc),
                            },
                        )
                        status = "command_failed"
                else:
                    status = "overtemp_alert_only"

            out[device.id] = TickResult(device.id, temp, target_pct, status)
        return out

    async def run_forever(self) -> None:
        try:
            while True:
                try:
                    await self.tick()
                except Exception as exc:  # pylint: disable=broad-except
                    log.exception("tick error: %s", exc)
                await asyncio.sleep(self.cfg.settings.poll_interval_s)
        except asyncio.CancelledError:
            log.info("control loop cancelled")
            raise

    async def aclose(self) -> None:
        """等所有未完成 fire-and-forget notify 收尾(测试 / 优雅关闭用)。"""
        pending = [t for t in self._notify_tasks if not t.done()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._notify_tasks.clear()
