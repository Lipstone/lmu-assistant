import pytest
from fastapi.testclient import TestClient

from lmu_assistant.server import create_app
from lmu_assistant.sources import get_source


def test_mock_source_produces_connected_snapshot():
    snap = get_source("mock").read()
    assert snap.connected
    assert len(snap.wheels) == 4
    assert snap.fuel_l > 0


def test_server_serves_page_and_websocket():
    app = create_app(get_source("mock"), hz=50)
    with TestClient(app) as client:
        assert "LMU Assistant" in client.get("/").text
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()
        assert msg["type"] == "snapshot"
        assert msg["data"]["source"] == "mock"


def test_refresh_rate_follows_settings(tmp_path):
    from lmu_assistant.config import ConfigStore
    from lmu_assistant.server import Broadcaster

    store = ConfigStore(tmp_path / "c.json")
    b = Broadcaster(get_source("mock"), None, None, store)
    assert b.period == pytest.approx(1 / 30)
    store.save(store.config.model_copy(update={"refresh_hz": 60}))
    assert b.period == pytest.approx(1 / 60)
    assert Broadcaster(get_source("mock"), 50, None, store).period == pytest.approx(1 / 50)  # --hz prioritaire


def test_websocket_sends_only_what_pages_show():
    app = create_app(get_source("mock"), hz=50)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            data = ws.receive_json()["data"]
        assert "vehicles" not in data and "weather_forecast" not in data  # données brutes, gardées par le serveur
        assert "relative" in data and "ts" in data
        assert "vehicles" in client.get("/api/snapshot").json()
        with client.websocket_connect("/ws?widget=relative") as ws:
            data = ws.receive_json()["data"]
        assert set(data) == {"connected", "source", "session", "track", "car", "ts", "relative"}


def test_settings_websocket_gets_config_without_snapshots(tmp_path):
    from lmu_assistant.config import AppConfig

    app = create_app(get_source("mock"), hz=50, config_path=tmp_path / "c.json")
    with TestClient(app) as client:
        with client.websocket_connect("/ws?snapshots=0") as ws:
            cfg = AppConfig().model_dump()
            cfg["text_opacity"] = 0.4
            assert client.put("/api/config", json=cfg).status_code == 200
            assert ws.receive_json() == {"type": "config", "data": cfg}  # aucune image avant


def test_slow_client_gets_latest_snapshot_only():
    import asyncio

    from lmu_assistant.server import Client

    class SlowWs:
        def __init__(self):
            self.sent = []

        async def send_text(self, text):
            self.sent.append(text)
            await asyncio.sleep(0.05)

    async def scenario():
        ws = SlowWs()
        client = Client(ws)
        task = asyncio.create_task(client.run())
        client.push_snapshot("s1")
        await asyncio.sleep(0.01)  # s1 en cours d'envoi
        for i in range(2, 10):
            client.push_snapshot(f"s{i}")  # la page est en retard : seules la dernière image compte
        client.push("config")
        await asyncio.sleep(0.2)
        task.cancel()
        return ws.sent

    assert asyncio.run(scenario()) == ["s1", "config", "s9"]
