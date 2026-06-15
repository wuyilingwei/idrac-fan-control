"""能力探测 (PLAN.md §5.2)。

按 PLAN.md §5.1 路由表:
    | iDRAC | 控制后端 | 命令 |
    | ≤8 / iDRAC9 <3.30.30.30 | ipmi | pyghmi raw 0x30 0x30 ... |
    | iDRAC9 ≥3.30.30.30 / iDRAC10 | redfish_oem | Dell Redfish OEM 风扇属性 |

模块结构:
    - parse_idrac_gen(firmware): 纯函数, 固件版本号 → idrac 主版本号。
    - decide_backend(gen, firmware): 纯函数, 决策路由。
    - probe_dry_run(firmware): 仅做版本号解析, 不连真机。
    - probe(host, user, password, ...): 真机 Redfish + IPMI 探测, 返回 DeviceInfo。

R730 阻塞时, probe IPMI fan_count 段 try/except, 失败返回 fan_count=None
(findings 记录, 不硬撑)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from app.config import DeviceInfo
from app.idrac import ipmi as _ipmi
from app.idrac.redfish import RedfishClient


# Dell iDRAC 主版本号映射阈值 (PLAN §5.1 + Dell 命名)
# 固件首段 → idrac_gen
#   2.x        → iDRAC8
#   3.x/4.x/5.x/6.x/7.x → iDRAC9
#   10.x+      → iDRAC10
_GEN_MAP = {
    2: 8,
    3: 9,
    4: 9,
    5: 9,
    6: 9,
    7: 9,
    10: 10,
}

# 切换 ipmi → redfish_oem 的固件阈值 (PLAN §5.1 + 社区资料 tigerblue77)
_IDRAC9_REDFISH_OEM_MIN = (3, 30, 30, 30)


def parse_idrac_gen(firmware: str) -> int:
    """固件版本号 → idrac_gen。

    规则:
        "2.x.x.x" → 8
        "3.x.x.x" / "4.x" / "5.x" / "6.x" / "7.x" → 9
        "10.x" → 10
        其余首段数字: 未知 → 抛 ValueError。

    参数:
        firmware: 例 "2.83.83.83", "3.30.30.30", "7.10.00.00", "10.0.0.0"。

    返回:
        int (8 / 9 / 10), 后续可扩展。
    """
    if not firmware:
        raise ValueError("firmware string is empty")
    head = firmware.strip().split(".", 1)[0]
    try:
        major = int(head)
    except ValueError as exc:
        raise ValueError(f"firmware first segment not int: {firmware!r}") from exc
    if major in _GEN_MAP:
        return _GEN_MAP[major]
    if major >= 10:
        # iDRAC10+ (10.x, 11.x ...): 假设 redfish_oem 路径
        return 10
    raise ValueError(f"unknown idrac firmware major: {major} (firmware={firmware!r})")


def _parse_firmware_tuple(firmware: str) -> Tuple[int, ...]:
    """固件版本号 → tuple[int, ...] 供阈值比较。

    非数字段 → 转 0。例 "3.30.30.30" → (3, 30, 30, 30)。
    """
    parts = firmware.strip().split(".")
    out: list[int] = []
    for p in parts:
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    return tuple(out)


def decide_backend(idrac_gen: int, firmware: str) -> str:
    """根据 idrac_gen + firmware 决定控制后端 (PLAN §5.1)。

    返回:
        "ipmi" | "redfish_oem"

    规则:
        idrac_gen ≤ 8 → ipmi
        idrac_gen == 9 且 firmware < 3.30.30.30 → ipmi
        其余 (iDRAC9 ≥ 3.30.30.30 / iDRAC10+) → redfish_oem
    """
    if idrac_gen <= 8:
        return "ipmi"
    if idrac_gen == 9:
        fw = _parse_firmware_tuple(firmware)
        if fw < _IDRAC9_REDFISH_OEM_MIN:
            return "ipmi"
        return "redfish_oem"
    # idrac_gen >= 10
    return "redfish_oem"


@dataclass
class _DryRunResult:
    """probe_dry_run 返回值: 仅版本号解析, 不含真机数据。"""

    idrac_firmware: str
    idrac_gen: int
    backend: str


def probe_dry_run(firmware: str) -> _DryRunResult:
    """仅做版本号解析的纯函数 (单测 / CLI 调用, 不连真机)。"""
    gen = parse_idrac_gen(firmware)
    backend = decide_backend(gen, firmware)
    return _DryRunResult(idrac_firmware=firmware, idrac_gen=gen, backend=backend)


def _ipmi_fan_count(host: str, user: str, password: str) -> Optional[int]:
    """用 M1 ipmi 模块读 SDR, 数 type=='Fan' 的项。

    失败 (连接超时 / 会话拒绝 / R730 BMC session 满) → 返回 None,
    不抛, 不打凭据 (PLAN §6 凭据安全)。
    """
    try:
        cmd = _ipmi.connect(host, user, password, keepalive=False)
        report = _ipmi.read_sensors(cmd)
        fans = report.get("fans", [])
        return len(fans)
    except Exception:
        # R730 阻塞: BMC session 满 / 网络不通 → fan_count 退化为 None。
        # 不打 traceback (避免泄露上下文), 由调用方在 findings 记录。
        return None


def _extract_service_tag(system_doc: dict) -> Optional[str]:
    """从 Redfish system doc 抽 ServiceTag。

    Dell iDRAC 把 ServiceTag 放在 "SKU" 字段; 有的固件也填 "Oem.Dell.DellSystem.ChassisServiceTag"。
    优先 SKU, 退化到 Oem 路径。
    """
    sku = system_doc.get("SKU")
    if sku:
        return str(sku)
    oem = system_doc.get("Oem", {}).get("Dell", {})
    # 不同固件结构略异, 这里尽力而为
    for key in ("DellSystem", "DellSystemModel"):
        sub = oem.get(key)
        if isinstance(sub, dict):
            tag = sub.get("ChassisServiceTag") or sub.get("ServiceTag")
            if tag:
                return str(tag)
    return None


def _extract_host_os(system_doc: dict) -> Optional[str]:
    """从 Redfish system doc 抽 host OS 名(尽力而为)。

    优先级:
        1. Oem.Dell.DellSystem.HostOSName(iDRAC9+ 装 iSM 后通常有)
        2. Oem.Dell.DellSystem.OSName / OperatingSystem
        3. HostName(iDRAC 配置的主机名,不严格是 OS;但用户能用来识别机器)
    都没有 → None(UI 显示 "—")
    """
    oem = system_doc.get("Oem", {}).get("Dell", {})
    for key in ("DellSystem", "DellSystemModel"):
        sub = oem.get(key)
        if isinstance(sub, dict):
            for field in ("HostOSName", "OSName", "OperatingSystem"):
                v = sub.get(field)
                if v:
                    return str(v)
    hn = system_doc.get("HostName")
    if hn:
        return str(hn)
    return None


def probe(
    host: str,
    user: str,
    password: str,
    verify_tls: bool = False,
) -> DeviceInfo:
    """对真机做一次能力探测, 返回 DeviceInfo。

    步骤 (PLAN §5.2):
        a. Redfish get_manager → FirmwareVersion → idrac_gen
        b. decide_backend (副作用: 不存, 仅作为调用方决策用 — 这里不返回 backend,
           交给上层 Config 写 device.backend)
        c. Redfish get_system → Model / SKU(ServiceTag)
        d. IPMI fan_count (失败 → None)

    Note:
        - 凭据透传到 RedfishClient / ipmi.connect, 不打印。
        - R730 IPMI 阻塞时, fan_count 段 try/except → None, 上层 findings 记录。
    """
    info = DeviceInfo()
    with RedfishClient(host, user, password, verify_tls=verify_tls) as rf:
        manager = rf.get_manager()
        firmware = manager.get("FirmwareVersion") or ""
        info.idrac_firmware = firmware or None
        if firmware:
            try:
                info.idrac_gen = parse_idrac_gen(firmware)
            except ValueError:
                info.idrac_gen = None

        system = rf.get_system()
        info.model = system.get("Model")
        info.service_tag = _extract_service_tag(system)
        info.host_os = _extract_host_os(system)

    # IPMI fan_count — R730 阻塞时 None, 不硬撑
    info.fan_count = _ipmi_fan_count(host, user, password)
    return info
