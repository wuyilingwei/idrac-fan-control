"""Redfish 监控 + redfish_oem 控制骨架 (PLAN.md §5.2 / §5.3)。

监控路径 (R730 / iDRAC9+ 通用):
    GET /redfish/v1/Managers/iDRAC.Embedded.1       → 取 FirmwareVersion (能力探测)
    GET /redfish/v1/Systems/System.Embedded.1       → 取 Model / SKU (ServiceTag)
    GET /redfish/v1/Chassis/System.Embedded.1/Thermal → 取 Temperatures / Fans

控制路径 (M8 阻塞: 需 iDRAC9+ 真机):
    set_fan_oem(pct): 当前 NotImplementedError, 字段待真机验证。

设计原则:
    - httpx.Client, 默认 verify=False (iDRAC 默认自签证书) + timeout=10。
    - basic auth 走 httpx auth 元组, 不拼到 URL, 不打日志。
    - 类支持 with 语句 (__enter__/__exit__), 用完即释放连接池。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx


# Dell iDRAC Redfish 标准端点路径常量
PATH_MANAGER = "/redfish/v1/Managers/iDRAC.Embedded.1"
PATH_SYSTEM = "/redfish/v1/Systems/System.Embedded.1"
PATH_THERMAL = "/redfish/v1/Chassis/System.Embedded.1/Thermal"

DEFAULT_TIMEOUT_S = 10.0


class RedfishClient:
    """httpx.Client 包装 — 监控 + redfish_oem 控制骨架。

    凭据透传到 httpx auth 元组, 不拼到 URL, 不打印 / 不记录。

    Args:
        host: iDRAC IP 或 hostname (不含 scheme)。
        user: iDRAC 用户名 (默认 root)。
        password: iDRAC 密码。
        verify_tls: TLS 校验开关 (默认 False, 适配 iDRAC 自签证书)。
        timeout: 单次请求超时秒数 (默认 10s)。
        transport: 可选 httpx Transport, 单测可注入 MockTransport。
    """

    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        verify_tls: bool = False,
        timeout: float = DEFAULT_TIMEOUT_S,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._host = host
        # base_url 用 https (iDRAC 默认 443 + 自签证书)
        self._base_url = f"https://{host}"
        self._client = httpx.Client(
            base_url=self._base_url,
            auth=(user, password),
            verify=verify_tls,
            timeout=timeout,
            transport=transport,
        )

    # ---------------- 上下文管理 ----------------

    def __enter__(self) -> "RedfishClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # ---------------- 监控 GET ----------------

    def _get_json(self, path: str) -> Dict[str, Any]:
        """统一 GET, 失败抛 httpx.HTTPStatusError; 返回 JSON dict。"""
        rsp = self._client.get(path)
        rsp.raise_for_status()
        return rsp.json()

    def get_manager(self) -> Dict[str, Any]:
        """GET Managers/iDRAC.Embedded.1 — 含 FirmwareVersion 等。"""
        return self._get_json(PATH_MANAGER)

    def get_system(self) -> Dict[str, Any]:
        """GET Systems/System.Embedded.1 — 含 Model / SKU (ServiceTag) 等。"""
        return self._get_json(PATH_SYSTEM)

    def get_thermal(self) -> Dict[str, Any]:
        """GET Chassis/System.Embedded.1/Thermal — 含 Temperatures / Fans。"""
        return self._get_json(PATH_THERMAL)

    # ---------------- 控制 (骨架) ----------------

    def set_fan_oem(self, pct: int) -> Dict[str, Any]:
        """Dell Redfish OEM 风扇转速下发 — 接口骨架。

        ⚠️ 当前抛 NotImplementedError, 等 iDRAC9+ 真机验证后补字段。
        参考: PLAN.md §5.3 已知风险清单。
        """
        # TODO: 待 iDRAC9+ 真机验证字段 (PLAN §5.3)
        # 候选 PATCH /redfish/v1/Managers/.../Oem/Dell/... 字段 Dell 在不同
        # iDRAC9 固件版本间漂移, 无真机不假装可用。
        raise NotImplementedError(
            "redfish_oem 控制路径需 iDRAC9+ 真机字段验证 (PLAN §5.3)"
        )
