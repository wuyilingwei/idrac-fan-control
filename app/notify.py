"""通知子系统 — PLAN §7。

事件类型 (PLAN §7.2):
    overtemp_alert / failsafe_trip / connection_lost / command_failed

通知器类型:
    telegram: 预设 Telegram sendMessage(只需 bot_token + chat_id)。
    webhook:  通用 GET/POST,可配 method/url/headers/body_template,占位符渲染。

占位符 (PLAN §7.3):
    {message} {server_name} {server_host} {event}
    {temp} {threshold} {timestamp} {device_id} {device_name} {device_host}

接口:
    make_dispatcher(cfg) -> NotifyFn
        返回符合 app.engine.ControlLoop.notify_fn 签名的 async 函数,
        遍历 cfg.notifiers 并行分发(asyncio.gather)。

安全:
    凭据(bot_token / secret headers)绝不入 log;
    异常仅 WARN log,不抛出(PLAN §7.4 警告)。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Dict, Mapping, Optional

import httpx

from app.config import Config, Notifier

log = logging.getLogger(__name__)

NotifyFn = Callable[[str, Dict[str, Any]], Awaitable[None]]
ClientFactory = Callable[[], httpx.AsyncClient]

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
DEFAULT_TIMEOUT_S = 10.0
DEFAULT_BODY_TEMPLATE = "{message}"


def _render(template: str, ctx: Mapping[str, Any]) -> str:
    """简单 {key} 占位符替换。未知 key 保留 {key} 字面便于调试。"""
    out = template
    for k, v in ctx.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def _enrich_ctx(event: str, ctx: Mapping[str, Any]) -> Dict[str, Any]:
    """补全 PLAN §7.3 占位符上下文。server_* 是 device_* 的别名。"""
    enriched: Dict[str, Any] = dict(ctx)
    enriched.setdefault("event", event)
    enriched.setdefault("timestamp", int(time.time()))
    enriched.setdefault("server_name", enriched.get("device_name", ""))
    enriched.setdefault("server_host", enriched.get("device_host", ""))
    if "message" not in enriched:
        parts = [f"[{event}]"]
        if enriched.get("device_name"):
            parts.append(str(enriched["device_name"]))
        if enriched.get("temp") is not None:
            parts.append(f"{enriched['temp']}°C")
        if enriched.get("error"):
            parts.append(f"err={enriched['error']}")
        enriched["message"] = " ".join(parts)
    return enriched


async def dispatch_one(
    notifier: Notifier,
    event: str,
    ctx: Mapping[str, Any],
    *,
    client: httpx.AsyncClient,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> None:
    """单个 notifier 分发。enabled=False / event 不订阅 → 跳过;异常仅 WARN。"""
    if not notifier.enabled:
        return
    if event not in notifier.events:
        return
    cfg = notifier.config
    enriched = _enrich_ctx(event, ctx)
    try:
        if notifier.type == "telegram":
            token = cfg["bot_token"]
            chat_id = cfg["chat_id"]
            await client.post(
                TELEGRAM_API.format(token=token),
                json={"chat_id": chat_id, "text": enriched["message"]},
                timeout=timeout,
            )
        elif notifier.type == "webhook":
            method = str(cfg.get("method", "POST")).upper()
            url = _render(str(cfg["url"]), enriched)
            headers = {
                k: _render(str(v), enriched)
                for k, v in (cfg.get("headers") or {}).items()
            }
            if method == "GET":
                await client.get(url, headers=headers, timeout=timeout)
            else:
                body = _render(
                    str(cfg.get("body_template", DEFAULT_BODY_TEMPLATE)), enriched
                )
                await client.post(url, content=body, headers=headers, timeout=timeout)
        else:
            log.warning(
                "unknown notifier type: id=%s type=%s", notifier.id, notifier.type
            )
    except Exception as exc:  # pylint: disable=broad-except
        log.warning(
            "notify dispatch failed: id=%s event=%s err=%s",
            notifier.id,
            event,
            exc,
        )


def make_dispatcher(
    cfg: Config,
    *,
    client_factory: Optional[ClientFactory] = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> NotifyFn:
    """构造 NotifyFn 闭包:遍历 cfg.notifiers 并行分发。

    client_factory: 测试用 MockTransport 注入;默认 lambda: httpx.AsyncClient()。
    生产长连接复用交给 M5 集成层,M4 阶段每次新建保持简单。
    """

    async def _dispatch(event: str, ctx: Dict[str, Any]) -> None:
        notifiers = cfg.notifiers
        if not notifiers:
            return
        factory: ClientFactory = client_factory or (lambda: httpx.AsyncClient())
        async with factory() as client:
            await asyncio.gather(
                *(
                    dispatch_one(n, event, ctx, client=client, timeout=timeout)
                    for n in notifiers
                ),
                return_exceptions=True,
            )

    return _dispatch
