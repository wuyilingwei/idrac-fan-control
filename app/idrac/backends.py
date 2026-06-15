"""M5 集成层 — 把 M1 IpmiBackend / M2 RedfishOemBackend 包成 M3 Backend Protocol。

`build_backend(device)` 工厂根据 `device.backend` 选具体实现。
ServiceContainer 持有 backend 实例的缓存,避免每次 tick 重建 pyghmi 会话(占 BMC session)。

注意:Backend Protocol 的方法是同步的(由 M3 ControlLoop 在 asyncio 任务里调用)。
单设备 + 60s poll_interval 场景下,1-2s 阻塞可接受;高并发场景应在 ControlLoop 加 to_thread 包装。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.config import Device

log = logging.getLogger(__name__)


class IpmiBackend:
    """pyghmi 后端 — PLAN §5.4 R730 主路径。keepalive=False 让 session 不被后台保活,降低 BMC 占用。"""

    def __init__(self, device: Device) -> None:
        self._host = device.host
        self._user = device.user
        self._password = device.password
        self._cmd: Optional[Any] = None

    def _ensure(self) -> Any:
        if self._cmd is None:
            from app.idrac import ipmi as ipmi_mod

            self._cmd = ipmi_mod.connect(
                self._host, self._user, self._password, keepalive=False
            )
        return self._cmd

    def read_hottest_temp(self, device: Device) -> float:
        """两层组合:strategy(max/avg)= 聚合方法;temp_sensors 列表 = 参与范围(空=全部)。

        - strategy=max + sensors=[]      → 全部传感器最高
        - strategy=max + sensors=[A, B]  → A、B 中最高
        - strategy=avg + sensors=[]      → 全部传感器平均
        - strategy=avg + sensors=[A, B]  → A、B 的平均
        """
        from app.idrac import ipmi as ipmi_mod

        cmd = self._ensure()
        report = ipmi_mod.read_sensors(cmd)
        temps = report.get("temps", [])
        if not temps:
            raise ConnectionError("no temperature sensors")
        wanted = set(getattr(device, "temp_sensors", []) or [])
        if wanted:
            filtered = [t for t in temps if t["name"] in wanted]
            if filtered:
                temps = filtered
        strategy = (getattr(device, "temp_strategy", "max") or "max").lower()
        values = [t["value_c"] for t in temps]
        if strategy == "avg":
            return sum(values) / len(values)
        return max(values)

    def read_sensors(self, device: Device) -> dict:
        """供 GET /api/devices/{id}/sensors 暴露全部温度/风扇传感器名,前端选 sensors 用。"""
        from app.idrac import ipmi as ipmi_mod

        cmd = self._ensure()
        return ipmi_mod.read_sensors(cmd)

    def set_fan_percent(self, device: Device, pct: int) -> None:
        from app.idrac import ipmi as ipmi_mod

        cmd = self._ensure()
        ipmi_mod.set_manual_mode(cmd)
        ipmi_mod.set_fan_percent(cmd, pct)

    def set_auto_mode(self, device: Device) -> None:
        from app.idrac import ipmi as ipmi_mod

        cmd = self._ensure()
        ipmi_mod.set_auto_mode(cmd)


def build_backend(device: Device) -> Any:
    """根据 device.backend 字段选实现。redfish_oem 暂未真机验证 → NotImplementedError(PLAN §5.3 M8 阻塞)。"""
    if device.backend == "ipmi":
        return IpmiBackend(device)
    if device.backend == "redfish_oem":
        raise NotImplementedError(
            "redfish_oem 控制路径待 iDRAC9+ 真机字段验证(PLAN §5.3 / M8 阻塞)"
        )
    raise NotImplementedError(f"unknown device.backend: {device.backend!r}")
