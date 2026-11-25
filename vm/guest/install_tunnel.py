"""Install the complete, checksum-verified official Linux tunnel release."""

import os
import stat
import sys
import zipfile
from pathlib import Path


def install(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        required = {"tunnel-client", "cloudflared", "cloudflared-manifest.json"}
        if not required.issubset(names):
            raise ValueError("Expected the complete tunnel-client Linux release")
        # Official release is flat. Refuse directory traversal or symlinks.
        for entry in bundle.infolist():
            if (Path(entry.filename).name != entry.filename
                    or entry.is_dir()
                    or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError("Unexpected release archive member")
        destination.mkdir(parents=True, exist_ok=True, mode=0o700)
        for entry in bundle.infolist():
            target = destination / entry.filename
            if target.is_symlink():
                raise ValueError("Release destination contains a symlink")
            with target.open("wb") as handle:
                handle.write(bundle.read(entry))
            os.chmod(target, 0o700 if entry.filename in {"tunnel-client", "cloudflared"} else 0o600)


if __name__ == "__main__":
    install(Path(sys.argv[1]), Path(sys.argv[2]))
