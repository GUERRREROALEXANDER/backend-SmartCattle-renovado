"""The RTSP camera service (camara/api.py), reached with a key only this server holds.

It knows nothing about accounts: its one key opens every camera. So nothing here decides who may do what; that is the
routes' job, and this client must only ever be called with an id they already checked.
"""

import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote

#: The service answers at once: starting a camera happens behind its answer.
TIMEOUT_SECONDS = 8


class CameraManagerError(Exception):
    """A failed call. Holds the status alone: the service's words can hold a camera's address."""

    def __init__(self, status: int | None) -> None:
        super().__init__(f"Camera service answered {status}")
        self.status = status


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """A redirect would carry the key to wherever it points."""

    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


# No proxy either: a proxy set in the environment would see the key.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirects())


class CameraManager:
    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def list(self) -> list[dict[str, Any]]:
        cameras = self._call("GET", "/api/camaras").get("camaras")
        if not isinstance(cameras, list):
            raise CameraManagerError(None)
        return [item for item in cameras if isinstance(item, dict)]

    def configure(self, camera_id: str, url: str) -> dict[str, Any]:
        return self._call("POST", "/api/configurar-camara", {"url": url, "camara_id": camera_id})

    def remove(self, camera_id: str) -> None:
        self._call("DELETE", f"/api/camaras/{quote(camera_id, safe='')}")

    def _call(self, method: str, path: str, body: dict[str, str] | None = None) -> dict[str, Any]:
        headers = {"X-API-Key": self._api_key}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(  # noqa: S310 - the scheme is checked by the setting's AnyHttpUrl
            f"{self._base_url}{path}", method=method, headers=headers,
            data=None if body is None else json.dumps(body).encode("utf-8"),
        )
        try:
            with _opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            error.close()
            # "from None": the chained error's request holds the key and the camera's password.
            raise CameraManagerError(error.code) from None
        except OSError:
            raise CameraManagerError(None) from None
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except ValueError:
            raise CameraManagerError(None) from None
        if not isinstance(parsed, dict):
            raise CameraManagerError(None)
        return parsed
