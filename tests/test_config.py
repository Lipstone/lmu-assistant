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
    assert (cfg.background_opacity, cfg.text_opacity) == (0.75, 1.0)
    assert cfg.hotkey == "ctrl+shift+o"
    assert cfg.window.click_through
    assert cfg.placement is False and cfg.placement_hotkey == "ctrl+shift+p"
    assert cfg.fuel_mode == "auto"
    assert cfg.delta_reference == "best"
    assert cfg.laptime_avg_laps == 5
    assert (cfg.tyre_temp_min_c, cfg.tyre_temp_max_c, cfg.pressure_unit) == (75.0, 100.0, "kpa")
    assert cfg.brake_overheat_c == 800.0
    assert cfg.pit_loss_s == 60.0
    assert cfg.refresh_hz == 30


def test_tyre_settings_validated():
    assert AppConfig(tyre_temp_min_c=80, tyre_temp_max_c=95, pressure_unit="psi").pressure_unit == "psi"
    with pytest.raises(ValidationError):
        AppConfig(tyre_temp_min_c=100, tyre_temp_max_c=90)
    with pytest.raises(ValidationError):
        AppConfig(pressure_unit="atm")


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
    data.update(text_opacity=0.5, hotkey="F9")
    data["widgets"][0].update(visible=False, x=123)
    cfg = AppConfig.model_validate(data)
    store.save(cfg)
    assert json.loads(path.read_text(encoding="utf-8"))["text_opacity"] == 0.5
    loaded = ConfigStore(path).config
    assert loaded == cfg
    assert loaded.hotkey == "f9"  # normalisé en minuscules


def test_widget_transparency_optional():
    cfg = AppConfig.model_validate(
        {"background_opacity": 0.0, "widgets": [{"id": "fuel", "text_opacity": 0.6, "background_opacity": 0.2}]}
    )
    fuel = next(w for w in cfg.widgets if w.id == "fuel")
    assert (fuel.text_opacity, fuel.background_opacity) == (0.6, 0.2)
    lap = next(w for w in cfg.widgets if w.id == "lap")
    assert lap.text_opacity is None and lap.background_opacity is None  # valeurs globales
    assert cfg.background_opacity == 0.0


def test_old_window_fields_ignored():
    cfg = AppConfig.model_validate({"window": {"transparency": "colorkey", "click_through": False}})
    assert cfg.window.click_through is False


def test_old_opacity_migrated():
    """Ancien `opacity` (tout le widget) : devient l'opacité du texte, le fond garde le même rendu."""
    cfg = AppConfig.model_validate(
        {
            "opacity": 0.85,  # ancien défaut : nouveaux défauts
            "background_opacity": 0.75,
            "widgets": [{"id": "fuel", "opacity": 0.5, "background_opacity": 0.4}, {"id": "lap", "opacity": 0.8}],
        }
    )
    assert (cfg.text_opacity, cfg.background_opacity) == (1.0, 0.75)
    fuel = next(w for w in cfg.widgets if w.id == "fuel")
    assert (fuel.text_opacity, fuel.background_opacity) == (0.5, 0.2)
    lap = next(w for w in cfg.widgets if w.id == "lap")
    assert (lap.text_opacity, lap.background_opacity) == (0.8, None)
    cfg = AppConfig.model_validate({"opacity": 0.5, "background_opacity": 0.6})
    assert (cfg.text_opacity, cfg.background_opacity) == (0.5, 0.3)


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
        {"delta_reference": "optimal"},
        {"widgets": [{"id": "inconnu"}]},
        {"widgets": [{"id": "lap"}, {"id": "lap"}]},
        {"widgets": [{"id": "lap", "scale": 0}]},
        {"widgets": [{"id": "lap", "x": -20000}]},
        {"widgets": [{"id": "fuel", "opacity": 0.05}]},
        {"widgets": [{"id": "fuel", "text_opacity": 0.05}]},
        {"text_opacity": 1.5},
        {"refresh_hz": 2},
        {"refresh_hz": 120},
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
    cfg["text_opacity"] = 0.4
    cfg["widgets"][1]["visible"] = False
    cfg["window"]["click_through"] = False
    r = client.put("/api/config", json=cfg)
    assert r.status_code == 200
    assert client.get("/api/config").json() == cfg
    assert (tmp_path / "config.json").exists()


def test_put_invalid_is_rejected_and_unchanged(client):
    r = client.put("/api/config", json={"text_opacity": 5})
    assert r.status_code == 422
    assert client.get("/api/config").json() == AppConfig().model_dump()


def test_put_broadcasts_config_on_websocket(client):
    cfg = AppConfig().model_dump()
    cfg["text_opacity"] = 0.3
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


def test_ranking_columns_off_by_default_and_saved(tmp_path):
    cfg = AppConfig()
    assert not any(w.show_damage or w.show_remaining or w.show_consumption for w in cfg.widgets)
    data = cfg.model_dump()
    rel = next(w for w in data["widgets"] if w["id"] == "relative")
    rel.update(show_damage=True, show_remaining=True, show_consumption=True)
    store = ConfigStore(tmp_path / "config.json")
    store.save(AppConfig.model_validate(data))
    loaded = {w.id: w for w in ConfigStore(tmp_path / "config.json").config.widgets}
    assert loaded["relative"].show_damage and loaded["relative"].show_consumption and loaded["relative"].show_remaining
    assert not loaded["standings"].show_damage


def test_lap_columns_default_and_saved(tmp_path):
    widgets = {w.id: w for w in AppConfig().widgets}
    assert widgets["standings"].show_last_lap  # dernier tour toujours affiché avant d'être réglable
    assert widgets["standings"].show_compound and not widgets["relative"].show_compound
    assert not any(w.show_headers for w in AppConfig().widgets)  # titres des colonnes : option
    assert not widgets["relative"].show_last_lap and not widgets["standings"].show_best_lap
    # ancienne config sans la clé : dernier tour gardé dans le Classement
    old = AppConfig.model_validate({"widgets": [{"id": "standings"}]}).widgets[0]
    assert old.show_last_lap and old.show_compound
    data = AppConfig().model_dump()
    for w in data["widgets"]:
        if w["id"] == "standings":
            w.update(show_last_lap=False, show_best_lap=True)
    store = ConfigStore(tmp_path / "config.json")
    store.save(AppConfig.model_validate(data))
    loaded = {w.id: w for w in ConfigStore(tmp_path / "config.json").config.widgets}
    assert loaded["standings"].show_best_lap and not loaded["standings"].show_last_lap
