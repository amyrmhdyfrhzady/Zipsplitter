"""Small Python client for the GitHub Actions FileSplitter API.

Requires: pip install requests
Set GITHUB_TOKEN in the environment. Never put a token in source code.
"""
from __future__ import annotations

import argparse
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import requests

API_ROOT = os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/")
API_VERSION = "2026-03-10"
MAX_UPLOAD_BYTES = int(os.getenv("FILESPLITTER_MAX_INPUT_BYTES", "1900000000"))


class FileSplitterClient:
    def __init__(self, owner: str, repo: str, token: str, ref: str = "main") -> None:
        if not token:
            raise ValueError("Set GITHUB_TOKEN in your environment")
        self.owner, self.repo, self.ref = owner, repo, ref
        self.root = f"{API_ROOT}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "FileSplitter-API-Python-Client/1.0",
        })

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        response = self.session.request(method, url, timeout=(20, 120), **kwargs)
        if not response.ok:
            try:
                detail = response.json().get("message", response.text[:1000])
            except ValueError:
                detail = response.text[:1000]
            raise RuntimeError(f"GitHub API HTTP {response.status_code}: {detail}")
        return response

    @staticmethod
    def _new_job_id() -> str:
        return f"job_{uuid.uuid4().hex}"

    def _dispatch(self, job_id: str, inputs: dict[str, str]) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"{self.root}/actions/workflows/process.yml/dispatches",
            json={"ref": self.ref, "inputs": {"job_id": job_id, **inputs}, "return_run_details": True},
        )
        return response.json()

    def submit_url(self, url: str, filename: str | None = None) -> dict[str, Any]:
        job_id = self._new_job_id()
        inferred_name = Path(unquote(urlsplit(url).path)).name or "input.bin"
        inputs = {"source_type": "url", "source_url": url, "filename": filename or inferred_name}
        run = self._dispatch(job_id, inputs)
        return {"job_id": job_id, **run}

    def submit_file(self, file_path: str) -> dict[str, Any]:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        size = path.stat().st_size
        if size <= 0 or size > MAX_UPLOAD_BYTES:
            raise ValueError(f"Input must be between 1 byte and {MAX_UPLOAD_BYTES} bytes")

        job_id = self._new_job_id()
        safe_name = re.sub(r"[^A-Za-z0-9._ -]", "_", path.name).lstrip(".")[:180] or "input.bin"
        tag = f"fs-input-{job_id}"
        created = self._request(
            "POST",
            f"{self.root}/releases",
            json={"tag_name": tag, "name": f"FileSplitter input {job_id}", "body": f"filesplitter_created_at={int(time.time())}", "draft": True, "prerelease": False, "generate_release_notes": False},
        ).json()

        try:
            upload_url = created["upload_url"].split("{", 1)[0]
            with path.open("rb") as stream:
                uploaded = self._request(
                    "POST",
                    upload_url,
                    params={"name": safe_name},
                    data=stream,
                    headers={"Content-Type": "application/octet-stream", "Content-Length": str(size)},
                ).json()
            run = self._dispatch(job_id, {
                "source_type": "release_asset",
                "input_release_id": str(created["id"]),
                "input_asset_id": str(uploaded["id"]),
                "filename": safe_name,
            })
            return {"job_id": job_id, "input_release_id": created["id"], **run}
        except Exception:
            # Best-effort cleanup; preserve the original upload/dispatch exception.
            try:
                self.session.delete(f"{self.root}/releases/{created['id']}", timeout=(20, 60))
                self.session.delete(f"{self.root}/git/refs/tags/{quote(tag, safe='')}", timeout=(20, 60))
            except requests.RequestException:
                pass
            raise

    def get_status(self, run_id: int) -> dict[str, Any]:
        return self._request("GET", f"{self.root}/actions/runs/{run_id}").json()

    def wait(self, run_id: int, poll_seconds: int = 10, timeout_seconds: int = 5 * 60 * 60) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            status = self.get_status(run_id)
            if status.get("status") == "completed":
                return status
            time.sleep(max(2, poll_seconds))
        raise TimeoutError(f"Workflow run {run_id} did not finish before the client timeout")

    def get_result(self, job_id: str) -> dict[str, Any]:
        tag = f"fs-output-{job_id}"
        release = self._request("GET", f"{self.root}/releases/tags/{quote(tag, safe='')}").json()
        asset = next((item for item in release.get("assets", []) if item.get("name") == "response.json"), None)
        if not asset:
            raise RuntimeError("response.json was not found in the output Release")
        response = self._request(
            "GET",
            f"{self.root}/releases/assets/{asset['id']}",
            headers={"Accept": "application/octet-stream"},
        )
        return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="Client for FileSplitter-API (GitHub Actions)")
    parser.add_argument("--repo", required=True, help="OWNER/REPO")
    parser.add_argument("--ref", default="main", help="Branch containing the workflows")
    sub = parser.add_subparsers(dest="command", required=True)

    url_parser = sub.add_parser("submit-url")
    url_parser.add_argument("url")
    url_parser.add_argument("--filename", default="input.bin")

    file_parser = sub.add_parser("submit-file")
    file_parser.add_argument("path")

    status_parser = sub.add_parser("status")
    status_parser.add_argument("run_id", type=int)

    result_parser = sub.add_parser("result")
    result_parser.add_argument("job_id")

    args = parser.parse_args()
    if "/" not in args.repo:
        parser.error("--repo must be OWNER/REPO")
    owner, repo = args.repo.split("/", 1)
    client = FileSplitterClient(owner, repo, os.getenv("GITHUB_TOKEN", ""), args.ref)

    if args.command == "submit-url":
        result = client.submit_url(args.url, args.filename)
    elif args.command == "submit-file":
        result = client.submit_file(args.path)
    elif args.command == "status":
        result = client.get_status(args.run_id)
    else:
        result = client.get_result(args.job_id)
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
