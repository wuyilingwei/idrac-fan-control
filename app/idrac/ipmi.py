"""pyghmi IPMI 后端 — R730 主路径（M1）。

封装最小化:
    connect(host, user, password) -> pyghmi.ipmi.command.Command
    read_sensors(cmd) -> {"temps": [...], "fans": [...]}
    set_manual_mode(cmd) -> raw 0x30 0x30 0x01 0x00
    set_fan_percent(cmd, pct) -> raw 0x30 0x30 0x02 0xff <pct>
    set_auto_mode(cmd) -> raw 0x30 0x30 0x01 0x01

设计原则 (PLAN.md §0 / §1.2 / §5.4):
    - 信任用户: set_fan_percent 不做下限钳制, 仅 0-100 物理边界。
    - 凭据透传: 不打印 / 不记录 password。
    - 兼容 pyghmi 1.6.x raw_command 返回 dict {"code": int, "data": bytearray}。
"""

from __future__ import annotations

from typing import Any, Dict, List

from pyghmi.ipmi import command as _pyghmi_command

# Dell OEM Fan Control raw 命令常量 (PLAN.md §5.4)
DELL_OEM_NETFN = 0x30
DELL_OEM_FAN_CMD = 0x30
_DATA_MANUAL = (0x01, 0x00)
_DATA_AUTO = (0x01, 0x01)
_FAN_SET_PREFIX = (0x02, 0xFF)


def connect(
    host: str,
    user: str,
    password: str,
    keepalive: bool = True,
) -> _pyghmi_command.Command:
    """建立 IPMI 会话。

    透传到 pyghmi.ipmi.command.Command。
    凭据仅传参, 不打印 / 不写日志。

    Args:
        keepalive: pyghmi 1.6.x Command 的 keepalive 关键字。
            默认 True 保持现有行为; 单序列短链路用例 (例如 verify-all)
            可传 False 让会话不参与 pyghmi 后台 keepalive 维持,
            降低对 iDRAC8 默认 4 路 BMC session 的占用压力。
    """
    return _pyghmi_command.Command(
        bmc=host,
        userid=user,
        password=password,
        keepalive=keepalive,
    )


def read_sensors(cmd: _pyghmi_command.Command) -> Dict[str, List[Dict[str, Any]]]:
    """读取 SDR, 筛 Temperature/Fan 且 value 非 None 的项。

    返回:
        {
            "temps": [{"name": str, "value_c": float}, ...],
            "fans":  [{"name": str, "rpm": float}, ...],
        }
    """
    temps: List[Dict[str, Any]] = []
    fans: List[Dict[str, Any]] = []
    for reading in cmd.get_sensor_data():
        if reading is None:
            continue
        name = getattr(reading, "name", None)
        sensor_type = getattr(reading, "type", None)
        value = getattr(reading, "value", None)
        if name is None or value is None:
            continue
        if sensor_type == "Temperature":
            temps.append({"name": name, "value_c": float(value)})
        elif sensor_type == "Fan":
            fans.append({"name": name, "rpm": float(value)})
    return {"temps": temps, "fans": fans}


def _raw(cmd: _pyghmi_command.Command, data: tuple) -> Dict[str, Any]:
    """统一 raw 调用入口, 兼容 pyghmi 返回 dict 形态。"""
    rsp = cmd.raw_command(
        netfn=DELL_OEM_NETFN,
        command=DELL_OEM_FAN_CMD,
        data=list(data),
    )
    # pyghmi 1.6.x 返回 dict, 形如 {"code": 0, "data": bytearray()}
    if isinstance(rsp, dict):
        code = rsp.get("code")
        if code not in (0, None):
            raise RuntimeError(
                f"IPMI raw command failed: completion code {code:#04x}"
            )
    return rsp if isinstance(rsp, dict) else {"data": rsp}


def set_manual_mode(cmd: _pyghmi_command.Command) -> Dict[str, Any]:
    """进入 Dell OEM 手动风扇控制模式。raw 0x30 0x30 0x01 0x00"""
    return _raw(cmd, _DATA_MANUAL)


def set_fan_percent(cmd: _pyghmi_command.Command, pct: int) -> Dict[str, Any]:
    """设转速 pct%。raw 0x30 0x30 0x02 0xff <pct>。

    pct 为 0-100 十进制 int, 内部转 hex byte 喂入 data。
    PLAN 决策: 不做下限钳制, 只做 0-100 物理边界检查 (信任用户)。
    """
    if not isinstance(pct, int):
        raise TypeError(f"pct must be int, got {type(pct).__name__}")
    if pct < 0 or pct > 100:
        raise ValueError(f"pct must be in [0, 100]; got {pct}")
    return _raw(cmd, _FAN_SET_PREFIX + (pct,))


def set_auto_mode(cmd: _pyghmi_command.Command) -> Dict[str, Any]:
    """恢复 Dell 自动风扇控制。raw 0x30 0x30 0x01 0x01"""
    return _raw(cmd, _DATA_AUTO)
