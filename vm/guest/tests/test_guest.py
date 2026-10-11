import importlib.util
import json
import os
import stat
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest


GUEST = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, GUEST / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def release(path, extra=None):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("tunnel-client", b"client")
        archive.writestr("cloudflared", b"runtime")
        archive.writestr("cloudflared-manifest.json", "{}")
        if extra:
            archive.writestr(extra, "unexpected")


def test_complete_tunnel_release_and_modes(tmp_path):
    installer = module("install_tunnel")
    archive = tmp_path / "release.zip"
    destination = tmp_path / "release"
    release(archive)
    installer.install(archive, destination)
    assert (destination / "cloudflared").read_bytes() == b"runtime"
    assert (destination / "cloudflared-manifest.json").is_file()
    if os.name != "nt":
        assert stat.S_IMODE((destination / "tunnel-client").stat().st_mode) == 0o700
        assert stat.S_IMODE((destination / "cloudflared-manifest.json").stat().st_mode) == 0o600


@pytest.mark.parametrize("member", ["../escape", "/escape", "subdir/escape"])
def test_rejects_archive_paths_before_writing(tmp_path, member):
    installer = module("install_tunnel")
    archive = tmp_path / "release.zip"
    release(archive, member)
    destination = tmp_path / "release"
    with pytest.raises(ValueError, match="archive member"):
        installer.install(archive, destination)
    assert not destination.exists()


def test_rejects_incomplete_runtime(tmp_path):
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("tunnel-client", b"incomplete")
    with pytest.raises(ValueError, match="complete"):
        module("install_tunnel").install(archive, tmp_path / "release")


@pytest.mark.skipif(os.name == "nt", reason="Linux guest config permissions")
def test_local_config_is_private_and_never_prints_key(tmp_path, monkeypatch, capsys):
    configure = module("configure")
    target = tmp_path / "private" / "config.json"
    monkeypatch.setattr(configure, "config_path", lambda: target)
    monkeypatch.setattr(configure.os, "isatty", lambda _: True)
    monkeypatch.setattr("builtins.input", lambda _: "tunnel_" + "a" * 32)
    secret = "test-runtime-key-not-a-real-secret"
    monkeypatch.setattr(configure.getpass, "getpass", lambda _: secret)
    validate = configure.validate
    monkeypatch.setattr(configure, "validate", lambda settings: validate({**settings, "default_cwd": str(tmp_path)}))
    configure.main()
    settings = json.loads(target.read_text())
    assert settings["runtime_api_key"] == secret
    assert settings["default_cwd"] == "/workspace"
    assert "Windows host disks" in settings["workspace_policy"]
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    assert secret not in capsys.readouterr().out
    before = target.read_bytes()
    monkeypatch.setattr(configure, "load_config", lambda: settings)
    monkeypatch.setattr(configure.getpass, "getpass", lambda _: pytest.fail("Asked for key again"))
    configure.main()
    assert target.read_bytes() == before


def test_setup_refuses_hidden_prompt_without_terminal(tmp_path, monkeypatch):
    configure = module("configure")
    monkeypatch.setattr(configure, "config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr(configure.os, "isatty", lambda _: False)
    with pytest.raises(SystemExit, match="interactive guest console"):
        configure.main()


@pytest.mark.parametrize("bind", ["0.0.0.0", "[::]", "*"])
def test_public_listener_rejected(monkeypatch, bind):
    verifier = module("verify")
    monkeypatch.setattr(verifier.subprocess, "run", lambda *a, **kw:
                        SimpleNamespace(stdout=f"LISTEN 0 128 {bind}:18102 0.0.0.0:*\n"))
    with pytest.raises(RuntimeError, match="loopback-only"):
        verifier.check_listeners({"server_port": 18102, "tunnel_health_port": 18103})


@pytest.mark.skipif(os.name == "nt", reason="Bash guest guard")
def test_bootstrap_wrong_home_fails_before_side_effects(tmp_path):
    result = subprocess.run(["bash", str(GUEST / "bootstrap.sh")],
                            env={**os.environ, "HOME": str(tmp_path)}, capture_output=True, text=True)
    assert result.returncode != 0
    assert "Run this script as the guest account agent" in result.stderr
