from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import quote

import requests

API_ROOT = os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/")
API_VERSION = "2026-03-10"


class GitHubAPIError(RuntimeError):
    def __init__(self, status_code: int, message: str, response_text: str = "") -> None:
        self.status_code = status_code
        self.response_text = response_text
        detail = response_text[:1200].strip()
        super().__init__(f"GitHub API returned HTTP {status_code}: {message}" + (f" | {detail}" if detail else ""))


class GitHubAPI:
    def __init__(self, token: str, owner: str, repo: str, timeout: tuple[int, int] = (20, 120)) -> None:
        if not token:
            raise ValueError("GITHUB_TOKEN is required")
        self.owner = owner
        self.repo = repo
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "FileSplitter-API/1.0",
            }
        )

    @classmethod
    def from_env(cls) -> "GitHubAPI":
        repository = os.getenv("GITHUB_REPOSITORY", "")
        if "/" not in repository:
            raise ValueError("GITHUB_REPOSITORY must be OWNER/REPO")
        owner, repo = repository.split("/", 1)
        return cls(os.getenv("GITHUB_TOKEN", ""), owner, repo)

    @property
    def repo_path(self) -> str:
        return f"/repos/{quote(self.owner, safe='')}/{quote(self.repo, safe='')}"

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: Any = None,
        headers: dict[str, str] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> requests.Response:
        url = path if path.startswith("https://") else f"{API_ROOT}{path}"
        for attempt in range(4):
            try:
                response = self.session.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    data=data,
                    headers=headers,
                    timeout=self.timeout,
                    allow_redirects=True,
                )
            except requests.RequestException as exc:
                if attempt == 3:
                    raise RuntimeError(f"GitHub request failed: {exc}") from exc
                if hasattr(data, "seek"):
                    data.seek(0)
                time.sleep(2**attempt)
                continue
            if response.status_code in expected:
                return response
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                retry_after = response.headers.get("Retry-After")
                delay = int(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                if hasattr(data, "seek"):
                    data.seek(0)
                time.sleep(min(max(delay, 1), 30))
                continue
            message = "request failed"
            try:
                message = response.json().get("message", message)
            except ValueError:
                pass
            raise GitHubAPIError(response.status_code, message, response.text)
        raise RuntimeError("GitHub request failed after retries")

    def create_release(
        self,
        tag: str,
        name: str,
        *,
        draft: bool,
        target_commitish: str | None = None,
        release_body: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "tag_name": tag,
            "name": name,
            "draft": draft,
            "prerelease": False,
            "generate_release_notes": False,
        }
        if target_commitish:
            body["target_commitish"] = target_commitish
        if release_body is not None:
            body["body"] = release_body
        response = self.request("POST", f"{self.repo_path}/releases", json=body, expected=(201,))
        return response.json()

    def upload_release_asset(self, upload_url: str, path: str, asset_name: str, content_type: str) -> dict[str, Any]:
        base_url = upload_url.split("{", 1)[0]
        safe_name = asset_name.replace("\\", "_").replace("/", "_")
        file_size = os.path.getsize(path)
        with open(path, "rb") as stream:
            response = self.request(
                "POST",
                base_url,
                params={"name": safe_name},
                data=stream,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Content-Type": content_type,
                    "Content-Length": str(file_size),
                },
                expected=(201,),
            )
        return response.json()

    def download_release_asset(self, asset_id: int, destination: str, max_bytes: int) -> int:
        path = f"{self.repo_path}/releases/assets/{asset_id}"
        headers = {"Accept": "application/octet-stream"}
        with self.session.get(f"{API_ROOT}{path}", headers=headers, stream=True, timeout=self.timeout, allow_redirects=True) as response:
            if response.status_code != 200:
                raise GitHubAPIError(response.status_code, "could not download Release asset", response.text[:1200])
            declared = response.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > max_bytes:
                raise ValueError(f"Input exceeds the configured maximum of {max_bytes} bytes")
            written = 0
            with open(destination, "wb") as output:
                for block in response.iter_content(chunk_size=1024 * 1024):
                    if not block:
                        continue
                    written += len(block)
                    if written > max_bytes:
                        raise ValueError(f"Input exceeds the configured maximum of {max_bytes} bytes")
                    output.write(block)
        return written

    def delete_release_and_tag(self, release_id: int, tag: str | None = None) -> None:
        self.request("DELETE", f"{self.repo_path}/releases/{release_id}", expected=(204, 404))
        if tag:
            encoded_tag = quote(tag, safe="")
            self.request("DELETE", f"{self.repo_path}/git/refs/tags/{encoded_tag}", expected=(204, 404))

    def list_releases(self, page: int = 1) -> list[dict[str, Any]]:
        response = self.request(
            "GET",
            f"{self.repo_path}/releases",
            params={"per_page": 100, "page": page},
        )
        return response.json()

    def get_release_by_tag(self, tag: str) -> dict[str, Any]:
        encoded_tag = quote(tag, safe="")
        response = self.request("GET", f"{self.repo_path}/releases/tags/{encoded_tag}")
        return response.json()

    def get_release_asset_bytes(self, asset_id: int) -> bytes:
        path = f"{self.repo_path}/releases/assets/{asset_id}"
        response = self.request(
            "GET",
            path,
            headers={"Accept": "application/octet-stream"},
            expected=(200,),
        )
        return response.content

    def dispatch(self, workflow_file: str, ref: str, inputs: dict[str, str]) -> dict[str, Any]:
        response = self.request(
            "POST",
            f"{self.repo_path}/actions/workflows/{quote(workflow_file, safe='')}/dispatches",
            json={"ref": ref, "inputs": inputs, "return_run_details": True},
            expected=(200,),
        )
        return response.json()

    def get_run(self, run_id: int) -> dict[str, Any]:
        response = self.request("GET", f"{self.repo_path}/actions/runs/{run_id}")
        return response.json()
