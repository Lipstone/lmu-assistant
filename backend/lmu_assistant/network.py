"""Accès depuis le réseau local : adresses IP du PC, URL à ouvrir et QR code.

Aucun appel réseau externe : la détection de l'adresse principale utilise un
socket UDP « connecté » vers une adresse privée, ce qui ne fait que demander
au système quelle interface serait utilisée (aucun paquet n'est envoyé).
"""

import ipaddress
import socket

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from . import __version__

DEFAULT_PORT = 8765
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
MAX_QR_LENGTH = 1024

# Adresse privée quelconque : sert seulement à choisir l'interface de sortie.
_PROBE_ADDRESS = ("10.255.255.255", 1)


def _is_lan_ipv4(addr: str) -> bool:
    try:
        ip = ipaddress.IPv4Address(addr)
    except ValueError:
        return False
    return not (ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast)


def _primary_ipv4() -> str | None:
    """Adresse de l'interface utilisée par défaut (astuce du socket UDP)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(_PROBE_ADDRESS)
            return s.getsockname()[0]
    except OSError:
        return None


def _hostname_ipv4s() -> list[str]:
    """Adresses associées au nom du PC (repli si l'astuce UDP échoue)."""
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        return []
    return [info[4][0] for info in infos]


def lan_ipv4_addresses() -> list[str]:
    """Adresses IPv4 du PC joignables depuis le réseau local (sans doublon).

    L'adresse principale vient en premier ; boucle locale et lien-local
    (169.254.x.x) sont exclues.
    """
    candidates = [_primary_ipv4(), *_hostname_ipv4s()]
    result: list[str] = []
    for addr in candidates:
        if addr and _is_lan_ipv4(addr) and addr not in result:
            result.append(addr)
    return result


def lan_urls(port: int, host: str = "0.0.0.0") -> list[str]:
    """URL de la page web pour les autres appareils du réseau local.

    Vide si le serveur n'écoute que sur la boucle locale (--host 127.0.0.1).
    """
    if host in LOOPBACK_HOSTS:
        return []
    if host not in ("0.0.0.0", "", "::"):
        return [f"http://{host}:{port}"] if _is_lan_ipv4(host) else []
    return [f"http://{ip}:{port}" for ip in lan_ipv4_addresses()]


def qr_svg(data: str) -> str:
    """QR code SVG (fond blanc) encodant `data`."""
    import qrcode
    from qrcode.image.svg import SvgPathFillImage

    img = qrcode.make(data, image_factory=SvgPathFillImage, border=2)
    return img.to_string(encoding="unicode")


# --- Routes -----------------------------------------------------------------

router = APIRouter()


def _settings(request: Request) -> tuple[int, str]:
    state = request.app.state
    port = getattr(state, "port", None) or request.url.port or DEFAULT_PORT
    host = getattr(state, "host", None) or "0.0.0.0"
    return port, host


@router.get("/api/info")
async def info(request: Request) -> dict:
    port, host = _settings(request)
    source = getattr(request.app.state, "source", None)
    return {
        "version": __version__,
        "source": getattr(source, "name", None),
        "port": port,
        "lan_urls": lan_urls(port, host),
        "lan_access": host not in LOOPBACK_HOSTS,
    }


@router.get("/api/qr.svg")
async def qr(request: Request, url: str | None = Query(None)) -> Response:
    if url is None:
        port, host = _settings(request)
        urls = lan_urls(port, host)
        url = urls[0] if urls else f"http://localhost:{port}"
    if not url or len(url) > MAX_QR_LENGTH:
        raise HTTPException(status_code=400, detail="URL vide ou trop longue")
    return Response(
        content=qr_svg(url),
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store"},
    )
