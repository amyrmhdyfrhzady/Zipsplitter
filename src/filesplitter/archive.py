from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path


def safe_filename(value: str, fallback: str = "input.bin") -> str:
    name = Path(value.replace("\\", "/")).name.strip()
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name)
    name = name.lstrip(".").strip()
    if not name or name in (".", ".."):
        return fallback
    return name[:180]


def make_zip(source_path: str, source_filename: str, archive_path: str) -> None:
    arcname = safe_filename(source_filename)
    with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        archive.write(source_path, arcname=arcname)
    if not os.path.isfile(archive_path) or os.path.getsize(archive_path) == 0:
        raise RuntimeError("ZIP creation failed or produced an empty archive")
