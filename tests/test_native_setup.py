import hashlib
import importlib.util
import zipfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("native_setup", Path(__file__).resolve().parents[1] / "scripts/setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def test_unit_paths_and_restart():
    unit = setup.unit_text("tunnel", '/home/a b/.venv/bin/python', '/home/a b/100%')
    assert 'WorkingDirectory=/home/a b/100%%' in unit
    assert 'ExecStart="/home/a b/.venv/bin/python" -m command_mcp_tunnel_starter tunnel' in unit
    assert 'Restart=always' in unit
    assert 'After=command-mcp.service' in unit


def make_zip(path, extra=None):
    with zipfile.ZipFile(path, "w") as z:
        for name in setup.executable_names("linux"):
            z.writestr(name, b"test")
        if extra:
            z.writestr(extra, b"bad")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_verified_extraction(tmp_path):
    archive = tmp_path / "release.zip"
    digest = make_zip(archive)
    setup.extract_verified(archive, tmp_path / "dest", digest, "linux")
    assert (tmp_path / "dest/tunnel-client").read_bytes() == b"test"


@pytest.mark.parametrize("extra", ["../escape", "dir/file", "C:escape"])
def test_unsafe_archive(tmp_path, extra):
    archive = tmp_path / "release.zip"
    digest = make_zip(archive, extra)
    with pytest.raises(ValueError):
        setup.extract_verified(archive, tmp_path / "dest", digest, "linux")
    assert not (tmp_path / "dest").exists()


def test_bad_hash(tmp_path):
    archive = tmp_path / "release.zip"
    make_zip(archive)
    with pytest.raises(ValueError, match="SHA-256"):
        setup.extract_verified(archive, tmp_path / "dest", "0" * 64, "linux")
