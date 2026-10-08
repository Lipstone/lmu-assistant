import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from lmu_assistant.config import WIDGET_IDS, WIDGET_SIZES, AppConfig, ConfigStore, window_size
from lmu_assistant.server import create_app
from lmu_assistant.sources import get_source


def test_defaults():
    cfg = AppConfig()
    assert [w.id for w in cfg.widgets] == list(WIDGET_IDS)
    assert all(w.visible and w.scale == 1.0 for w in cfg.widgets)
    assert 0.1 <= cfg.opacity <= 1.0
    assert cfg.hotkey == "ctrl+shift+o"
    assert cfg.window.click_through
    assert cfg.placement is False and cfg.placement_hotkey == "ctrl+shift+p"
    assert cfg.fuel_mode == "auto"


def test_every_widget_has_a_window_size():
    assert set(WIDGET_SIZES) == set(WIDGET_IDS)
    assert window_size("fuel", 2.0) == (2 * WIDGET_SIZES["fuel"][0], 2 * WIDGET_SIZES["fuel"][1])


def test_old_single_window_config_still_loads():
    # Avant le découpage en une fenêtre par widget, "window" avait x/y/width/height : ignorés.
    cfg = AppConfig.model_validate({"window": {"x": 5, "y": 5, "width": 400, "height": 420, "click_through": False}})
    assert cfg.window.click_through is False
    assert "width" not in cfg.window.model_dump()


def test_missing_file_gives_defaults(tmp_path):
    store = ConfigStore(tmp_path / "absent.json")
    assert store.config == AppConfig()


def test_corrupt_file_gives_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ pas du json", encoding="utf-8")
    assert ConfigStore(path).config == AppConfig()


def test_save_load_roundtrip(tmp_path):
    path = tmp_path / "sub" / "config.json"
    store = ConfigStore(path)
    data = AppConfig().model_dump()
    data.update(opacity=0.5, hotkey="F9")
    data["widgets"][0].update(visible=False, x=123)
    cfg = AppConfig.model_validate(data)
    store.save(cfg)
    assert json.loads(path.read_text(encoding="utf-8"))["opacity"] == 0.5
    loaded = ConfigStore(path).config
    assert loaded == cfg
    assert loaded.hotkey == "f9"  # normalisé en minuscules


def test_widget_transparency_optional():
    cfg = AppConfig.model_validate(
        {"background_opacity": 0.0, "widgets": [{"id": "fuel", "opacity": 0.6, "background_opacity": 0.2}]}
    )
    fuel = next(w for w in cfg.widgets if w.id == "fuel")
    assert (fuel.opacity, fuel.background_opacity) == (0.6, 0.2)
    lap = next(w for w in cfg.widgets if w.id == "lap")
    assert lap.opacity is None and lap.background_opacity is None  # valeurs globales
    assert cfg.background_opacity == 0.0


def test_partial_widgets_completed():
    cfg = AppConfig.model_validate({"widgets": [{"id": "fuel", "visible": False}]})
    assert [w.id for w in cfg.widgets][0] == "fuel"
    assert sorted(w.id for w in cfg.widgets) == sorted(WIDGET_IDS)


@pytest.mark.parametrize(
    "bad",
    [
        {"opacity": 2},
        {"opacity": 0},
        {"hotkey": "   "},
        {"placement_hotkey": ""},
        {"fuel_mode": "kwh"},
        {"widgets": [{"id": "inconnu"}]},
        {"widgets": [{"id": "lap"}, {"id": "lap"}]},
        {"widgets": [{"id": "lap", "scale": 0}]},
        {"widgets": [{"id": "lap", "x": -20000}]},
        {"widgets": [{"id": "fuel", "opacity": 0.05}]},
        {"widgets": [{"id": "fuel", "background_opacity": 1.5}]},
        {"background_opacity": -0.1},
        {"window": {"click_through": "peut-être"}},
        {"champ_inconnu": 1},
    ],
)
def test_validation_rejects(bad):
    with pytest.raises(ValidationError):
        AppConfig.model_validate(bad)


@pytest.fixture
def client(tmp_path):
    app = create_app(get_source("mock"), hz=50, config_path=tmp_path / "config.json")
    with TestClient(app) as c:
        yield c


def test_get_config_defaults(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    assert r.json() == AppConfig().model_dump()


def test_put_then_get(client, tmp_path):
    cfg = AppConfig().model_dump()
    cfg["opacity"] = 0.4
    cfg["widgets"][1]["visible"] = False
    cfg["window"]["click_through"] = False
    r = client.put("/api/config", json=cfg)
    assert r.status_code == 200
    assert client.get("/api/config").json() == cfg
    assert (tmp_path / "config.json").exists()


def test_put_invalid_is_rejected_and_unchanged(client):
    r = client.put("/api/config", json={"opacity": 5})
    assert r.status_code == 422
    assert client.get("/api/config").json() == AppConfig().model_dump()


def test_put_broadcasts_config_on_websocket(client):
    cfg = AppConfig().model_dump()
    cfg["opacity"] = 0.3
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "snapshot"  # client bien enregistré
        assert client.put("/api/config", json=cfg).status_code == 200
        for _ in range(200):
            msg = ws.receive_json()
            if msg["type"] == "config":
                break
        else:
            pytest.fail("pas de message config reçu")
    assert msg["data"] == cfg


def test_settings_page_served(client):
    r = client.get("/settings.html")
    assert r.status_code == 200
    assert "settings.js" in r.text
