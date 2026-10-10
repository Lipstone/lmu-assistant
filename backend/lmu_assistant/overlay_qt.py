"""Fenêtres de l'overlay avec Qt (PySide6 / QtWebEngine).

Pourquoi Qt et plus pywebview : sous Windows, pywebview (WebView2) ne rend pas le fond des fenêtres
transparent (zones grises ou blanches opaques, mesuré sur le PC de Rémy le 2026-10-08), alors que
Qt avec WA_TranslucentBackground compose la page pixel par pixel sur le jeu (fond semi-transparent,
texte net) et gère les clics traversants (Qt.WindowTransparentForInput).

Qt n'accepte d'agir sur les fenêtres que depuis son thread : `QtWindow` reçoit les ordres de la
logique de l'overlay (autre thread) par signaux, exécutés dans le thread de l'interface.

L'interface ingénieur et l'overlay course sont indépendants : fermer la fenêtre de l'interface la cache
seulement, l'application reste dans la zone de notification (icône près de l'horloge : rouvrir
l'interface, afficher/masquer l'overlay, mode placement, quitter).
"""

import os
import signal
import threading

from PySide6.QtCore import QFile, QIODevice, QObject, QRectF, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineScript
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

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

    def __init__(self, title: str, click_through: bool = False) -> None:
        super().__init__()
        self.setWindowTitle(title)
        # Clics traversants dès la création : la fenêtre native naît avec le bon style.
        self.setWindowFlags(FLAGS | (Qt.WindowType.WindowTransparentForInput if click_through else Qt.WindowType(0)))
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


class MainWindow(QWebEngineView):
    """Fenêtre de l'interface ingénieur (page principale) : fenêtre normale, dans la barre des tâches.
    Avec l'icône de notification (`keep_running`), la fermer la cache seulement : l'overlay course continue.
    Sinon la fermer quitte l'application (serveur et overlay compris)."""

    def __init__(self, url: str, title: str) -> None:
        super().__init__()
        self.keep_running = False
        self.on_hidden = None
        self.setWindowTitle(title)
        self.setMinimumSize(640, 400)
        self.resize(1440, 900)
        # Liens « télécharger » (exports de l'analyse) : enregistrés dans le dossier Téléchargements.
        self.page().profile().downloadRequested.connect(lambda download: download.accept())
        self.titleChanged.connect(lambda t: self.setWindowTitle(f"{title} - {t}" if t and t != title else title))
        self.setUrl(url)

    def closeEvent(self, event) -> None:
        # Qt 6 : app.quit() ferme d'abord les fenêtres et abandonne si l'une refuse ; en sortie, on accepte.
        if self.keep_running and not QApplication.instance().property("lmu_quitting"):
            event.ignore()
            self.hide()
            if self.on_hidden:
                self.on_hidden()
            return
        super().closeEvent(event)
        QApplication.instance().quit()


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
        self.click_through: bool | None = None
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
        if visible and self.click_through is not None:
            self._set_input_flag(self.click_through)

    @Slot(bool)
    def _do_click(self, enabled: bool) -> None:
        self.click_through = enabled
        self._set_input_flag(enabled)

    def _set_input_flag(self, enabled: bool) -> None:
        """Clics traversants ou non. Sur la fenêtre native déjà créée, le style change sur place
        (QWindow.setFlags) : instantané. QWidget.setWindowFlag recréerait chaque fenêtre et sa page,
        ce qui rendait le mode placement très lent à s'activer (une quinzaine de fenêtres)."""
        flag = Qt.WindowType.WindowTransparentForInput
        handle = self.view.windowHandle()
        if handle is None:  # pas encore affichée : réglé à la création de la fenêtre native
            self.view.setWindowFlag(flag, enabled)
            return
        if bool(handle.flags() & flag) != enabled:
            handle.setFlag(flag, enabled)


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
    def hide_widget(self) -> None:
        """Croix du mode placement : retire ce widget de l'overlay (enregistrement hors du thread de l'interface)."""
        threading.Thread(target=self._overlay.hide_widget, args=(self._wid,), daemon=True).start()

    @Slot()
    def start_move(self) -> None:
        handle = self._view.windowHandle()
        if handle is not None:
            handle.startSystemMove()  # déplacement natif, suivi ensuite par Overlay.sync_moves


