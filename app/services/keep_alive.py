"""Keeps a sleeping host awake.

Render's free instances stop after about fifteen minutes without a request from outside, and the next visitor
waits half a minute for the process to start again. A request to the service's own public address counts as
traffic, so the process asks for its own /api/health a little more often than that.

It only runs where a public address is known: RENDER_EXTERNAL_URL (Render sets it by itself) or KEEP_ALIVE_URL.
On a developer's computer neither exists and nothing is started. It cannot wake a process that is already
stopped; for that the host needs a monitor outside it (docs/DEPLOYMENT.md).
"""

import asyncio
import logging
import urllib.error
import urllib.request

from app.core.config import Settings

logger = logging.getLogger(__name__)

HEALTH_PATH = "/api/health"
_TIMEOUT_SECONDS = 20
#: The first request waits for the server to be listening.
_FIRST_DELAY_SECONDS = 45


def keep_alive_target(settings: Settings) -> str | None:
    """The address to ask, or None when there is nothing to keep awake."""
    if not settings.keep_alive_enabled:
        return None
    base = settings.keep_alive_url or settings.render_external_url
    if base is None:
        return None
    return str(base).rstrip("/") + HEALTH_PATH


def _ping(url: str) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": "smartcattle-keep-alive"})  # noqa: S310 (configured https address)
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310
        status: int = response.status
        return status


async def keep_alive_loop(url: str, every_seconds: float, first_delay: float = _FIRST_DELAY_SECONDS) -> None:
    """Asks for the health check for as long as the process lives. A failed request is logged, never fatal."""
    await asyncio.sleep(first_delay)
    while True:
        try:
            status = await asyncio.to_thread(_ping, url)
            logger.debug("keep-alive %s -> %s", url, status)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            logger.warning("keep-alive request failed: %s", type(error).__name__)
        await asyncio.sleep(every_seconds)


def start_keep_alive(settings: Settings) -> asyncio.Task[None] | None:
    url = keep_alive_target(settings)
    if url is None:
        return None
    logger.info("keep-alive on: %s every %s minutes", url, settings.keep_alive_minutes)
    return asyncio.create_task(keep_alive_loop(url, settings.keep_alive_minutes * 60), name="keep-alive")
