"""Fenêtres de l'overlay avec Qt (PySide6 / QtWebEngine).

Pourquoi Qt et plus pywebview : sous Windows, pywebview (WebView2) ne rend pas le fond des fenêtres
transparent (zones grises ou blanches opaques, mesuré sur le PC de Rémy le 2026-10-08), alors que
Qt avec WA_TranslucentBackground compose la page pixel par pixel sur le jeu (fond semi-transparent,
texte net) et gère les clics traversants (Qt.WindowTransparentForInput).

Qt n'accepte d'agir sur les fenêtres que depuis son thread : `QtWindow` reçoit les ordres de la
logique de l'overlay (autre thread) par signaux, exécutés dans le thread de l'interface.
"""

import os
import signal
import threading

from PySide6.QtCore import QFile, QIODevice, QObject, Qt, QTimer, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineScript
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

# Les fenêtres affichent la même page locale : un seul processus de rendu pour toutes.
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--process-per-site")

FLAGS = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool

# Pont page -> Python : la page trouve l'objet `window.lmuOverlay` (évènement « lmuoverlayready »).
BOOTSTRAP = """
new QWebChannel(qt.webChannelTransport, (channel) => {
  window.lmuOverlay = channel.objects.api;
  window.dispatchEvent(new Event("lmuoverlayready"));
});
"""


def _channel_script() -> QWebEngineScript:
    f = QFile(":/qtwebchannel/qwebchannel.js")
    f.open(QIODevice.OpenModeFlag.ReadOnly)
    source = bytes(f.readAll().data()).decode("utf-8")
    f.close()
    script = QWebEngineScript()
    script.setName("lmu-overlay-bridge")
    script.setSourceCode(source + BOOTSTRAP)
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    script.setRunsOnSubFrames(False)
    return script


class View(QWebEngineView):
    """Fenêtre d'un widget : sans bordure, au premier plan, fond transparent pixel par pixel."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setWindowTitle(title)
        self.setWindowFlags(FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)  # ne vole pas le focus au jeu
        self.setStyleSheet("background: transparent")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.page().setBackgroundColor(Qt.GlobalColor.transparent)
        self.setMinimumSize(1, 1)
        self.on_move = None

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if self.on_move:
            self.on_move(self.x(), self.y())


class QtWindow(QObject):
    """Interface attendue par `Overlay` (move, resize, show, hide, x, y, set_click_through),
    utilisable depuis n'importe quel thread."""

    _move = Signal(int, int)
    _resize = Signal(int, int)
    _visible = Signal(bool)
    _click = Signal(bool)

    def __init__(self, view: View) -> None:
        super().__init__()
        self.view = view
        self.x, self.y = view.x(), view.y()
        self.shown = False
        view.on_move = self._moved
        queued = Qt.ConnectionType.QueuedConnection
        self._move.connect(self._do_move, queued)
        self._resize.connect(self._do_resize, queued)
        self._visible.connect(self._do_visible, queued)
        self._click.connect(self._do_click, queued)

    def _moved(self, x: int, y: int) -> None:
        self.x, self.y = x, y

    # Appelés par l'overlay (thread quelconque)
    def move(self, x: int, y: int) -> None:
        self.x, self.y = x, y
        self._move.emit(x, y)

    def resize(self, width: int, height: int) -> None:
        self._resize.emit(width, height)

    def show(self) -> None:
        self._visible.emit(True)

    def hide(self) -> None:
        self._visible.emit(False)

    def set_click_through(self, enabled: bool) -> None:
        self._click.emit(enabled)

    # Exécutés dans le thread de l'interface
    @Slot(int, int)
    def _do_move(self, x: int, y: int) -> None:
        self.view.move(x, y)

    @Slot(int, int)
    def _do_resize(self, width: int, height: int) -> None:
        self.view.resize(width, height)

    @Slot(bool)
    def _do_visible(self, visible: bool) -> None:
        self.shown = visible
        self.view.setVisible(visible)

    @Slot(bool)
    def _do_click(self, enabled: bool) -> None:
        # Changer les drapeaux masque la fenêtre : on la réaffiche si elle était visible.
        self.view.setWindowFlag(Qt.WindowType.WindowTransparentForInput, enabled)
        if self.shown:
            self.view.show()


class Bridge(QObject):
    """Fonctions appelées par la page d'un widget (window.lmuOverlay) : taille du contenu,
    agrandissement et déplacement à la souris (mode placement)."""

    def __init__(self, overlay, widget_id: str, view: View) -> None:
        super().__init__()
        self._overlay, self._wid, self._view = overlay, widget_id, view

    @Slot(float, float)
    def fit(self, width: float, height: float) -> None:
        self._overlay.set_content(self._wid, width, height)

    @Slot(float, bool)
    def set_scale(self, scale: float, final: bool) -> None:
        if final:  # enregistrement sur le serveur : hors du thread de l'interface
            threading.Thread(target=self._overlay.set_scale, args=(self._wid, scale, True), daemon=True).start()
        else:
            self._overlay.set_scale(self._wid, scale, False)

    @Slot()
    def start_move(self) -> None:
        handle = self._view.windowHandle()
        if handle is not None:
            handle.startSystemMove()  # déplacement natif, suivi ensuite par Overlay.sync_moves


def run(overlay, url_for, title_for, states: dict, quit_after: float | None = None) -> int:
    """Crée une fenêtre par widget et exécute la boucle Qt (thread principal) jusqu'à la fermeture.
    `states` : état initial de chaque fenêtre (WindowState). Renvoie le nombre de fenêtres créées."""
    app = QApplication.instance() or QApplication([])
    script = _channel_script()
    keep = []  # ponts et canaux : gardés en vie tant que l'overlay tourne
    for wid, state in states.items():
        view = View(title_for(wid))
        view.page().scripts().insert(script)
        bridge = Bridge(overlay, wid, view)
        channel = QWebChannel(view.page())
        channel.registerObject("api", bridge)
        view.page().setWebChannel(channel)
        keep += [bridge, channel]
        view.setGeometry(state.x, state.y, state.width, state.height)
        win = QtWindow(view)
        overlay.windows[wid] = win
        view.setUrl(url_for(wid))
    threading.Thread(target=overlay.run, name="overlay", daemon=True).start()
    # Ctrl+C dans la console : Python ne reprend la main que si la boucle Qt lui laisse du temps.
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, lambda *_: app.quit())
    tick = QTimer()
    tick.timeout.connect(lambda: None)
    tick.start(300)
    if quit_after:
        QTimer.singleShot(int(quit_after * 1000), app.quit)
    print(f"[overlay] {len(states)} fenêtres de widgets (Qt)")
    app.exec()
    return len(states)
