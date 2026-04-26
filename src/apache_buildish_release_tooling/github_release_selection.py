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

"""Helpers for selecting, reusing, and updating Buildish GitHub Releases."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from apache_buildish_release_tooling.git_repo import GitRepository
from apache_buildish_release_tooling.github_checks import resolve_repository_slug
from apache_buildish_release_tooling.github_releases import (
    create_draft_release,
    list_releases,
    update_release,
)
from apache_buildish_release_tooling.models import PrepareRcState
from apache_buildish_release_tooling.release_state import derive_final_tag, require_semantic_version


@dataclass(frozen=True)
class SelectedGitHubRelease:
    """Resolved GitHub Release metadata for one exact version."""

    repository_slug: str
    release_payload: dict[str, object]
    selected_rc_tag: str

    def require_release_id(self, *, reference_tag: str) -> int:
        """Return the numeric release id or raise a direct error."""

        release_id = self.release_payload.get("id")
        if not isinstance(release_id, int):
            raise ValueError(f"GitHub Release for {reference_tag} does not include a numeric id")
        return release_id

    def require_release_tag(self, *, reference_tag: str) -> str:
        """Return the release tag name or raise a direct error."""

        release_tag = self.release_payload.get("tag_name")
        if not isinstance(release_tag, str) or not release_tag:
            raise ValueError(f"GitHub Release for {reference_tag} does not include a tag name")
        return release_tag

    @property
    def release_url(self) -> str:
        """Return the best available browser/API URL for this release."""

        return asset_release_url(self.release_payload)


@dataclass(frozen=True)
class DraftReleaseSyncPlan:
    """Draft-release cleanup and reuse decisions for one sync run."""

    deleted_release_ids: list[int]
    same_rc_release: dict[str, object] | None


def asset_release_url(release_payload: dict[str, object]) -> str:
    """Return the best browser or API URL available for one release payload."""

    html_url = release_payload.get("html_url")
    if isinstance(html_url, str) and html_url:
        return html_url
    api_url = release_payload.get("url")
    if isinstance(api_url, str):
        return api_url
    return ""


def matching_draft_releases(
    releases: Iterable[dict[str, object]],
    *,
    version: str,
    tag_names: Iterable[str],
    release_name: str,
) -> list[dict[str, object]]:
    """Return draft GitHub Release payloads matching one exact release family."""

    tag_name_set = set(tag_names)
    matching_releases: list[dict[str, object]] = []
    for release in releases:
        if release.get("draft") is not True:
            continue
        release_tag = release.get("tag_name")
        release_title = release.get("name")
        matches_exact_version_rc = (
            isinstance(release_tag, str)
            and re.fullmatch(rf"v{re.escape(version)}-rc[0-9]+", release_tag) is not None
        )
        if (
            isinstance(release_tag, str)
            and release_tag in tag_name_set
            or matches_exact_version_rc
            or isinstance(release_title, str)
            and release_title == release_name
        ):
            matching_releases.append(release)
    return matching_releases


def selected_github_release(
    *,
    repo: GitRepository,
    version: str,
    expected_selected_rc_tag: str | None = None,
) -> SelectedGitHubRelease:
    """Resolve the GitHub Release selected for one exact version."""

    version = require_semantic_version(version)
    repository_slug = resolve_repository_slug(repo.path)
    release_payload, selected_rc_tag = _selected_release_for_version(
        list_releases(repository_slug),
        version=version,
    )
    if expected_selected_rc_tag is not None and selected_rc_tag != expected_selected_rc_tag:
        raise ValueError(
            f"draft GitHub Release for v{version} now points at {selected_rc_tag}, expected {expected_selected_rc_tag}"
        )
    if not repo.tag_exists(selected_rc_tag):
        raise ValueError(f"selected RC tag does not exist locally: {selected_rc_tag}")
    return SelectedGitHubRelease(
        repository_slug=repository_slug,
        release_payload=release_payload,
        selected_rc_tag=selected_rc_tag,
    )


def plan_draft_release_sync(
    matching_draft_releases: Iterable[dict[str, object]],
    *,
    version: str,
    state: PrepareRcState,
) -> DraftReleaseSyncPlan:
    """Classify matching draft releases into deletions and same-RC reuse candidates."""

    lower_rc_release_ids: list[int] = []
    legacy_release_ids: list[int] = []
    same_rc_release: dict[str, object] | None = None
    higher_rc_tags: list[str] = []
    for release in matching_draft_releases:
        release_id = release.get("id")
        if not isinstance(release_id, int):
            continue
        existing_rc_tag = _release_payload_rc_tag(release, version)
        if existing_rc_tag is None:
            legacy_release_ids.append(release_id)
            continue
        existing_rc_number = _rc_number_from_tag(version, existing_rc_tag)
        if existing_rc_number < state.rc_number:
            lower_rc_release_ids.append(release_id)
            continue
        if existing_rc_number > state.rc_number:
            higher_rc_tags.append(existing_rc_tag)
            continue
        if same_rc_release is not None:
            raise ValueError(f"multiple draft GitHub Releases already exist for {state.rc_tag}")
        existing_source_ref = _release_payload_source_ref(release)
        if existing_source_ref is not None and existing_source_ref != state.resolved_source_ref:
            raise ValueError(
                f"draft GitHub Release for {state.rc_tag} points at a different source ref: {existing_source_ref}"
            )
        same_rc_release = release
    if higher_rc_tags:
        raise ValueError(
            "draft GitHub Release already records a higher RC: " + ", ".join(sorted(higher_rc_tags))
        )
    return DraftReleaseSyncPlan(
        deleted_release_ids=sorted(legacy_release_ids + lower_rc_release_ids),
        same_rc_release=same_rc_release,
    )


def upsert_draft_release(
    repository_slug: str,
    *,
    state: PrepareRcState,
    release_name: str,
    desired_release_body: str,
    same_rc_release: dict[str, object] | None,
) -> tuple[dict[str, object], str]:
    """Create, reuse, or update the selected draft release for one RC."""

    if same_rc_release is None:
        return (
            create_draft_release(
                repository_slug,
                tag_name=state.rc_tag,
                target_commitish=state.resolved_source_ref,
                release_name=release_name,
                release_body=desired_release_body,
            ),
            "created",
        )
    existing_release_id = same_rc_release.get("id")
    if not isinstance(existing_release_id, int):
        raise ValueError(f"draft GitHub Release for {state.rc_tag} does not include a numeric id")
    same_release_body = same_rc_release.get("body")
    same_release_name = same_rc_release.get("name")
    if (
        isinstance(same_release_body, str)
        and same_release_body == desired_release_body
        and isinstance(same_release_name, str)
        and same_release_name == release_name
        and same_rc_release.get("tag_name") == state.rc_tag
    ):
        return same_rc_release, "reused"
    return (
        update_release(
            repository_slug,
            existing_release_id,
            payload={
                "tag_name": state.rc_tag,
                "target_commitish": state.resolved_source_ref,
                "name": release_name,
                "body": desired_release_body,
                "draft": True,
                "prerelease": False,
            },
        ),
        "updated",
    )


def _release_body_line_value(release_payload: dict[str, object], prefix: str) -> str | None:
    """Extract one exact line value from a release body by prefix."""

    body = release_payload.get("body")
    if not isinstance(body, str) or not body:
        return None
    pattern = re.compile(rf"(?m)^{re.escape(prefix)}(?P<value>.+)$")
    match = pattern.search(body)
    if match is None:
        return None
    value = match.group("value").strip()
    return value or None


def _release_payload_rc_tag(release_payload: dict[str, object], version: str) -> str | None:
    """Resolve one RC tag from a draft release payload."""

    release_tag = release_payload.get("tag_name")
    if isinstance(release_tag, str) and re.fullmatch(rf"v{re.escape(version)}-rc[0-9]+", release_tag):
        return release_tag
    body_rc_tag = _release_body_line_value(release_payload, "RC tag: ")
    if body_rc_tag is None:
        return None
    if not re.fullmatch(rf"v{re.escape(version)}-rc[0-9]+", body_rc_tag):
        raise ValueError(f"draft release body contains an invalid RC tag for {version}: {body_rc_tag}")
    return body_rc_tag


def _release_payload_source_ref(release_payload: dict[str, object]) -> str | None:
    """Resolve the recorded source ref from a draft release payload."""

    return _release_body_line_value(release_payload, "Resolved source ref: ")


def _selected_release_for_version(
    releases: Iterable[dict[str, object]],
    *,
    version: str,
) -> tuple[dict[str, object], str]:
    """Return the unique release payload and RC tag selected for one version."""

    final_tag = derive_final_tag(version)
    matching_releases: list[tuple[dict[str, object], str]] = []
    for release in releases:
        selected_rc_tag = _release_payload_rc_tag(release, version)
        release_tag = release.get("tag_name")
        if selected_rc_tag is None and release_tag != final_tag:
            continue
        if selected_rc_tag is None:
            raise ValueError(f"GitHub Release for {final_tag} does not record an RC tag")
        matching_releases.append((release, selected_rc_tag))
    if not matching_releases:
        raise ValueError(f"no GitHub Release exists for version {version}")
    selected_rc_tags = {selected_rc_tag for _release, selected_rc_tag in matching_releases}
    if len(selected_rc_tags) != 1:
        raise ValueError(
            f"GitHub Releases for v{version} record multiple RC tags: "
            + ", ".join(sorted(selected_rc_tags))
        )
    selected_rc_tag = next(iter(selected_rc_tags))
    matching_releases.sort(
        key=lambda item: _release_selection_priority(
            item[0],
            selected_rc_tag=selected_rc_tag,
            final_tag=final_tag,
        )
    )
    selected_release = matching_releases[0][0]
    selected_priority = _release_selection_priority(
        selected_release,
        selected_rc_tag=selected_rc_tag,
        final_tag=final_tag,
    )
    ambiguous_matches = [
        release
        for release, _release_rc_tag in matching_releases
        if _release_selection_priority(
            release,
            selected_rc_tag=selected_rc_tag,
            final_tag=final_tag,
        )
        == selected_priority
    ]
    if len(ambiguous_matches) != 1:
        raise ValueError(f"multiple GitHub Releases match version {version} at the same priority")
    return selected_release, selected_rc_tag


def _release_selection_priority(
    release_payload: dict[str, object],
    *,
    selected_rc_tag: str,
    final_tag: str,
) -> tuple[int, int]:
    """Rank exact-version releases by the preferred draft/final tagging scheme."""

    release_tag = release_payload.get("tag_name")
    release_id = release_payload.get("id")
    numeric_release_id = release_id if isinstance(release_id, int) else 0
    if release_tag == final_tag and release_payload.get("draft") is False:
        return (0, numeric_release_id)
    if release_tag == selected_rc_tag:
        return (1, numeric_release_id)
    if release_tag == final_tag:
        return (2, numeric_release_id)
    return (3, numeric_release_id)


def _rc_number_from_tag(version: str, rc_tag: str) -> int:
    """Parse the numeric RC counter from one exact-version RC tag."""

    match = re.fullmatch(rf"v{re.escape(version)}-rc([0-9]+)", rc_tag)
    if match is None:
        raise ValueError(f"invalid RC tag for version {version}: {rc_tag}")
    return int(match.group(1))
