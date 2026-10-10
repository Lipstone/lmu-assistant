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

    def set_click_through(self, on):
        self.clicks.append((self.wid, on))


def make_overlay(monkeypatch, overrides=None):
    clicks = []
    windows = {wid: FakeWindow() for wid in WIDGET_IDS}
    for wid, w in windows.items():
        w.wid, w.clicks = wid, clicks
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
    assert clicks[0] == (WIDGET_IDS[0], True)
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
    assert ov.placement and clicks == [(w, False) for w in WIDGET_IDS]


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


def test_click_through_applied_only_when_changed(monkeypatch):
    ov, _, clicks = make_overlay(monkeypatch)
    ov.apply(config())
    assert clicks == [(w, True) for w in WIDGET_IDS]
    clicks.clear()
    ov.apply(config())
    assert clicks == []  # rien n'a changé


def test_window_fits_measured_widget(monkeypatch):
    ov, windows, _ = make_overlay(monkeypatch)
    ov.apply(config(scale=1.5))
    windows["fuel"].calls.clear()
    ov.set_content("fuel", 200, 151.2)  # mesuré par la page, à l'échelle 1
    assert windows["fuel"].calls == [("resize", 300, 227)]
    assert (ov.applied["fuel"].width, ov.applied["fuel"].height) == (300, 227)
    windows["fuel"].calls.clear()
    ov.apply(config(scale=1.5))  # la config relue ne remet pas la taille par défaut
    assert windows["fuel"].calls == []
    ov.set_scale("fuel", 1.0, final=False)
    assert windows["fuel"].calls == [("resize", 200, 152)]


def test_fit_before_first_apply_is_kept(monkeypatch):
    ov, windows, _ = make_overlay(monkeypatch)
    ov.set_content("lap", 220, 180)
    ov.apply(config())
    assert ("resize", 220, 180) in windows["lap"].calls
    ov.set_content("lap", "x", None)  # valeur invalide de la page : ignorée
    assert ov.content["lap"] == (220.0, 180.0)


def test_toggle_placement_applies_before_saving(monkeypatch):
    server = FakeServer(monkeypatch, config())
    ov, _, clicks = make_overlay(monkeypatch)
    ov.apply(server.cfg)
    clicks.clear()
    order = []
    monkeypatch.setattr(overlay, "put_config", lambda url, cfg: order.append(("put", list(clicks))) or True)
    ov.toggle_placement()
    # Les fenêtres sont devenues cliquables avant l'aller-retour avec le serveur
    assert order == [("put", [(w, False) for w in WIDGET_IDS])]


def test_stale_config_does_not_undo_local_action(monkeypatch):
    server = FakeServer(monkeypatch, config())
    ov, windows, _ = make_overlay(monkeypatch)
    ov.apply(server.cfg)
    generation = ov.generation
    stale = json.loads(json.dumps(server.cfg))  # lue par la boucle de suivi juste avant le raccourci
    ov.toggle_placement()
    ov.apply_fetched(stale, generation)
    assert ov.placement  # la config périmée est ignorée
    ov.apply_fetched(server.cfg, ov.generation)
    assert ov.placement


def test_close_cross_hides_widget_and_saves(monkeypatch):
    server = FakeServer(monkeypatch, config(placement=True))
    ov, windows, _ = make_overlay(monkeypatch)
    ov.apply(server.cfg)
    windows["fuel"].calls.clear()
    ov.hide_widget("fuel")
    assert windows["fuel"].calls == [("hide",)]
    assert server.widget("fuel")["visible"] is False
    assert server.widget("fuel")["page_visible"] is True  # l'interface ingénieur garde le widget
    ov.apply(server.cfg)
    assert windows["fuel"].calls == [("hide",)]
    ov.toggle()
    ov.toggle()  # afficher/masquer l'overlay ne le fait pas revenir
    assert ("show",) not in windows["fuel"].calls
