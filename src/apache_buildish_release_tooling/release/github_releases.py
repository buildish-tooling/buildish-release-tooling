# Copyright 2026 The Apache Software Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""GitHub Release helpers used by the release-tooling CLI."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from apache_buildish_release_tooling.release.process import run_logged_command


class _ExternalGithubReadModel(BaseModel):
    """Tolerant GitHub Release API subset reader."""

    model_config = ConfigDict(extra="allow")


class _GitHubReleaseAssetRead(_ExternalGithubReadModel):
    id: int | None = None
    name: str | None = None


class _GitHubReleaseRead(_ExternalGithubReadModel):
    id: int | None = None
    draft: bool | None = None
    tag_name: str | None = None
    name: str | None = None
    body: str | None = None
    html_url: str | None = None
    url: str | None = None
    assets: list[_GitHubReleaseAssetRead] | None = None


def _release_read_view(release: Mapping[str, object]) -> _GitHubReleaseRead | None:
    try:
        return _GitHubReleaseRead.model_validate(release)
    except ValidationError:
        return None


def _validated_release_payload(payload: object, *, source: str) -> dict[str, object]:
    """Validate one GitHub Release object payload returned by the API."""

    if not isinstance(payload, dict):
        raise ValueError(f"{source} did not return an object payload")
    parsed = _release_read_view(payload)
    if parsed is None:
        raise ValueError(f"{source} returned a malformed GitHub Release payload")
    return parsed.model_dump(mode="python", exclude_none=True)


def list_releases(repository_slug: str) -> list[dict[str, object]]:
    """List GitHub releases for a repository through the GitHub CLI API."""

    completed = run_logged_command(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github+json",
            f"repos/{repository_slug}/releases?per_page=100",
        ]
    )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, list):
        return []
    releases: list[dict[str, object]] = []
    for release in payload:
        if not isinstance(release, dict):
            continue
        parsed = _release_read_view(release)
        if parsed is None:
            continue
        releases.append(parsed.model_dump(mode="python", exclude_none=True))
    return releases


def matching_draft_release_ids(
    releases: Sequence[Mapping[str, object]],
    *,
    tag_names: Sequence[str],
    release_name: str,
) -> list[int]:
    """Return draft GitHub Release identifiers matching the given tags or name."""

    matching_ids: list[int] = []
    tag_name_set = set(tag_names)
    for release in releases:
        parsed = _release_read_view(release)
        if parsed is None or parsed.draft is not True:
            continue
        release_id = parsed.id
        if release_id is None:
            continue
        if parsed.tag_name in tag_name_set or parsed.name == release_name:
            matching_ids.append(release_id)
    return matching_ids


def release_by_tag(
    releases: Sequence[Mapping[str, object]],
    *,
    tag_name: str,
) -> dict[str, object]:
    """Return the unique GitHub Release matching one exact tag name."""

    matches: list[Mapping[str, object]] = []
    for release in releases:
        parsed = _release_read_view(release)
        if parsed is not None and parsed.tag_name == tag_name:
            matches.append(release)
    if not matches:
        raise ValueError(f"no GitHub Release exists for tag {tag_name}")
    if len(matches) != 1:
        raise ValueError(f"expected exactly one GitHub Release for tag {tag_name}, found {len(matches)}")
    return dict(matches[0])


def release_asset_ids_by_names(
    release_payload: Mapping[str, object],
    *,
    asset_names: Sequence[str],
) -> dict[str, int]:
    """Return matching GitHub Release asset identifiers keyed by asset basename."""

    parsed_release = _release_read_view(release_payload)
    if parsed_release is None or parsed_release.assets is None:
        return {}
    requested_names = set(asset_names)
    matching_assets: dict[str, int] = {}
    for asset_payload in parsed_release.assets:
        asset_id = asset_payload.id
        asset_name = asset_payload.name
        if asset_id is not None and asset_name in requested_names:
            matching_assets[asset_name] = asset_id
    return matching_assets


def delete_release(repository_slug: str, release_id: int) -> None:
    """Delete a GitHub Release by release identifier."""

    run_logged_command(
        [
            "gh",
            "api",
            "-X",
            "DELETE",
            "-H",
            "Accept: application/vnd.github+json",
            f"repos/{repository_slug}/releases/{release_id}",
        ],
        capture_output=False,
    )


def delete_release_asset(repository_slug: str, asset_id: int) -> None:
    """Delete one GitHub Release asset by asset identifier."""

    run_logged_command(
        [
            "gh",
            "api",
            "-X",
            "DELETE",
            "-H",
            "Accept: application/vnd.github+json",
            f"repos/{repository_slug}/releases/assets/{asset_id}",
        ],
        capture_output=False,
    )


def download_release_asset_text(repository_slug: str, asset_id: int) -> str:
    """Download one GitHub Release asset as UTF-8 text."""

    completed = run_logged_command(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/octet-stream",
            f"repos/{repository_slug}/releases/assets/{asset_id}",
        ]
    )
    return completed.stdout


def create_draft_release(
    repository_slug: str,
    *,
    tag_name: str,
    target_commitish: str,
    release_name: str,
    release_body: str,
) -> dict[str, object]:
    """Create a draft GitHub Release and return the API response payload."""

    completed = run_logged_command(
        [
            "gh",
            "api",
            "-X",
            "POST",
            "-H",
            "Accept: application/vnd.github+json",
            f"repos/{repository_slug}/releases",
            "--input",
            "-",
        ],
        input_text=json.dumps(
            {
                "tag_name": tag_name,
                "target_commitish": target_commitish,
                "name": release_name,
                "body": release_body,
                "draft": True,
                "prerelease": False,
                "generate_release_notes": False,
            }
        ),
    )
    return _validated_release_payload(
        json.loads(completed.stdout),
        source="GitHub release creation",
    )


def update_release(
    repository_slug: str,
    release_id: int,
    *,
    payload: dict[str, object],
) -> dict[str, object]:
    """Patch an existing GitHub Release and return the API response payload."""

    completed = run_logged_command(
        [
            "gh",
            "api",
            "-X",
            "PATCH",
            "-H",
            "Accept: application/vnd.github+json",
            f"repos/{repository_slug}/releases/{release_id}",
            "--input",
            "-",
        ],
        input_text=json.dumps(payload),
    )
    return _validated_release_payload(
        json.loads(completed.stdout),
        source="GitHub release update",
    )


def upload_release_assets(
    repository_slug: str,
    *,
    tag_name: str,
    asset_paths: Sequence[Path],
    clobber: bool,
) -> None:
    """Upload one or more assets to a GitHub Release by tag."""

    if not asset_paths:
        raise ValueError("at least one GitHub Release asset path is required")
    command = ["gh", "release", "upload", tag_name]
    command.extend(str(path) for path in asset_paths)
    if clobber:
        command.append("--clobber")
    command.extend(["-R", repository_slug])
    run_logged_command(command, capture_output=False)