def app_icon() -> QIcon:
    """Icône de l'application (zone de notification) : pastille bleue « LMU »."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#4fc3f7"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(2, 2, 60, 60), 14, 14)
    p.setPen(QColor("#0f1115"))
    p.setFont(QFont("Segoe UI", 19, QFont.Weight.Bold))
    p.drawText(QRectF(0, 0, 64, 64), Qt.AlignmentFlag.AlignCenter, "LMU")
    p.end()
    return QIcon(pix)


class Tray(QObject):
    """Icône de la zone de notification : l'application tourne tant qu'on ne choisit pas « Quitter »,
    l'interface ingénieur s'ouvre et se ferme sans toucher à l'overlay course."""

    def __init__(self, app: QApplication, overlay, open_main, title: str, quit_app) -> None:
        super().__init__()
        self.icon = QSystemTrayIcon(app_icon())
        self.icon.setToolTip(title)
        self.title = title
        self.told = False
        menu = QMenu()
        actions = [("Interface ingénieur", open_main)]
        if overlay is not None:
            def in_thread(fn):  # l'overlay enregistre sur le serveur : hors du thread de l'interface
                return lambda: threading.Thread(target=fn, daemon=True).start()

            actions += [("Afficher / masquer l'overlay course", in_thread(overlay.toggle)),
                        ("Mode placement (déplacer, retirer des widgets)", in_thread(overlay.toggle_placement))]
        for label, fn in actions:
            action = QAction(label, menu)
            action.triggered.connect(fn)
            menu.addAction(action)
        menu.addSeparator()
        quit_action = QAction("Quitter LMU Assistant", menu)
        quit_action.triggered.connect(quit_app)
        menu.addAction(quit_action)
        self.menu = menu
        self.icon.setContextMenu(menu)
        self.icon.activated.connect(
            lambda reason: open_main() if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                                                     QSystemTrayIcon.ActivationReason.DoubleClick) else None
        )
        self.icon.show()

    def main_hidden(self) -> None:
        if not self.told:  # une seule fois : où est passée l'application
            self.told = True
            self.icon.showMessage(self.title, "L'overlay course continue. Icône LMU près de l'horloge : "
                                  "rouvrir l'interface ou quitter.", app_icon(), 5000)


def run(overlay, url_for, title_for, states: dict, quit_after: float | None = None,
        main_url: str | None = None, main_title: str = "LMU Assistant", show_main: bool = True) -> int:
    """Crée une fenêtre par widget (si `overlay`) et la fenêtre de l'interface ingénieur (`main_url`, affichée
    au lancement si `show_main`), puis exécute la boucle Qt (thread principal) jusqu'à « Quitter ».
    `states` : état initial de chaque fenêtre (WindowState). Renvoie le nombre de fenêtres de widgets créées."""
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(main_title)
    app.setWindowIcon(app_icon())

    def quit_app() -> None:
        """Quitte vraiment : la fenêtre de l'interface ne doit plus se contenter de se cacher."""
        app.setProperty("lmu_quitting", True)
        app.quit()
    script = _channel_script()
    keep = []  # ponts, canaux et fenêtre principale : gardés en vie tant que l'application tourne
    if overlay is None:
        states = {}
    for wid, state in states.items():
        view = View(title_for(wid), state.click_through)
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
    if overlay is not None:
        threading.Thread(target=overlay.run, name="overlay", daemon=True).start()
    main = None

    def open_main() -> None:
        nonlocal main
        if main is None:
            main = MainWindow(main_url, main_title)
            main.keep_running = tray is not None
            main.on_hidden = tray.main_hidden if tray is not None else None
            print(f"[interface] fenêtre ouverte : {main_url}")
        main.showNormal()
        main.raise_()
        main.activateWindow()

    # Icône de notification : seulement avec l'overlay (sans lui, fermer l'interface quitte, comme avant).
    tray = None
    if overlay is not None and main_url and QSystemTrayIcon.isSystemTrayAvailable():
        tray = Tray(app, overlay, open_main, main_title, quit_app)
        app.setQuitOnLastWindowClosed(False)
        keep.append(tray)
    if main_url and show_main:
        open_main()
    # Ctrl+C dans la console : Python ne reprend la main que si la boucle Qt lui laisse du temps.
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, lambda *_: quit_app())
    tick = QTimer()
    tick.timeout.connect(lambda: None)
    tick.start(300)
    if quit_after:
        QTimer.singleShot(int(quit_after * 1000), quit_app)
    if overlay is not None:
        print(f"[overlay] {len(states)} fenêtres de widgets (Qt)")
    app.exec()
    if tray is not None:
        tray.icon.hide()  # pas d'icône fantôme dans la zone de notification
    return len(states)
