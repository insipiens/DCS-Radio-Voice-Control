#!/usr/bin/env python3
"""Build the legacy developer/debug DCS Radio Voice Control ZIP.

The supported end-user distribution is the Inno Setup executable built from
installer/DCSRadioVoiceControl.iss.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import zipfile


ROOT_FILES = (
    "INSTALLATION.md",
    "LICENSE",
    "PIPER.md",
    "README.md",
    "configuration.bat",
    "install.bat",
    "maintenance.ps1",
    "repair.bat",
    "run.bat",
    "setup-stt.bat",
    "setup-stt.ps1",
    "setup-tts.bat",
    "setup-tts.ps1",
    "setup.bat",
    "setup.ps1",
    "uninstall.bat",
)
TREE_PATTERNS = (
    "dcs/*.lua",
    "src/dcs_radio_voice_control/*.py",
    "tools/__init__.py",
    "tools/build_radio_overlay.py",
    "tools/install.py",
    "tools/purge-local.ps1",
)
ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)
ARCHIVE_ROOT = "DCS-Radio-Voice-Control"


def release_files(root: Path) -> tuple[Path, ...]:
    paths = [root / name for name in ROOT_FILES]
    for pattern in TREE_PATTERNS:
        paths.extend(root.glob(pattern))
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Release input is missing: {missing[0]}")
    return tuple(sorted(set(paths), key=lambda path: path.relative_to(root).as_posix()))


def build_release(root: Path, output: Path) -> Path:
    root = root.resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for source in release_files(root):
            relative = source.relative_to(root).as_posix()
            archive_name = f"{ARCHIVE_ROOT}/{relative}"
            info = zipfile.ZipInfo(archive_name, ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes(), compresslevel=9)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("dist/DCS-Radio-Voice-Control-developer.zip"),
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    print(build_release(root, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
