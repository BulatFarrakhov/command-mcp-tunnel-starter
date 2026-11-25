"""The Windows test ZIP must contain everything needed for offline source provisioning."""

import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_windows_package_contents_and_checksum(tmp_path):
    subprocess.run([sys.executable, str(ROOT / "vm" / "build_windows_package.py"), str(tmp_path)], check=True)
    archive = tmp_path / "command-mcp-linux-vm-windows-home-preview.zip"
    sums = (tmp_path / "SHA256SUMS.txt").read_text(encoding="ascii").split()[0]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == sums
    with zipfile.ZipFile(archive) as zipped:
        names = set(zipped.namelist())
        assert {
            "Setup.cmd", "uv.lock", "pyproject.toml", "vm/windows/Prepare.ps1",
            "vm/windows/Install.ps1", "vm/windows/Manage.ps1", "vm/windows/Uninstall.ps1",
            "vm/guest/bootstrap.sh", "vm/guest/workspace-AGENTS.md",
            "src/command_mcp_tunnel_starter/server.py",
        } <= names
        assert all(".git" not in name and not name.endswith((".env", ".pyc")) for name in names)
