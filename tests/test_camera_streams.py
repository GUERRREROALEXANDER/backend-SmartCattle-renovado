"""The bridge to the RTSP camera service: the key stays here and each account reaches only its own cameras.

Against a real HTTP server standing in for the service, so the header and the body are the ones actually sent.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app
from tests.conftest import TEST_JWT_SECRET

KEY = "clave-del-servicio-de-camaras-de-prueba-0001"
PASSWORD = "una-clave-larga"
URL = "rtsp://admin:SECRETO@192.168.1.50:554/cam/realmonitor?channel=1"
STREAMS = "/api/camera-streams"


class Service:
    """Holds what the stand-in was asked and what it will answer."""

    def __init__(self) -> None:
        self.cameras: dict[str, dict] = {}
        self.calls: list[tuple[str, str, dict[str, str], dict | None]] = []
        self.force_status: int | None = None
        self.redirect_to: str | None = None


def serve(service: Service) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:
            pass

        def answer(self, code: int, body: object = None) -> None:
            raw = b"" if body is None else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def handle_any(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length)) if length else None
            service.calls.append((self.command, self.path, {k.lower(): v for k, v in self.headers.items()}, body))
            if service.redirect_to:
                self.send_response(307)
                self.send_header("Location", service.redirect_to)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            if service.force_status:
                return self.answer(service.force_status, {"detail": f"fallo con {URL}"})
            if self.headers.get("X-API-Key") != KEY:
                return self.answer(401, {"detail": "nope"})
            if self.command == "GET":
                return self.answer(200, {"camaras": list(service.cameras.values()), "max_camaras": 8})
            if self.command == "POST":
                camera_id = body["camara_id"]
                service.cameras[camera_id] = {
                    "camara_id": camera_id, "estado": "conectando", "camara": "rtsp://***@192.168.1.50:554/cam/x",
                    "reintentos": 0, "cuadros": 0, "ultimo_error": f"fallo con {URL}",
                    "rtsp_url": f"rtsp://127.0.0.1:8554/{camera_id}",
                    "hls_url": f"http://127.0.0.1:8888/{camera_id}/index.m3u8",
                }
                return self.answer(200, service.cameras[camera_id])
            camera_id = self.path.rsplit("/", 1)[-1]
            if service.cameras.pop(camera_id, None) is None:
                return self.answer(404, {"detail": "no"})
            return self.answer(204)

        do_GET = do_POST = do_DELETE = handle_any

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def service():
    held = Service()
    server = serve(held)
    held.url = f"http://127.0.0.1:{server.server_address[1]}"
    yield held
    server.shutdown()
    server.server_close()


def client_for(**settings) -> TestClient:
    app = create_app(Settings(
        _env_file=None, database_url=None, jwt_secret=TEST_JWT_SECRET, account_isolation=True,
        rate_limit_enabled=False, **settings,
    ))
    return TestClient(app)


@pytest.fixture
def api(service):
    with client_for(camera_manager_url=service.url, camera_api_key=KEY) as client:
        yield client


def sign_up(api, email):
    body = {"email": email, "password": PASSWORD, "full_name": "Persona De Prueba"}
    return {"Authorization": f"Bearer {api.post('/api/auth/register', json=body).json()['access_token']}"}


@pytest.fixture
def ana(api):
    return sign_up(api, "ana@finca.example")


@pytest.fixture
def luis(api):
    return sign_up(api, "luis@finca.example")


def start(api, headers, name="Corral", url=URL):
    return api.post(STREAMS, json={"name": name, "url": url}, headers=headers)


def test_the_key_comes_from_the_server_and_the_browser_sends_none(api, ana, service):
    assert start(api, ana).status_code == 201
    method, path, headers, body = service.calls[-1]
    assert (method, path) == ("POST", "/api/configurar-camara")
    assert headers["x-api-key"] == KEY
    assert "authorization" not in headers, "the person's session is not passed on"
    assert body["url"] == URL


def test_a_new_name_saves_the_camera_with_an_id_from_here_and_no_password(api, ana, service):
    stream = start(api, ana).json()
    assert stream["id"].startswith("cam-")
    assert service.calls[-1][3]["camara_id"] == stream["id"]
    saved = api.get("/api/cameras/saved", headers=ana).json()["items"]
    assert [(item["id"], item["name"], item["source"]) for item in saved] == [
        (stream["id"], "Corral", "rtsp://192.168.1.50:554"),
    ]


def test_a_saved_name_reconnects_that_camera_without_a_second_one(api, ana):
    first = api.post("/api/cameras/saved", json={"name": "Corral", "source": "rtsp://10.0.0.1/x"}, headers=ana).json()
    assert start(api, ana, name=" corral ").json()["id"] == first["id"]
    assert api.get("/api/cameras/saved", headers=ana).json()["total"] == 1


@pytest.mark.parametrize("field", ["SECRETO", "admin", "ultimo_error", "rtsp_url", "reintentos"])
def test_nothing_private_reaches_the_browser(api, ana, field):
    created = start(api, ana)
    assert field not in created.text
    assert field not in api.get(STREAMS, headers=ana).text
    assert field not in api.get("/api/cameras/saved", headers=ana).text
    assert field not in api.get("/api/audit-log", headers=ana).text


def test_it_reports_only_where_the_camera_is_and_how_it_goes(api, ana):
    stream_id = start(api, ana).json()["id"]
    assert api.get(STREAMS, headers=ana).json() == {"total": 1, "items": [{
        "id": stream_id, "name": "Corral", "state": "conectando", "address": "192.168.1.50:554", "retries": 0,
        "hls_url": f"http://127.0.0.1:8888/{stream_id}/index.m3u8",
    }]}


def test_an_account_never_sees_or_stops_another_ones_camera(api, ana, luis, service):
    stream_id = start(api, ana).json()["id"]
    assert api.get(STREAMS, headers=luis).json() == {"items": [], "total": 0}
    service.calls.clear()
    assert api.delete(f"{STREAMS}/{stream_id}", headers=luis).status_code == 404
    assert service.calls == [], "the service is not even asked"
    assert stream_id in service.cameras


def test_a_camera_of_the_service_that_no_account_saved_is_hidden(api, ana, service):
    service.cameras["live"] = {"camara_id": "live", "estado": "transmitiendo"}
    assert api.get(STREAMS, headers=ana).json()["total"] == 0


def test_the_same_name_in_two_accounts_is_two_cameras(api, ana, luis):
    assert start(api, ana).json()["id"] != start(api, luis).json()["id"]


def test_stopping_keeps_the_camera_saved(api, ana, service):
    stream_id = start(api, ana).json()["id"]
    assert api.delete(f"{STREAMS}/{stream_id}", headers=ana).status_code == 204
    assert stream_id not in service.cameras
    assert api.get("/api/cameras/saved", headers=ana).json()["total"] == 1


def test_deleting_a_saved_camera_stops_its_stream(api, ana, service):
    stream_id = start(api, ana).json()["id"]
    assert api.delete(f"/api/cameras/saved/{stream_id}", headers=ana).status_code == 204
    assert stream_id not in service.cameras


def test_deleting_a_saved_camera_works_with_the_service_failing(api, ana, service):
    stream_id = start(api, ana).json()["id"]
    service.force_status = 500
    assert api.delete(f"/api/cameras/saved/{stream_id}", headers=ana).status_code == 204


def test_it_needs_a_session(api):
    assert api.get(STREAMS).status_code == 401
    assert api.post(STREAMS, json={"name": "Corral", "url": URL}).status_code == 401
    assert api.delete(f"{STREAMS}/cam-x").status_code == 401


def test_a_worker_watches_but_does_not_connect_or_stop(api, ana):
    stream_id = start(api, ana).json()["id"]
    invited = api.post(
        "/api/users", headers=ana,
        json={"email": "peon@finca.example", "password": PASSWORD, "full_name": "Peón De Prueba", "role": "worker"},
    )
    assert invited.status_code == 201, invited.text
    login = api.post("/api/auth/login", json={"email": "peon@finca.example", "password": PASSWORD}).json()
    worker = {"Authorization": f"Bearer {login['access_token']}"}
    assert api.get(STREAMS, headers=worker).json()["total"] == 1
    assert start(api, worker, name="Otra").status_code == 403
    assert api.delete(f"{STREAMS}/{stream_id}", headers=worker).status_code == 403


@pytest.mark.parametrize(("service_status", "answered"), [(401, 502), (403, 502), (409, 409), (422, 422), (500, 503)])
def test_a_failure_of_the_service_does_not_end_the_session_or_leave_a_camera(
    api, ana, service, service_status, answered,
):
    service.force_status = service_status
    response = start(api, ana)
    assert response.status_code == answered
    assert "SECRETO" not in response.text
    assert KEY not in response.text
    assert api.get("/api/cameras/saved", headers=ana).json()["total"] == 0


def test_a_failure_keeps_a_camera_that_was_already_saved(api, ana, service):
    api.post("/api/cameras/saved", json={"name": "Corral", "source": "rtsp://10.0.0.1/x"}, headers=ana)
    service.force_status = 500
    assert start(api, ana).status_code == 503
    assert api.get("/api/cameras/saved", headers=ana).json()["total"] == 1


@pytest.mark.parametrize("url", [
    "http://192.168.1.50/x", "192.168.1.50", "file:///etc/passwd", "rtsp://", "rtsp://a b/c", "rtsp:///x",
    "rtsp://admin:cl/ave@192.168.1.50/x",
])
def test_a_url_that_is_not_a_camera_never_reaches_the_service(api, ana, service, url):
    service.calls.clear()
    response = start(api, ana, url=url)
    assert response.status_code == 422
    assert service.calls == []
    assert url not in response.text


def test_a_redirect_does_not_carry_the_key_away(api, ana, service):
    other = Service()
    server = serve(other)
    try:
        service.redirect_to = f"http://127.0.0.1:{server.server_address[1]}/robada"
        assert api.get(STREAMS, headers=ana).status_code == 503
        assert other.calls == []
    finally:
        server.shutdown()
        server.server_close()


def test_a_service_that_is_off_is_a_503():
    with client_for(camera_manager_url="http://127.0.0.1:9", camera_api_key=KEY) as client:
        ana = sign_up(client, "ana@finca.example")
        response = client.get(STREAMS, headers=ana)
    assert response.status_code == 503
    assert response.json()["detail"] == "The camera service is not responding"


def test_unconfigured_is_a_503_and_the_rest_of_the_cameras_still_work():
    with client_for() as client:
        ana = sign_up(client, "ana@finca.example")
        assert client.get(STREAMS, headers=ana).status_code == 503
        saved = client.post("/api/cameras/saved", json={"name": "Corral", "source": "0"}, headers=ana).json()
        assert client.delete(f"/api/cameras/saved/{saved['id']}", headers=ana).status_code == 204


@pytest.mark.parametrize("settings", [{"camera_manager_url": "http://127.0.0.1:8095"}, {"camera_api_key": KEY}])
def test_half_a_configuration_is_refused_at_startup(settings):
    with pytest.raises(ValidationError, match="CAMERA_MANAGER_URL"):
        Settings(_env_file=None, **settings)


def test_the_key_never_appears_in_the_settings_repr():
    settings = Settings(_env_file=None, camera_manager_url="http://127.0.0.1:8095", camera_api_key=KEY)
    assert KEY not in repr(settings)
