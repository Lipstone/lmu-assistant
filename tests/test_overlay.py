import json

from lmu_assistant import overlay
from lmu_assistant.config import WIDGET_IDS, AppConfig, window_size


class FakeWindow:
    def __init__(self):
        self.calls = []
        self.x = self.y = 0

    def move(self, x, y):
        self.calls.append(("move", x, y))
        self.x, self.y = x, y

    def resize(self, w, h):
        self.calls.append(("resize", w, h))

    def show(self):
        self.calls.append(("show",))

    def hide(self):
        self.calls.append(("hide",))


def make_overlay(monkeypatch, overrides=None):
    clicks = []
    windows = {wid: FakeWindow() for wid in WIDGET_IDS}
    names = {id(w): wid for wid, w in windows.items()}
    native_ready = set(WIDGET_IDS)

    def native(win, on, mode="alpha"):
        clicks.append((names[id(win)], on, mode))
        return names[id(win)] in native_ready

    monkeypatch.setattr(overlay, "set_native_style", native)
    monkeypatch.setattr(overlay.Hotkey, "set", lambda self, combo: None)
    return overlay.Overlay(windows, "http://x/api/config", overrides or {}, None), windows, clicks


def config(placement=False, **fuel):
    data = AppConfig().model_dump()
    data["placement"] = placement
    next(w for w in data["widgets"] if w["id"] == "fuel").update(fuel)
    return data


def test_plan_one_window_per_widget():
    plan = overlay.plan(config(x=-1500, y=300, scale=1.5, visible=False))
    assert set(plan) == set(WIDGET_IDS)
    fuel = plan["fuel"]
    assert (fuel.x, fuel.y) == (-1500, 300)  # écran à gauche de l'écran principal
    assert (fuel.width, fuel.height) == window_size("fuel", 1.5)
    assert fuel.visible is False and plan["lap"].visible is True


def test_plan_invalid_config_gives_defaults():
    plan = overlay.plan({"widgets": [{"id": "inconnu"}]})
    assert plan == overlay.plan(AppConfig().model_dump())


def test_plan_click_through_override():
    assert all(not s.click_through for s in overlay.plan({}, {"click_through": False}).values())


def test_apply_moves_only_changed_windows(monkeypatch):
    ov, windows, clicks = make_overlay(monkeypatch)
    ov.apply(config())
    assert len(clicks) == len(WIDGET_IDS)
    assert clicks[0] == (WIDGET_IDS[0], True, "alpha")
    for w in windows.values():
        w.calls.clear()

    ov.apply(config(x=500, y=40, visible=False))
    assert windows["fuel"].calls == [("move", 500, 40), ("hide",)]
    assert windows["lap"].calls == []


def test_hotkey_toggle_keeps_hidden_widgets_hidden(monkeypatch):
    ov, windows, _ = make_overlay(monkeypatch)
    ov.apply(config(visible=False))
    for w in windows.values():
        w.calls.clear()
    ov.toggle()  # masque tout
    ov.toggle()  # réaffiche
    assert windows["lap"].calls == [("hide",), ("show",)]
    assert windows["fuel"].calls == [("hide",), ("hide",)]


class FakeServer:
    """Remplace GET/PUT /api/config."""

    def __init__(self, monkeypatch, cfg):
        self.cfg = cfg
        self.puts = 0
        monkeypatch.setattr(overlay, "fetch_config", lambda url: json.loads(json.dumps(self.cfg)))
        monkeypatch.setattr(overlay, "put_config", self.put)

    def put(self, url, cfg):
        AppConfig.model_validate(cfg)  # le serveur refuserait une config invalide
        self.cfg = cfg
        self.puts += 1
        return True

    def widget(self, wid):
        return next(w for w in self.cfg["widgets"] if w["id"] == wid)


def test_placement_disables_click_through(monkeypatch):
    assert all(not s.click_through for s in overlay.plan(config(placement=True)).values())
    ov, _, clicks = make_overlay(monkeypatch)
    ov.apply(config())
    clicks.clear()
    ov.apply(config(placement=True))
    assert ov.placement and clicks == [(w, False, "alpha") for w in WIDGET_IDS]


