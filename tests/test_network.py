import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from lmu_assistant import __version__, network
from lmu_assistant.server import create_app
from lmu_assistant.sources import get_source


class FakeSocket:
    """Remplace socket.socket : getsockname renvoie l'adresse choisie."""

    def __init__(self, addr=None, error=False):
        self.addr, self.error = addr, error

    def __call__(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def connect(self, address):
        if self.error:
            raise OSError("réseau indisponible")

    def getsockname(self):
        return (self.addr, 54321)


def _fake_getaddrinfo(addrs):
    def getaddrinfo(host, port, family=0, *args, **kwargs):
        return [(family, 2, 17, "", (a, 0)) for a in addrs]
    return getaddrinfo


def test_lan_ips_primary_first_and_filtered(monkeypatch):
    monkeypatch.setattr(network.socket, "socket", FakeSocket("192.168.1.20"))
    monkeypatch.setattr(
        network.socket,
        "getaddrinfo",
        _fake_getaddrinfo(["127.0.1.1", "169.254.3.4", "10.0.0.5", "192.168.1.20"]),
    )
    assert network.lan_ipv4_addresses() == ["192.168.1.20", "10.0.0.5"]


def test_lan_ips_fallback_when_udp_fails(monkeypatch):
    monkeypatch.setattr(network.socket, "socket", FakeSocket(error=True))
    monkeypatch.setattr(network.socket, "getaddrinfo", _fake_getaddrinfo(["127.0.0.1", "172.16.4.2"]))
    assert network.lan_ipv4_addresses() == ["172.16.4.2"]


def test_lan_ips_none(monkeypatch):
    monkeypatch.setattr(network.socket, "socket", FakeSocket("127.0.0.1"))

    def boom(*a, **k):
        raise OSError

    monkeypatch.setattr(network.socket, "getaddrinfo", boom)
    assert network.lan_ipv4_addresses() == []


def test_lan_urls_respects_host(monkeypatch):
    monkeypatch.setattr(network, "lan_ipv4_addresses", lambda: ["192.168.1.20"])
    assert network.lan_urls(8765) == ["http://192.168.1.20:8765"]
    assert network.lan_urls(8765, "127.0.0.1") == []
    assert network.lan_urls(9000, "192.168.1.30") == ["http://192.168.1.30:9000"]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(network, "lan_ipv4_addresses", lambda: ["192.168.1.20", "10.0.0.5"])
    app = create_app(get_source("mock"), hz=50)
    app.state.port = 8765
    with TestClient(app) as c:
        yield c


def test_api_info_shape(client):
    info = client.get("/api/info").json()
    assert info == {
        "version": __version__,
        "source": "mock",
        "port": 8765,
        "lan_urls": ["http://192.168.1.20:8765", "http://10.0.0.5:8765"],
        "lan_access": True,
    }


def _assert_svg(resp):
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")
    root = ET.fromstring(resp.text)
    assert root.tag.endswith("svg")
    assert root.get("viewBox")


def test_qr_svg_default_and_explicit(client):
    _assert_svg(client.get("/api/qr.svg"))
    _assert_svg(client.get("/api/qr.svg", params={"url": "http://10.0.0.5:8765"}))


def test_qr_svg_rejects_too_long(client):
    assert client.get("/api/qr.svg", params={"url": "x" * 2000}).status_code == 400


def test_connect_page_served(client):
    assert "qr" in client.get("/connect.html").text
    assert "connect.html" in client.get("/").text
