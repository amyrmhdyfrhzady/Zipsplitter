from __future__ import annotations

import os
from pathlib import Path


def split_file(archive_path: str, output_dir: str, part_size: int) -> list[str]:
    if part_size <= 0:
        raise ValueError("part_size must be greater than zero")
    os.makedirs(output_dir, exist_ok=True)
    output_paths: list[str] = []
    part_number = 1
    with open(archive_path, "rb") as source:
        while True:
            block = source.read(part_size)
            if not block:
                break
            part_path = os.path.join(output_dir, f"part{part_number}.zip")
            with open(part_path, "wb") as part:
                part.write(block)
            output_paths.append(part_path)
            part_number += 1
    if not output_paths:
        raise RuntimeError("The ZIP archive produced no output parts")
    for index, path in enumerate(output_paths[:-1]):
        if os.path.getsize(path) != part_size:
            raise RuntimeError(f"Part {index + 1} has an unexpected size")
    if any(os.path.getsize(path) > part_size for path in output_paths):
        raise RuntimeError("A generated part exceeds the configured part size")
    return output_paths
