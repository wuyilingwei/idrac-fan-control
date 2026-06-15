"""config.json 读写 / 权限设置 / 迁移 (PLAN.md §1.2 / §2 / §6)。

数据模型严格匹配 PLAN.md §2 schema:
    Config {
        version: int = 2,
        devices: list[Device],
        curves: list[Curve],
        assignments: dict[str, str],   # device_id -> curve_id
        settings: Settings,
        notifiers: list[Notifier],
    }

设计原则:
    - dataclass + to_dict / from_dict 互转, 便于前端 JSON 序列化。
    - `Device.password = field(repr=False)`: repr 不暴露密码字面量。
    - 原子写: 临时文件 + os.replace, 防并发崩 config。
    - 类 Unix 自动 chmod 0o600; Windows 暂用 stub + TODO。
    - migrate: 未知未来版本号 raise NotImplementedError; 1→2 实际无升级路径 (项目从 v2 起)。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


CONFIG_VERSION = 2


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class DeviceInfo:
    """加设备时探测缓存 (PLAN §2 devices[].info)。"""

    model: Optional[str] = None
    service_tag: Optional[str] = None
    idrac_firmware: Optional[str] = None
    idrac_gen: Optional[int] = None
    fan_count: Optional[int] = None
    host_os: Optional[str] = None  # 宿主操作系统(Probe 端点最佳努力填充;iDRAC8 通常拿不到)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Optional[Dict[str, Any]]) -> "DeviceInfo":
        raw = raw or {}
        return cls(
            model=raw.get("model"),
            service_tag=raw.get("service_tag"),
            idrac_firmware=raw.get("idrac_firmware"),
            idrac_gen=raw.get("idrac_gen"),
            fan_count=raw.get("fan_count"),
            host_os=raw.get("host_os"),
        )


def mask_password(s: str) -> str:
    """前 3 后 2 打码,中间 `***`;长度 ≤ 5 时全打 `*****`。"""
    if not s:
        return ""
    if len(s) <= 5:
        return "*" * 5
    return s[:3] + "***" + s[-2:]


def is_masked_password(s: str) -> bool:
    """判断字符串是否是 mask_password() 产出的 mask 形态(用于 PUT/POST 时识别占位)。"""
    if not s:
        return False
    if s == "*" * 5:
        return True
    return len(s) >= 5 and "***" in s and s[3:6] == "***"


@dataclass
class Device:
    """单台 iDRAC 设备 (PLAN §2 devices[])。"""

    id: str
    name: str
    host: str
    user: str
    # repr=False 防 `repr(device)` 把明文密码打印到日志/异常 traceback。
    password: str = field(default="", repr=False)
    backend: str = "ipmi"  # ipmi | redfish_oem
    info: DeviceInfo = field(default_factory=DeviceInfo)
    verify_tls: bool = False
    # 温度获取策略 (PLAN 扩展):
    #   max:    所有 temp 传感器取最高(默认,适合保守散热)
    #   avg:    所有 temp 传感器取平均
    #   select: 仅从 temp_sensors 列出的传感器中取 max
    temp_strategy: str = "max"
    temp_sensors: List[str] = field(default_factory=list)

    def to_dict(self, *, mask_password_field: bool = False) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "host": self.host,
            "user": self.user,
            "password": mask_password(self.password) if mask_password_field else self.password,
            "backend": self.backend,
            "info": self.info.to_dict(),
            "verify_tls": self.verify_tls,
            "temp_strategy": self.temp_strategy,
            "temp_sensors": list(self.temp_sensors),
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Device":
        return cls(
            id=raw["id"],
            name=raw["name"],
            host=raw["host"],
            user=raw["user"],
            password=raw.get("password", ""),
            backend=raw.get("backend", "ipmi"),
            info=DeviceInfo.from_dict(raw.get("info")),
            verify_tls=raw.get("verify_tls", False),
            temp_strategy=raw.get("temp_strategy", "max"),
            temp_sensors=list(raw.get("temp_sensors") or []),
        )


@dataclass
class CurvePoint:
    """曲线点 (PLAN §2 curves[].points[])。"""

    temp: float
    pct: int

    def to_dict(self) -> Dict[str, Any]:
        return {"temp": self.temp, "pct": self.pct}

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "CurvePoint":
        return cls(temp=float(raw["temp"]), pct=int(raw["pct"]))


@dataclass
class Curve:
    """温度曲线 (PLAN §2 curves[])。"""

    id: str
    name: str
    mode: str = "linear"  # linear | step
    points: List[CurvePoint] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "mode": self.mode,
            "points": [p.to_dict() for p in self.points],
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Curve":
        points = [CurvePoint.from_dict(p) for p in raw.get("points", [])]
        # 自动按 temp 升序,持久化一致(无论上游传顺序)
        points.sort(key=lambda p: p.temp)
        return cls(
            id=raw["id"],
            name=raw["name"],
            mode=raw.get("mode", "linear"),
            points=points,
        )


@dataclass
class Settings:
    """全局设置 (PLAN §2 settings)。默认值见 default_settings()。"""

    failsafe_enabled: bool = True
    failsafe_temp_c: int = 80
    poll_interval_s: int = 15
    autostart: bool = False
    restore_on_exit: bool = True
    language: str = "auto"  # auto | zh-CN | en
    # 主密码: 空 = 无鉴权 + 启动强制 bind 127.0.0.1 (安全默认)
    # 非空 = 启用鉴权 + 允许 bind_host 任意地址
    master_password: str = field(default="", repr=False)
    # 监听地址: 默认 127.0.0.1 (本地)。设公网地址(0.0.0.0)必须同时设 master_password
    bind_host: str = "127.0.0.1"

    def to_dict(self, *, mask_password_field: bool = False) -> Dict[str, Any]:
        d = asdict(self)
        if mask_password_field:
            d["master_password"] = mask_password(self.master_password)
        return d

    @classmethod
    def from_dict(cls, raw: Optional[Dict[str, Any]]) -> "Settings":
        raw = raw or {}
        defaults = default_settings()
        return cls(
            failsafe_enabled=raw.get("failsafe_enabled", defaults.failsafe_enabled),
            failsafe_temp_c=raw.get("failsafe_temp_c", defaults.failsafe_temp_c),
            poll_interval_s=raw.get("poll_interval_s", defaults.poll_interval_s),
            autostart=raw.get("autostart", defaults.autostart),
            restore_on_exit=raw.get("restore_on_exit", defaults.restore_on_exit),
            language=raw.get("language", defaults.language),
            master_password=raw.get("master_password", defaults.master_password),
            bind_host=raw.get("bind_host", defaults.bind_host),
        )


def default_settings() -> Settings:
    """PLAN §2 默认 settings (failsafe_enabled=True, failsafe_temp_c=80, ...)."""
    return Settings(
        failsafe_enabled=True,
        failsafe_temp_c=80,
        poll_interval_s=15,
        autostart=False,
        restore_on_exit=True,
        language="auto",
        master_password="",
        bind_host="127.0.0.1",
    )


@dataclass
class Notifier:
    """通知器 (PLAN §2 notifiers[])。"""

    id: str
    type: str  # telegram | webhook
    enabled: bool = True
    events: List[str] = field(default_factory=list)
    # config 子结构因 type 而异 (telegram 含 bot_token/chat_id; webhook 含 url/headers/...).
    # 明文存储 → 不在 dataclass 强类型化, 直接透传 dict。
    config: Dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "enabled": self.enabled,
            "events": list(self.events),
            "config": dict(self.config),
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Notifier":
        return cls(
            id=raw["id"],
            type=raw["type"],
            enabled=raw.get("enabled", True),
            events=list(raw.get("events", [])),
            config=dict(raw.get("config", {})),
        )


@dataclass
class Config:
    """顶层 Config (PLAN §2)。"""

    version: int = CONFIG_VERSION
    devices: List[Device] = field(default_factory=list)
    curves: List[Curve] = field(default_factory=list)
    # assignments: device_id -> curve_id
    assignments: Dict[str, str] = field(default_factory=dict)
    settings: Settings = field(default_factory=default_settings)
    notifiers: List[Notifier] = field(default_factory=list)

    def to_dict(self, *, mask_password_field: bool = False) -> Dict[str, Any]:
        return {
            "version": self.version,
            "devices": [d.to_dict(mask_password_field=mask_password_field) for d in self.devices],
            "curves": [c.to_dict() for c in self.curves],
            "assignments": dict(self.assignments),
            "settings": self.settings.to_dict(mask_password_field=mask_password_field),
            "notifiers": [n.to_dict() for n in self.notifiers],
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Config":
        return cls(
            version=int(raw.get("version", CONFIG_VERSION)),
            devices=[Device.from_dict(d) for d in raw.get("devices", [])],
            curves=[Curve.from_dict(c) for c in raw.get("curves", [])],
            assignments=dict(raw.get("assignments", {})),
            settings=Settings.from_dict(raw.get("settings")),
            notifiers=[Notifier.from_dict(n) for n in raw.get("notifiers", [])],
        )


# ---------------------------------------------------------------------------
# 读 / 写 / 迁移
# ---------------------------------------------------------------------------


def _default_config() -> Config:
    """空 Config v2, 默认 settings, 其余空集合。"""
    return Config(
        version=CONFIG_VERSION,
        devices=[],
        curves=[],
        assignments={},
        settings=default_settings(),
        notifiers=[],
    )


def load(path: Path) -> Config:
    """从 JSON 读 Config; 文件不存在则返回默认空 Config v2。

    若 version != 2, 透传 migrate() 处理。
    """
    path = Path(path)
    if not path.exists():
        return _default_config()
    with path.open("r", encoding="utf-8") as fp:
        raw = json.load(fp)
    if not isinstance(raw, dict):
        raise ValueError(
            f"config.json root must be a JSON object, got {type(raw).__name__}"
        )
    return migrate(raw)


def save(cfg: Config, path: Path) -> None:
    """原子写 JSON + 自动设权限。

    步骤:
        1. 写到同目录临时文件 (NamedTemporaryFile)。
        2. os.replace 原子替换目标。
        3. 类 Unix: chmod 0o600; Windows: ACL stub。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2)

    # NamedTemporaryFile 放在同目录, 避免跨文件系统 os.replace 失败。
    fd, tmp_path = tempfile.mkstemp(
        prefix=".config.", suffix=".tmp", dir=str(path.parent)
    )
    tmp = Path(tmp_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            fp.write(payload)
        os.replace(tmp, path)
    except Exception:
        # 清理临时文件 (若 replace 已发生则 tmp 已不存在)
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise

    _restrict_perms(path)


def _restrict_perms(path: Path) -> None:
    """类 Unix: chmod 0o600; Windows: 调 _set_acl_owner_only stub。"""
    if sys.platform.startswith("win"):
        _set_acl_owner_only(path)
    else:
        try:
            os.chmod(path, 0o600)
        except OSError:
            # 即使 chmod 失败也不应让 save 整体崩溃; 调用方可自检。
            # PLAN §6 决策: 权限是"挡同机其他用户顺手查看", 非真攻击者防护。
            pass


def _set_acl_owner_only(path: Path) -> None:
    """Windows ACL: 收紧到当前用户。

    TODO: 用 win32security (pywin32) 或 ctypes 真正实现 (PLAN §6)。
    当前 stub 行为 = 不报错、不动作, 避免在无 pywin32 环境下崩溃。
    """
    # TODO(M2.1): 用 win32security.SetNamedSecurityInfo 限制到 SID 当前用户。
    return None


def migrate(raw: Dict[str, Any]) -> Config:
    """版本迁移分发。

    - version == 2: 直接 from_dict。
    - version 缺失 / == 1: stub 1→2 (项目从 v2 起, 实际无升级路径)。
      行为 = 补默认字段后转 v2。最保守。
    - 其他 (未来未知版本): NotImplementedError。
    """
    version = raw.get("version")
    if version is None or version == 1:
        # 1→2 stub: 项目从 v2 起步, v1 schema 实际不存在。
        # 兜底: 把 raw 当作 v2 部分字段, 缺失字段用默认填充。
        upgraded = dict(raw)
        upgraded["version"] = CONFIG_VERSION
        upgraded.setdefault("devices", [])
        upgraded.setdefault("curves", [])
        upgraded.setdefault("assignments", {})
        upgraded.setdefault("settings", default_settings().to_dict())
        upgraded.setdefault("notifiers", [])
        return Config.from_dict(upgraded)
    if version == CONFIG_VERSION:
        return Config.from_dict(raw)
    raise NotImplementedError(
        f"unknown future config version: {version!r} (current = {CONFIG_VERSION})"
    )
