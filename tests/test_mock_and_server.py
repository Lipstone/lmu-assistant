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
