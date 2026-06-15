"""ServiceContainer — 装载 Config + ControlLoop + Dispatcher,跑后台轮询 — PLAN §1.1 / §10。

启动:`await container.start()`(由 Starlette lifespan 调用)→ 启动后台 tick 循环。
关闭:`await container.stop()` → cancel + aclose + restore_on_exit。

写操作互斥:`container.lock`(`asyncio.Lock`)— API 改 config 时持锁,save + chmod + 刷新 ControlLoop。
测试:`auto_start=False` 禁用后台循环,API 路由仍可手动 `tick_once()`。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional

from app.config import Config, load, save
from app.engine import BackendFactory, ControlLoop, TickResult
from app.notify import NotifyFn, make_dispatcher

log = logging.getLogger(__name__)


def _stub_backend_factory(device):
    raise NotImplementedError(
        f"backend not configured for device {device.id} (backend={device.backend}); "
        "M5 集成时按 device.backend 选 IPMI/Redfish"
    )


def _default_backend_factory_with_cache():
    """生产默认 factory:device.backend → IpmiBackend / RedfishOemBackend,缓存按 device.id 复用实例。

    缓存在 _refresh_loop() 时由 ServiceContainer 清理(配置变更后 device 可能换 host)。
    """
    cache: dict = {}

    def factory(device):
        cached = cache.get(device.id)
        if cached is not None and getattr(cached, "_host", None) == device.host:
            return cached
        from app.idrac.backends import build_backend
        backend = build_backend(device)
        cache[device.id] = backend
        return backend

    factory.cache = cache  # type: ignore[attr-defined]
    return factory


class ServiceContainer:
    """API 路由 / lifespan 共用的服务容器。"""

    def __init__(
        self,
        cfg_path: Path,
        *,
        backend_factory: Optional[BackendFactory] = None,
        poll_interval_override: Optional[float] = None,
        auto_start: bool = True,
    ) -> None:
        self.cfg_path = cfg_path
        self.cfg: Config = load(cfg_path)
        self._lock: Optional[asyncio.Lock] = None  # lazy: Py3.9 要求在 loop 内创建
        self.backend_factory: BackendFactory = (
            backend_factory or _stub_backend_factory
        )
        self.dispatcher: NotifyFn = make_dispatcher(self.cfg)
        self.last_tick: Dict[str, TickResult] = {}
        self._task: Optional[asyncio.Task] = None
        self._poll_interval_override = poll_interval_override
        self.auto_start = auto_start
        self.loop = ControlLoop(
            self.cfg,
            notify_fn=self.dispatcher,
            backend_factory=self.backend_factory,
        )

    @property
    def lock(self) -> asyncio.Lock:
        """Lazy Lock: Py3.9 要求在 event loop 内构造 — 第一次访问时(必在 async context)创建。"""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _refresh_loop(self) -> None:
        """配置变更后刷新 dispatcher 和 ControlLoop 内部缓存。"""
        self.dispatcher = make_dispatcher(self.cfg)
        self.loop.cfg = self.cfg
        self.loop._curves_by_id = {c.id: c for c in self.cfg.curves}
        self.loop.notify_fn = self.dispatcher

    async def save_cfg(self) -> None:
        """同步:外部已改 self.cfg(in-place),持锁 save + refresh。"""
        async with self.lock:
            save(self.cfg, self.cfg_path)
            self._refresh_loop()

    async def replace_cfg(self, new_cfg: Config) -> None:
        async with self.lock:
            self.cfg = new_cfg
            save(self.cfg, self.cfg_path)
            self._refresh_loop()

    async def tick_once(self) -> Dict[str, TickResult]:
        out = await self.loop.tick()
        self.last_tick = out
        return out

    async def _run_loop(self) -> None:
        try:
            while True:
                try:
                    out = await self.loop.tick()
                    self.last_tick = out
                except Exception as exc:  # pylint: disable=broad-except
                    log.exception("service tick error: %s", exc)
                interval = (
                    self._poll_interval_override
                    if self._poll_interval_override is not None
                    else self.cfg.settings.poll_interval_s
                )
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            log.info("service loop cancelled")
            raise

    async def start(self) -> None:
        """启动后台 tick 循环。auto_start=False 时 no-op。"""
        if not self.auto_start:
            return
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """取消循环 + 等待 dispatcher 清理 + restore_on_exit(PLAN §12)。"""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.loop.aclose()
        if self.cfg.settings.restore_on_exit:
            for device in self.cfg.devices:
                try:
                    backend = self.backend_factory(device)
                    backend.set_auto_mode(device)
                except Exception as exc:  # pylint: disable=broad-except
                    log.warning(
                        "restore_on_exit failed device=%s: %s", device.id, exc
                    )