def test_toggle_placement_saves_and_applies(monkeypatch):
    server = FakeServer(monkeypatch, config())
    ov, _, _ = make_overlay(monkeypatch)
    ov.apply(server.cfg)
    ov.toggle_placement()
    assert server.cfg["placement"] is True and ov.placement
    ov.toggle_placement()
    assert server.cfg["placement"] is False


def test_window_moved_with_mouse_is_saved_not_moved_back(monkeypatch):
    server = FakeServer(monkeypatch, config(placement=True))
    ov, windows, _ = make_overlay(monkeypatch)
    ov.apply(server.cfg)
    windows["fuel"].x, windows["fuel"].y = 900, 450  # glissé par l'utilisateur
    moved = ov.sync_moves()
    assert moved == {"fuel": {"x": 900, "y": 450}}
    windows["fuel"].calls.clear()
    ov.apply(server.cfg)  # config pas encore enregistrée : la fenêtre ne doit pas revenir
    assert windows["fuel"].calls == []
    ov.save_widgets(moved)
    assert (server.widget("fuel")["x"], server.widget("fuel")["y"]) == (900, 450)
    ov.apply(server.cfg)
    assert windows["fuel"].calls == []
    assert ov.sync_moves() == {}


def test_resize_with_grip(monkeypatch):
    server = FakeServer(monkeypatch, config(placement=True))
    ov, windows, _ = make_overlay(monkeypatch)
    ov.apply(server.cfg)
    windows["lap"].calls.clear()
    ov.set_scale("lap", 1.52, final=False)  # arrondi au pas de 0,05
    assert windows["lap"].calls == [("resize", *window_size("lap", 1.5))]
    ov.apply(server.cfg)  # ancienne échelle dans la config : pas de retour en arrière pendant le geste
    assert windows["lap"].calls == [("resize", *window_size("lap", 1.5))]
    ov.set_scale("lap", 9, final=True)  # borné à 4
    assert server.widget("lap")["scale"] == 4.0
    assert server.puts == 1
    windows["lap"].calls.clear()
    ov.apply(server.cfg)
    assert windows["lap"].calls == []


def test_transparency_mode_change_reapplied(monkeypatch):
    ov, _, clicks = make_overlay(monkeypatch)
    ov.apply(config())
    clicks.clear()
    ov.apply(config())
    assert clicks == []  # rien n'a changé
    cfg = config()
    cfg["window"]["transparency"] = "colorkey"
    ov.apply(cfg)
    assert clicks == [(w, True, "colorkey") for w in WIDGET_IDS]


def test_native_style_retried_until_window_exists(monkeypatch):
    ov, windows, clicks = make_overlay(monkeypatch)
    monkeypatch.setattr(overlay, "set_native_style", lambda win, on, mode="alpha": clicks.append(on) or win is not windows["fuel"])
    ov.apply(config())
    assert ov.native_pending == {"fuel"}
    clicks.clear()
    monkeypatch.setattr(overlay, "set_native_style", lambda win, on, mode="alpha": clicks.append(on) or True)
    ov.apply(config())
    assert clicks == [True] and ov.native_pending == set()


def test_ex_style():
    base = 0x100
    assert overlay.ex_style(base, False, "alpha") == base
    assert overlay.ex_style(base, True, "alpha") == base | overlay.WS_EX_LAYERED | overlay.WS_EX_TRANSPARENT
    assert overlay.ex_style(base, False, "colorkey") == base | overlay.WS_EX_LAYERED
    on = base | overlay.WS_EX_LAYERED | overlay.WS_EX_TRANSPARENT
    assert overlay.ex_style(on, False, "alpha") == base


def test_native_style_noop_off_windows(monkeypatch):
    monkeypatch.setattr(overlay.sys, "platform", "linux")
    assert overlay.set_native_style(object(), False) is True
