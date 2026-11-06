from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from .archive import make_zip, safe_filename
from .downloader import download_url
from .github_api import GitHubAPI
from .splitter import split_file

DEFAULT_PART_SIZE = 19 * 1024 * 1024
DEFAULT_MAX_INPUT_BYTES = 1_900_000_000


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Required environment variable is missing: {name}")
    return value


def validate_job_id(job_id: str) -> str:
    if not re.fullmatch(r"job_[A-Za-z0-9_-]{8,64}", job_id):
        raise ValueError("job_id must match job_[A-Za-z0-9_-]{8,64}")
    return job_id


def create_input_file(api: GitHubAPI, source_type: str, work_dir: str, max_bytes: int, job_id: str) -> tuple[str, str, int]:
    source_path = os.path.join(work_dir, "source.bin")
    requested_filename = os.getenv("FS_FILENAME", "").strip()

    if source_type == "url":
        url = required_env("FS_SOURCE_URL")
        if not requested_filename:
            from urllib.parse import urlsplit
            requested_filename = Path(urlsplit(url).path).name or "input.bin"
        filename = safe_filename(requested_filename)
        size = download_url(url, source_path, max_bytes)
        return source_path, filename, size

    if source_type == "release_asset":
        release_id = required_env("FS_INPUT_RELEASE_ID")
        asset_id = required_env("FS_INPUT_ASSET_ID")
        if not release_id.isdigit() or not asset_id.isdigit():
            raise ValueError("input_release_id and input_asset_id must be numeric GitHub IDs")
        release = api.request("GET", f"{api.repo_path}/releases/{int(release_id)}").json()
        expected_tag = f"fs-input-{job_id}"
        if release.get("tag_name") != expected_tag or not release.get("draft"):
            raise ValueError("The supplied input Release is not the draft Release created for this job_id")
        asset = next((item for item in release.get("assets", []) if int(item.get("id", -1)) == int(asset_id)), None)
        if asset is None:
            raise ValueError("input_asset_id does not belong to the supplied input Release")
        filename = safe_filename(requested_filename or asset.get("name", "input.bin"))
        try:
            size = api.download_release_asset(int(asset_id), source_path, max_bytes)
            if size == 0:
                raise ValueError("The uploaded input file is empty")
        finally:
            # The upload Release is temporary and is removed after the download attempt.
            try:
                api.delete_release_and_tag(int(release_id), release.get("tag_name"))
            except Exception as exc:
                print(f"::warning::Could not delete temporary input Release {release_id}: {exc}")
        return source_path, filename, size

    raise ValueError("source_type must be 'url' or 'release_asset'")


def main() -> None:
    api = GitHubAPI.from_env()
    job_id = validate_job_id(required_env("FS_JOB_ID"))
    source_type = required_env("FS_SOURCE_TYPE")
    part_size = int(os.getenv("FS_PART_SIZE", str(DEFAULT_PART_SIZE)))
    max_bytes = int(os.getenv("FS_MAX_INPUT_BYTES", str(DEFAULT_MAX_INPUT_BYTES)))
    if part_size != DEFAULT_PART_SIZE:
        raise ValueError("This project is configured for exactly 19 MiB parts; FS_PART_SIZE must be 19922944")
    if max_bytes <= 0:
        raise ValueError("FS_MAX_INPUT_BYTES must be positive")

    output_tag = f"fs-output-{job_id}"
    output_release: dict[str, Any] | None = None
    work_dir = tempfile.mkdtemp(prefix=f"filesplitter-{job_id}-")

    try:
        source_path, source_filename, source_size = create_input_file(api, source_type, work_dir, max_bytes, job_id)
        print(f"Downloaded input for {job_id}: {source_size} bytes")

        archive_name = f"{Path(source_filename).stem or 'archive'}.zip"
        archive_path = os.path.join(work_dir, archive_name)
        make_zip(source_path, source_filename, archive_path)
        os.remove(source_path)

        parts_dir = os.path.join(work_dir, "parts")
        part_paths = split_file(archive_path, parts_dir, part_size)
        os.remove(archive_path)
        if len(part_paths) > 999:
            raise ValueError("This Release would exceed the supported limit of 999 parts plus response.json")

        output_release = api.create_release(
            output_tag,
            f"FileSplitter output {job_id}",
            draft=True,
            release_body=f"filesplitter_created_at={int(time.time())}",
        )
        upload_url = output_release["upload_url"]
        part_urls: list[str] = []

        for index, part_path in enumerate(part_paths, start=1):
            asset_name = f"part{index}.zip"
            asset = api.upload_release_asset(upload_url, part_path, asset_name, "application/zip")
            part_urls.append(asset["browser_download_url"])
            print(f"Uploaded {asset_name}: {os.path.getsize(part_path)} bytes")

        response_payload = {"parts": part_urls}
        response_path = os.path.join(work_dir, "response.json")
        with open(response_path, "w", encoding="utf-8") as response_file:
            json.dump(response_payload, response_file, ensure_ascii=False, separators=(",", ":"))
        api.upload_release_asset(upload_url, response_path, "response.json", "application/json")

        # Publish only after every part and response.json have been uploaded.
        api.request(
            "PATCH",
            f"{api.repo_path}/releases/{output_release['id']}",
            json={"draft": False, "make_latest": "false"},
        )
        print(f"::notice::FileSplitter completed: {job_id}; parts={len(part_paths)}; release_tag={output_tag}")
    except Exception:
        if output_release is not None:
            try:
                api.delete_release_and_tag(int(output_release["id"]), output_tag)
            except Exception as cleanup_error:
                print(f"::warning::Could not remove incomplete output Release: {cleanup_error}")
        raise
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
