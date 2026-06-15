"""Starlette API — PLAN §1.1 / §10。

入口:
    build_app(container: ServiceContainer) -> Starlette

路由(全 /api/*):
    GET   /api/health
    GET/PUT /api/config                              整体配置读/写
    GET/POST /api/devices                            设备列表 / 创建
    GET/PUT/DELETE /api/devices/{device_id}          设备 CRUD
    GET/POST /api/curves                             曲线列表 / 创建
    GET/PUT/DELETE /api/curves/{curve_id}            曲线 CRUD
    GET /api/assignments                             分配表
    PUT /api/assignments/{device_id}  body={"curve_id": str|null}  null=移除
    GET/PUT /api/settings                            全局设置(PUT 部分更新)
    GET /api/status                                  最近一次 tick 结果
    POST /api/devices/{device_id}/fan/manual  body={"pct": int}
    POST /api/devices/{device_id}/fan/auto           交还 Dell 自动
    POST /api/devices/{device_id}/probe              触发能力探测(同步,放 to_thread)
    POST /api/notifiers/test  body={"notifier_id": str, "event": str, "ctx"?: dict}
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import httpx
import os
import secrets
from pathlib import Path as _Path
from typing import Set

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles


# ---------- 简单认证 ----------
# 主密码存 settings.master_password(空 = 无鉴权 + 强制 bind 127.0.0.1)。
# 在 Settings UI 可改;改完重启生效 bind_host,master_password 立即生效。
# token 进程级 in-memory,重启失效。
AUTH_WHITELIST = {"/api/health", "/api/auth/login", "/api/auth/status"}
_VALID_TOKENS: Set[str] = set()


def _auth_password(request: Request) -> str:
    """从 container.cfg.settings 动态取主密码。"""
    try:
        return request.app.state.container.cfg.settings.master_password or ""
    except AttributeError:
        return ""


def _auth_enabled(request: Request) -> bool:
    return bool(_auth_password(request))


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not _auth_enabled(request):
            return await call_next(request)
        path = request.url.path
        if not path.startswith("/api/") or path in AUTH_WHITELIST:
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] not in _VALID_TOKENS:
            return JSONResponse({"detail": "auth required"}, status_code=401)
        return await call_next(request)


async def post_auth_login(request: Request) -> JSONResponse:
    if not _auth_enabled(request):
        return JSONResponse({"token": "", "auth_required": False})
    raw = await request.json()
    pw = raw.get("password", "")
    if pw != _auth_password(request):
        raise HTTPException(status_code=401, detail="invalid password")
    token = secrets.token_hex(24)
    _VALID_TOKENS.add(token)
    return JSONResponse({"token": token, "auth_required": True})


async def post_auth_logout(request: Request) -> JSONResponse:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        _VALID_TOKENS.discard(auth[7:])
    return JSONResponse({"status": "ok"})


async def get_auth_status(request: Request) -> JSONResponse:
    return JSONResponse({"auth_required": _auth_enabled(request)})

from app.config import (
    Curve,
    Device,
    Settings,
    is_masked_password,
    mask_password,
    save,
)
from app.config import Config as ConfigDataclass


def _resolve_device_password(new_pw: str, old: Optional[Device]) -> str:
    """如果新传入的 password 是 mask 形态(且与旧值的 mask 一致),沿用旧 password;否则用新值。"""
    if old is not None and is_masked_password(new_pw) and new_pw == mask_password(old.password):
        return old.password
    return new_pw
from app.service import ServiceContainer

log = logging.getLogger(__name__)


# ---------- helpers ----------


def _container(request: Request) -> ServiceContainer:
    return request.app.state.container


def _tick_to_dict(tr) -> Dict[str, Any]:
    return {
        "device_id": tr.device_id,
        "temp": tr.temp,
        "target_pct": tr.target_pct,
        "status": tr.status,
    }


def _device_or_404(container: ServiceContainer, dev_id: str) -> Device:
    for d in container.cfg.devices:
        if d.id == dev_id:
            return d
    raise HTTPException(status_code=404, detail=f"device id {dev_id!r} not found")


def _curve_or_404(container: ServiceContainer, curve_id: str) -> Curve:
    for c in container.cfg.curves:
        if c.id == curve_id:
            return c
    raise HTTPException(status_code=404, detail=f"curve id {curve_id!r} not found")


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


# ---------- routes: 健康 / config ----------


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "version": 2})


async def get_config(request: Request) -> JSONResponse:
    return JSONResponse(_container(request).cfg.to_dict(mask_password_field=True))


async def put_config(request: Request) -> JSONResponse:
    raw = await request.json()
    try:
        new_cfg = ConfigDataclass.from_dict(raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise _bad_request(f"invalid config: {exc}")
    container = _container(request)
    # 整体替换时,逐设备处理 mask 占位:若传入 password 是旧值的 mask 形态,沿用旧值
    old_by_id = {d.id: d for d in container.cfg.devices}
    for d in new_cfg.devices:
        d.password = _resolve_device_password(d.password, old_by_id.get(d.id))
    await container.replace_cfg(new_cfg)
    return JSONResponse(new_cfg.to_dict(mask_password_field=True))


# ---------- routes: devices ----------


async def get_devices(request: Request) -> JSONResponse:
    return JSONResponse(
        [d.to_dict(mask_password_field=True) for d in _container(request).cfg.devices]
    )


async def post_device(request: Request) -> JSONResponse:
    raw = await request.json()
    try:
        new_d = Device.from_dict(raw)
    except (KeyError, TypeError) as exc:
        raise _bad_request(f"invalid device: {exc}")
    container = _container(request)
    if any(d.id == new_d.id for d in container.cfg.devices):
        raise HTTPException(status_code=409, detail=f"device id {new_d.id!r} exists")
    # 新增设备不应该传 mask 占位(无旧值可恢复);若传了,直接落明文(信任用户)
    async with container.lock:
        container.cfg.devices.append(new_d)
        save(container.cfg, container.cfg_path)
        container._refresh_loop()
    return JSONResponse(new_d.to_dict(mask_password_field=True), status_code=201)


async def get_device(request: Request) -> JSONResponse:
    d = _device_or_404(_container(request), request.path_params["device_id"])
    return JSONResponse(d.to_dict(mask_password_field=True))


async def put_device(request: Request) -> JSONResponse:
    container = _container(request)
    dev_id = request.path_params["device_id"]
    old = _device_or_404(container, dev_id)
    raw = await request.json()
    try:
        updated = Device.from_dict({**raw, "id": dev_id})
    except (KeyError, TypeError) as exc:
        raise _bad_request(f"invalid device: {exc}")
    # 如果前端回传的是 mask 占位,保留原 password 不被覆盖
    updated.password = _resolve_device_password(updated.password, old)
    async with container.lock:
        container.cfg.devices = [
            updated if d.id == dev_id else d for d in container.cfg.devices
        ]
        save(container.cfg, container.cfg_path)
        container._refresh_loop()
    return JSONResponse(updated.to_dict(mask_password_field=True))


async def delete_device(request: Request) -> JSONResponse:
    container = _container(request)
    dev_id = request.path_params["device_id"]
    _device_or_404(container, dev_id)
    async with container.lock:
        container.cfg.devices = [
            d for d in container.cfg.devices if d.id != dev_id
        ]
        container.cfg.assignments.pop(dev_id, None)
        save(container.cfg, container.cfg_path)
        container._refresh_loop()
    return JSONResponse({"deleted": dev_id})


# ---------- routes: curves ----------


async def get_curves(request: Request) -> JSONResponse:
    return JSONResponse([c.to_dict() for c in _container(request).cfg.curves])


async def post_curve(request: Request) -> JSONResponse:
    raw = await request.json()
    try:
        new_c = Curve.from_dict(raw)
    except (KeyError, TypeError) as exc:
        raise _bad_request(f"invalid curve: {exc}")
    container = _container(request)
    if any(c.id == new_c.id for c in container.cfg.curves):
        raise HTTPException(status_code=409, detail=f"curve id {new_c.id!r} exists")
    async with container.lock:
        container.cfg.curves.append(new_c)
        save(container.cfg, container.cfg_path)
        container._refresh_loop()
    return JSONResponse(new_c.to_dict(), status_code=201)


async def get_curve(request: Request) -> JSONResponse:
    c = _curve_or_404(_container(request), request.path_params["curve_id"])
    return JSONResponse(c.to_dict())


async def put_curve(request: Request) -> JSONResponse:
    container = _container(request)
    curve_id = request.path_params["curve_id"]
    _curve_or_404(container, curve_id)
    raw = await request.json()
    try:
        updated = Curve.from_dict({**raw, "id": curve_id})
    except (KeyError, TypeError) as exc:
        raise _bad_request(f"invalid curve: {exc}")
    async with container.lock:
        container.cfg.curves = [
            updated if c.id == curve_id else c for c in container.cfg.curves
        ]
        save(container.cfg, container.cfg_path)
        container._refresh_loop()
    return JSONResponse(updated.to_dict())


async def delete_curve(request: Request) -> JSONResponse:
    container = _container(request)
    curve_id = request.path_params["curve_id"]
    _curve_or_404(container, curve_id)
    async with container.lock:
        container.cfg.curves = [
            c for c in container.cfg.curves if c.id != curve_id
        ]
        # 分配过这条曲线的 device 移除分配
        container.cfg.assignments = {
            k: v for k, v in container.cfg.assignments.items() if v != curve_id
        }
        save(container.cfg, container.cfg_path)
        container._refresh_loop()
    return JSONResponse({"deleted": curve_id})


# ---------- routes: assignments ----------


async def get_assignments(request: Request) -> JSONResponse:
    return JSONResponse(_container(request).cfg.assignments)


async def put_assignment(request: Request) -> JSONResponse:
    container = _container(request)
    dev_id = request.path_params["device_id"]
    _device_or_404(container, dev_id)
    raw = await request.json()
    curve_id = raw.get("curve_id")
    if curve_id is not None:
        _curve_or_404(container, curve_id)
    async with container.lock:
        if curve_id is None:
            container.cfg.assignments.pop(dev_id, None)
        else:
            container.cfg.assignments[dev_id] = curve_id
        save(container.cfg, container.cfg_path)
        container._refresh_loop()
    return JSONResponse({dev_id: curve_id})


# ---------- routes: settings ----------


async def get_settings(request: Request) -> JSONResponse:
    return JSONResponse(
        _container(request).cfg.settings.to_dict(mask_password_field=True)
    )


async def put_settings(request: Request) -> JSONResponse:
    container = _container(request)
    raw = await request.json()
    if not isinstance(raw, dict):
        raise _bad_request("settings body must be object")
    old_settings = container.cfg.settings
    merged = old_settings.to_dict()  # 不 mask,内部 merge 用真值
    merged.update(raw)
    # 若前端回传 master_password 是旧值的 mask 形态 → 沿用旧值,不覆盖
    new_pw = merged.get("master_password", "")
    if is_masked_password(new_pw) and new_pw == mask_password(old_settings.master_password):
        merged["master_password"] = old_settings.master_password
    try:
        new_settings = Settings.from_dict(merged)
    except (KeyError, TypeError) as exc:
        raise _bad_request(f"invalid settings: {exc}")
    # 安全约束:无主密码强制 bind 127.0.0.1
    if not new_settings.master_password and new_settings.bind_host not in {"127.0.0.1", "localhost", "::1"}:
        raise _bad_request(
            "bind_host 必须为 127.0.0.1/localhost/::1,除非设置 master_password"
        )
    async with container.lock:
        container.cfg.settings = new_settings
        save(container.cfg, container.cfg_path)
        container._refresh_loop()
    return JSONResponse(new_settings.to_dict(mask_password_field=True))


# ---------- routes: status ----------


async def get_status(request: Request) -> JSONResponse:
    container = _container(request)
    return JSONResponse(
        {
            "last_tick": {
                k: _tick_to_dict(v) for k, v in container.last_tick.items()
            },
            "devices": [d.id for d in container.cfg.devices],
        }
    )


# ---------- routes: fan 控制 / probe / notifier 测试 ----------


async def post_fan_manual(request: Request) -> JSONResponse:
    container = _container(request)
    dev_id = request.path_params["device_id"]
    device = _device_or_404(container, dev_id)
    raw = await request.json()
    pct = raw.get("pct")
    if not isinstance(pct, int) or isinstance(pct, bool):
        raise _bad_request("pct must be int")
    if pct < 0 or pct > 100:
        raise _bad_request("pct must be in [0, 100]")
    try:
        backend = container.backend_factory(device)
        if hasattr(backend, "set_manual_mode"):
            backend.set_manual_mode(device)
        backend.set_fan_percent(device, pct)
    except NotImplementedError as exc:
        raise HTTPException(status_code=503, detail=f"backend unavailable: {exc}")
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=502, detail=f"backend error: {exc}")
    return JSONResponse({"device_id": dev_id, "pct": pct, "status": "ok"})


async def post_fan_auto(request: Request) -> JSONResponse:
    container = _container(request)
    dev_id = request.path_params["device_id"]
    device = _device_or_404(container, dev_id)
    try:
        backend = container.backend_factory(device)
        backend.set_auto_mode(device)
    except NotImplementedError as exc:
        raise HTTPException(status_code=503, detail=f"backend unavailable: {exc}")
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=502, detail=f"backend error: {exc}")
    return JSONResponse({"device_id": dev_id, "status": "auto"})


async def get_device_sensors(request: Request) -> JSONResponse:
    """返回当前设备所有 temp / fan 传感器名,前端做 select 策略选择列表用。"""
    container = _container(request)
    dev_id = request.path_params["device_id"]
    device = _device_or_404(container, dev_id)
    try:
        backend = container.backend_factory(device)
        if not hasattr(backend, "read_sensors"):
            raise HTTPException(
                status_code=501, detail="backend does not expose read_sensors"
            )
        report = await asyncio.to_thread(backend.read_sensors, device)
    except NotImplementedError as exc:
        raise HTTPException(status_code=503, detail=f"backend unavailable: {exc}")
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=502, detail=f"backend error: {exc}")
    return JSONResponse(
        {
            "temps": [{"name": t["name"], "value_c": t["value_c"]} for t in report.get("temps", [])],
            "fans": [{"name": f["name"], "rpm": f["rpm"]} for f in report.get("fans", [])],
        }
    )


async def post_probe(request: Request) -> JSONResponse:
    container = _container(request)
    dev_id = request.path_params["device_id"]
    device = _device_or_404(container, dev_id)
    try:
        from app.idrac.probe import probe

        info = await asyncio.to_thread(
            probe, device.host, device.user, device.password, device.verify_tls
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=503, detail=f"probe unavailable: {exc}")
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=502, detail=f"probe failed: {exc}")
    async with container.lock:
        for d in container.cfg.devices:
            if d.id == dev_id:
                d.info = info
                break
        save(container.cfg, container.cfg_path)
    return JSONResponse(info.to_dict())


async def post_notifier_test(request: Request) -> JSONResponse:
    container = _container(request)
    raw = await request.json()
    notifier_id = raw.get("notifier_id")
    event = raw.get("event", "overtemp_alert")
    ctx = raw.get("ctx") or {}
    notifier = next(
        (n for n in container.cfg.notifiers if n.id == notifier_id), None
    )
    if notifier is None:
        raise HTTPException(
            status_code=404, detail=f"notifier id {notifier_id!r} not found"
        )
    from app.notify import dispatch_one

    async with httpx.AsyncClient() as client:
        await dispatch_one(notifier, event, ctx, client=client)
    return JSONResponse(
        {"notifier_id": notifier_id, "event": event, "status": "dispatched"}
    )


# ---------- routes 表 + 工厂 ----------


routes: List[Route] = [
    Route("/api/health", health, methods=["GET"]),
    Route("/api/auth/status", get_auth_status, methods=["GET"]),
    Route("/api/auth/login", post_auth_login, methods=["POST"]),
    Route("/api/auth/logout", post_auth_logout, methods=["POST"]),
    Route("/api/config", get_config, methods=["GET"]),
    Route("/api/config", put_config, methods=["PUT"]),
    Route("/api/devices", get_devices, methods=["GET"]),
    Route("/api/devices", post_device, methods=["POST"]),
    Route("/api/devices/{device_id}", get_device, methods=["GET"]),
    Route("/api/devices/{device_id}", put_device, methods=["PUT"]),
    Route("/api/devices/{device_id}", delete_device, methods=["DELETE"]),
    Route("/api/curves", get_curves, methods=["GET"]),
    Route("/api/curves", post_curve, methods=["POST"]),
    Route("/api/curves/{curve_id}", get_curve, methods=["GET"]),
    Route("/api/curves/{curve_id}", put_curve, methods=["PUT"]),
    Route("/api/curves/{curve_id}", delete_curve, methods=["DELETE"]),
    Route("/api/assignments", get_assignments, methods=["GET"]),
    Route("/api/assignments/{device_id}", put_assignment, methods=["PUT"]),
    Route("/api/settings", get_settings, methods=["GET"]),
    Route("/api/settings", put_settings, methods=["PUT"]),
    Route("/api/status", get_status, methods=["GET"]),
    Route(
        "/api/devices/{device_id}/fan/manual",
        post_fan_manual,
        methods=["POST"],
    ),
    Route(
        "/api/devices/{device_id}/fan/auto",
        post_fan_auto,
        methods=["POST"],
    ),
    Route("/api/devices/{device_id}/sensors", get_device_sensors, methods=["GET"]),
    Route("/api/devices/{device_id}/probe", post_probe, methods=["POST"]),
    Route("/api/notifiers/test", post_notifier_test, methods=["POST"]),
]


def _make_lifespan(container: ServiceContainer):
    @asynccontextmanager
    async def lifespan(app: Starlette):
        await container.start()
        try:
            yield
        finally:
            await container.stop()

    return lifespan


def build_app(
    container: ServiceContainer,
    *,
    cors_origins: Optional[List[str]] = None,
    static_dir: Optional[str] = None,
) -> Starlette:
    """构造 Starlette app。

    static_dir: 若提供且目录存在,挂载 `/` → StaticFiles(html=True),
      用于托管 M6 前端 build 产物(`frontend` 跑 `npm run build` 后输出到 app/static/)。
      None 或目录不存在 → 跳过(API only,前端走 vite dev server)。
    """
    cors = cors_origins if cors_origins is not None else ["*"]
    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=cors,
            allow_methods=["*"],
            allow_headers=["*"],
        ),
        Middleware(AuthMiddleware),
    ]
    final_routes = list(routes)
    if static_dir and _Path(static_dir).is_dir():
        # /api/* 在前匹配优先;Mount("/", ...) 兜底所有未匹配路径
        final_routes.append(
            Mount("/", app=StaticFiles(directory=static_dir, html=True), name="static")
        )
    app = Starlette(
        routes=final_routes,
        middleware=middleware,
        lifespan=_make_lifespan(container),
    )
    app.state.container = container
    return app
