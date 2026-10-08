import json
import socket
import sys
import urllib.request
from pathlib import Path

from lmu_assistant import paths
from lmu_assistant.__main__ import build_app, build_parser
from lmu_assistant.launcher import start_server


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_launcher_starts_and_stops_server(tmp_path):
    port = free_port()
    parser = build_parser()
    args = parser.parse_args(["--source", "mock", "--host", "127.0.0.1", "--port", str(port),
                              "--config", str(tmp_path / "config.json")])
    server, thread = start_server(build_app(parser, args), args.host, args.port)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/info", timeout=5) as r:
            info = json.load(r)
        assert info["source"] == "mock" and info["port"] == port
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as r:
            assert "LMU Assistant" in r.read().decode()
    finally:
        server.should_exit = True
        thread.join(5)
    assert not thread.is_alive()


def test_paths_in_development():
    assert not paths.is_frozen()
    assert (paths.resource_dir() / "web" / "index.html").exists()
    assert paths.data_dir() == paths.REPO_ROOT / "data"


def test_paths_when_frozen(monkeypatch, tmp_path):
    exe = tmp_path / "LMU-Assistant.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert paths.is_frozen()
    assert paths.resource_dir() == tmp_path / "bundle"
    assert paths.data_dir() == Path(exe).resolve().parent / "data"
