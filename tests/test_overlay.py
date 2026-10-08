from lmu_assistant import overlay
from lmu_assistant.config import WIDGET_IDS, AppConfig, window_size


class FakeWindow:
    def __init__(self):
        self.calls = []

    def move(self, x, y):
        self.calls.append(("move", x, y))

    def resize(self, w, h):
        self.calls.append(("resize", w, h))

    def show(self):
        self.calls.append(("show",))

    def hide(self):
        self.calls.append(("hide",))


def make_overlay(monkeypatch, overrides=None):
    clicks = []
    monkeypatch.setattr(overlay, "set_click_through", lambda title, on: clicks.append((title, on)))
    monkeypatch.setattr(overlay.Hotkey, "set", lambda self, combo: None)
    windows = {wid: FakeWindow() for wid in WIDGET_IDS}
    return overlay.Overlay(windows, "http://x/api/config", overrides or {}, None), windows, clicks


def config(**fuel):
    data = AppConfig().model_dump()
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
    assert clicks[0][0] == overlay.window_title(WIDGET_IDS[0])
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
