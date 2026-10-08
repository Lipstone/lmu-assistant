"""Diagnostic transparence overlay LMU : mesure à l'écran ce qui se voit à travers des fenêtres pywebview.
Lancer : python diag_transparence.py   (pip install pywebview pillow)
Ne touche à rien d'autre ; ferme ses fenêtres à la fin et affiche un tableau de résultats."""
import ctypes, sys, threading, time
from ctypes import wintypes
import webview
from PIL import ImageGrab

PAGE = """<html><body style='margin:0;background:transparent'>
<div style='position:absolute;left:0;top:0;width:100px;height:100px;background:transparent'></div>
<div style='position:absolute;left:100px;top:0;width:100px;height:100px;background:rgba(0,0,0,0.5)'></div>
<div style='position:absolute;left:0;top:100px;width:200px;height:100px;background:rgb(0,0,255)'></div>
</body></html>"""
BG = "<html><body style='margin:0;background:rgb(255,0,0)'></body></html>"
VARIANTS = ["A_defaut", "B_blur", "C_blur_layered", "D_colorkey", "E_extendframe", "F_extendframe_layered"]
user32, dwmapi, gdi32 = ctypes.windll.user32, ctypes.windll.dwmapi, ctypes.windll.gdi32

class BB(ctypes.Structure):
    _fields_ = [("dwFlags", wintypes.DWORD), ("fEnable", wintypes.BOOL), ("hRgnBlur", wintypes.HANDLE), ("fT", wintypes.BOOL)]
class MARGINS(ctypes.Structure):
    _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int), ("t", ctypes.c_int), ("b", ctypes.c_int)]
user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
user32.SetLayeredWindowAttributes.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_ubyte, wintypes.DWORD]
gdi32.CreateRectRgn.restype = wintypes.HANDLE

def native(win, variant):
    from System import Action
    from System.Drawing import Color
    form = win.native
    def apply():
        hwnd = ctypes.c_void_p(form.Handle.ToInt64())
        if variant == "A_defaut":
            return
        if variant == "D_colorkey":
            form.BackColor = Color.FromArgb(255, 1, 0, 1)
            user32.SetWindowLongW(hwnd, -20, user32.GetWindowLongW(hwnd, -20) | 0x80000)
            user32.SetLayeredWindowAttributes(hwnd, 1 | 1 << 16, 255, 1)
            return
        form.BackColor = Color.Black
        if variant.startswith("E") or variant.startswith("F"):
            m = MARGINS(-1, -1, -1, -1)
            dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(m))
        else:
            rgn = gdi32.CreateRectRgn(0, 0, -1, -1)
            dwmapi.DwmEnableBlurBehindWindow(hwnd, ctypes.byref(BB(3, True, rgn, False)))
        if variant in ("C_blur_layered", "F_extendframe_layered"):
            user32.SetWindowLongW(hwnd, -20, user32.GetWindowLongW(hwnd, -20) | 0x80000 | 0x20)
            user32.SetLayeredWindowAttributes(hwnd, 0, 255, 2)
        form.Invalidate(True)
    form.Invoke(Action(apply))

wins = {}
def run():
    time.sleep(4)
    for i, v in enumerate(VARIANTS):
        native(wins[v], v)
    time.sleep(3)
    img = ImageGrab.grab(all_screens=False)
    print("\nRESULTATS (attendu : transparent=(255,0,0) rouge du fond, semi=(~128,0,0), bleu=(0,0,255))")
    print("fond rouge seul :", img.getpixel((50, 650)))
    for i, v in enumerate(VARIANTS):
        x, y = 40 + i * 220, 60
        print(f"{v:24s} transparent={img.getpixel((x+50, y+50))} semi={img.getpixel((x+150, y+50))} bleu={img.getpixel((x+100, y+150))}")
    img.crop((0, 0, 40 + len(VARIANTS) * 220, 320)).save("diag_transparence.png")
    print("capture : diag_transparence.png")
    for w in list(wins.values()) + [bgwin]:
        w.destroy()

bgwin = webview.create_window("diag fond", html=BG, x=0, y=0, width=40 + len(VARIANTS) * 220 + 40, height=720, frameless=True)
for i, v in enumerate(VARIANTS):
    wins[v] = webview.create_window(f"diag {v}", html=PAGE, x=40 + i * 220, y=60, width=200, height=200,
                                    frameless=True, on_top=True, transparent=True, background_color="#000000")
webview.start(run)
print("pywebview", webview.__version__ if hasattr(webview, "__version__") else "?", "| windows", sys.getwindowsversion())
