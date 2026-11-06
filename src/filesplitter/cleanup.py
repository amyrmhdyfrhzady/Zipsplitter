from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from .github_api import GitHubAPI


def parse_github_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def latest_asset_time(release: dict[str, Any]) -> datetime | None:
    timestamps = [
        parsed
        for asset in release.get("assets", [])
        if (parsed := parse_github_time(asset.get("created_at"))) is not None
    ]
    return max(timestamps) if timestamps else None


def input_draft_time(release: dict[str, Any]) -> datetime | None:
    # Clients write an explicit Unix timestamp into the draft body so empty drafts
    # can also expire without relying on the target commit's created_at value.
    body = release.get("body") or ""
    match = re.search(r"(?:^|\s)filesplitter_created_at=(\d+)(?:$|\s)", body)
    body_time = datetime.fromtimestamp(int(match.group(1)), timezone.utc) if match else None
    asset_time = latest_asset_time(release)
    candidates = [value for value in (body_time, asset_time) if value is not None]
    return max(candidates) if candidates else None


def main() -> None:
    api = GitHubAPI.from_env()
    output_ttl = int(os.getenv("FS_RELEASE_TTL_SECONDS", "18000"))
    input_ttl = int(os.getenv("FS_INPUT_DRAFT_TTL_SECONDS", "86400"))
    now = datetime.now(timezone.utc)
    page = 1
    deleted = 0
    all_releases: list[dict[str, Any]] = []

    # Fetch all pages before deleting anything; deleting page 1 while paging can shift
    # subsequent pages and cause some Releases to be skipped.
    while True:
        releases = api.list_releases(page)
        if not releases:
            break
        all_releases.extend(releases)
        if len(releases) < 100:
            break
        page += 1

    for release in all_releases:
        tag = str(release.get("tag_name") or "")
        if tag.startswith("fs-output-"):
            # Published output TTL starts at published_at. An orphan draft uses
            # the recorded creation time or latest uploaded asset timestamp.
            created_at = parse_github_time(release.get("published_at")) or input_draft_time(release)
            ttl = output_ttl
            reason = "expired output Release"
        elif tag.startswith("fs-input-") and release.get("draft"):
            # For draft input Releases, use the asset upload timestamp, not the
            # release's created_at (which can reflect the target commit date).
            created_at = input_draft_time(release)
            ttl = input_ttl
            reason = "stale input draft"
        else:
            continue

        if created_at is None or now - created_at < timedelta(seconds=ttl):
            continue
        release_id = int(release["id"])
        try:
            api.delete_release_and_tag(release_id, tag)
            deleted += 1
            print(f"::notice::Deleted {reason}: {tag} (release_id={release_id})")
        except Exception as exc:
            print(f"::warning::Could not delete {tag} (release_id={release_id}): {exc}")

    print(f"::notice::FileSplitter cleanup finished; deleted={deleted}")


if __name__ == "__main__":
    main()
