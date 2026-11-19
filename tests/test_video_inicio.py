import asyncio

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services import keep_alive
from tests.conftest import TEST_JWT_SECRET

URL = "/api/video-inicio"
VIDEO = {"url": "https://cdn.example.com/portada.mp4", "title": "  La   finca al amanecer ", "poster_url": ""}


def _settings(**overrides):
    values = {
        "_env_file": None, "smartcattle_ai_url": None, "ai_api_key": None, "database_url": None,
        "jwt_secret": TEST_JWT_SECRET,
    }
    return Settings(**(values | overrides))


@pytest.fixture
def admin_client():
    with TestClient(create_app(_settings(site_admin_emails="Ana@Finca.example"))) as client:
        yield client


def _register(client, email="ana@finca.example"):
    body = client.post("/api/auth/register", json={
        "email": email, "password": "una-clave-larga", "full_name": "Ana Restrepo",
    }).json()
    return {"Authorization": f"Bearer {body['access_token']}"}


def _login(client, email="ana@finca.example"):
    body = client.post("/api/auth/login", json={"email": email, "password": "una-clave-larga"}).json()
    return {"Authorization": f"Bearer {body['access_token']}"}


def test_the_cover_has_no_video_until_somebody_sets_one(auth_client):
    response = auth_client.get(URL)
    assert response.status_code == 200
    assert response.json() == {"video": None}


def test_reading_the_cover_needs_no_session(admin_client):
    headers = _register(admin_client)
    assert admin_client.put(URL, json=VIDEO, headers=headers).status_code == 200
    body = admin_client.get(URL).json()["video"]
    assert body["url"] == VIDEO["url"]
    assert body["title"] == "La finca al amanecer"
    assert body["poster_url"] is None
    assert body["source"] == "panel"


def test_the_deployment_default_shows_until_it_is_replaced():
    settings = _settings(video_inicio_url="/video-inicio.mp4", site_admin_emails="ana@finca.example")
    with TestClient(create_app(settings)) as client:
        assert client.get(URL).json()["video"] == {
            "url": "/video-inicio.mp4", "title": None, "poster_url": None, "updated_at": None, "source": "deployment",
        }
        headers = _register(client)
        client.put(URL, json=VIDEO, headers=headers)
        assert client.get(URL).json()["video"]["source"] == "panel"
        assert client.delete(URL, headers=headers).status_code == 204
        assert client.get(URL).json()["video"]["source"] == "deployment"


def test_the_database_remembers_it_and_keeps_the_moment_in_utc(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'video_inicio.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), "head")
    settings = _settings(database_url=url, site_admin_emails="ana@finca.example")
    with TestClient(create_app(settings)) as client:
        headers = _register(client)
        saved = client.put(URL, json=VIDEO, headers=headers).json()["video"]
        assert client.put(URL, json=VIDEO | {"title": "Otra"}, headers=headers).status_code == 200
    # A new process reads what the last one stored.
    with TestClient(create_app(settings)) as client:
        body = client.get(URL).json()["video"]
        assert body["title"] == "Otra"
        assert body["url"] == saved["url"]
        assert body["updated_at"].endswith("Z")
        assert client.delete(URL, headers=_login(client)).status_code == 204
        assert client.get(URL).json() == {"video": None}


def test_a_mistyped_default_falls_back_to_no_video():
    with TestClient(create_app(_settings(video_inicio_url="javascript:alert(1)"))) as client:
        assert client.get(URL).json() == {"video": None}


def test_changing_it_needs_a_session(auth_client):
    assert auth_client.put(URL, json=VIDEO).status_code == 401
    assert auth_client.delete(URL).status_code == 401


def test_an_owner_who_is_not_a_site_admin_is_refused(auth_client, owner_headers):
    # Registration is open by default, so anybody could have become this owner.
    assert auth_client.get(f"{URL}/permiso", headers=owner_headers).json() == {"can_edit": False}
    assert auth_client.put(URL, json=VIDEO, headers=owner_headers).status_code == 403


def test_every_owner_may_where_registration_is_closed():
    with TestClient(create_app(_settings(public_registration=False))) as client:
        headers = _register(client)
        assert client.get(f"{URL}/permiso", headers=headers).json() == {"can_edit": True}
        assert client.put(URL, json=VIDEO, headers=headers).status_code == 200


def test_a_named_admin_may_and_other_owners_may_not(admin_client):
    admin = _register(admin_client)
    assert admin_client.get(f"{URL}/permiso", headers=admin).json() == {"can_edit": True}
    other = _register(admin_client, "otra@finca.example")
    assert admin_client.put(URL, json=VIDEO, headers=other).status_code == 403


@pytest.mark.parametrize("url", [
    "http://cdn.example.com/portada.mp4",       # http outside this computer
    "https://cdn.example.com/portada.exe",      # not a video
    "javascript:alert(1)//x.mp4",
    "//evil.example.com/portada.mp4",           # protocol-relative
    "portada.mp4",                              # neither a URL nor a site path
    "https://cdn.example.com/a b.mp4",
    'https://cdn.example.com/"onerror=x.mp4',
])
def test_addresses_a_page_should_not_load_are_refused(admin_client, url):
    headers = _register(admin_client)
    assert admin_client.put(URL, json={"url": url}, headers=headers).status_code == 422


@pytest.mark.parametrize("url", [
    "https://cdn.example.com/portada.webm?v=3", "/video-inicio.mp4", "http://localhost:5173/video-inicio.mp4",
])
def test_addresses_a_page_can_load_are_accepted(admin_client, url):
    headers = _register(admin_client)
    assert admin_client.put(URL, json={"url": url}, headers=headers).status_code == 200


def test_the_health_check_answers_under_api_too(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_keep_alive_stays_off_without_a_public_address():
    assert keep_alive.keep_alive_target(_settings()) is None


def test_keep_alive_uses_the_address_render_provides():
    settings = _settings(render_external_url="https://smartcattle-backend.onrender.com")
    assert keep_alive.keep_alive_target(settings) == "https://smartcattle-backend.onrender.com/api/health"
    assert keep_alive.keep_alive_target(_settings(
        render_external_url="https://smartcattle-backend.onrender.com", keep_alive_enabled=False,
    )) is None


def test_a_failed_ping_does_not_stop_the_loop(monkeypatch):
    calls = []

    async def run():
        enough = asyncio.Event()

        def flaky(url):
            calls.append(url)
            if len(calls) == 1:
                raise OSError("network is down")
            if len(calls) >= 3:
                enough.set()
            return 200

        monkeypatch.setattr(keep_alive, "_ping", flaky)
        task = asyncio.create_task(keep_alive.keep_alive_loop("https://x.example/api/health", 0.01, first_delay=0))
        await asyncio.wait_for(enough.wait(), timeout=5)
        task.cancel()

    asyncio.run(run())
    assert len(calls) >= 3
