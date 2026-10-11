"""Build a deterministic, source-only Windows test package from tracked files."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
NAME = "command-mcp-linux-vm-windows-home-preview.zip"
ROOT_FILES = {"Setup.cmd", "README.md", "SECURITY.md", "pyproject.toml", "uv.lock"}
PREFIXES = ("src/", "vm/guest/", "vm/windows/")
DOCS = {"docs/WINDOWS-VM.md"}


def main() -> None:
    output_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "dist"
    output_dir.mkdir(parents=True, exist_ok=True)
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).split(b"\0")
    paths = sorted(
        path.decode() for path in tracked if path and (
            path.decode() in ROOT_FILES | DOCS or path.decode().startswith(PREFIXES)
        )
    )
    if "Setup.cmd" not in paths or "vm/windows/Prepare.ps1" not in paths or "uv.lock" not in paths:
        raise SystemExit("Required Windows setup files are missing from Git")
    archive = output_dir / NAME
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for name in paths:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zipped.writestr(info, (ROOT / name).read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output_dir / "SHA256SUMS.txt").write_text(f"{digest}  {NAME}\n", encoding="ascii")
    print(f"{archive} ({len(paths)} files, SHA-256 {digest})")


if __name__ == "__main__":
    main()
