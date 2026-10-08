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
