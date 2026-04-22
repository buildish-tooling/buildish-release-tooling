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

"""Semantic-version and release-line helpers."""

from __future__ import annotations


def _parse_version_parts(version: str) -> tuple[int, int, int]:
    pieces = version.split(".")
    if len(pieces) != 3 or not all(piece.isdigit() for piece in pieces):
        raise ValueError(f"invalid version: {version}")
    return int(pieces[0]), int(pieces[1]), int(pieces[2])


def _compare_versions(left: str, right: str) -> int:
    left_parts = _parse_version_parts(left)
    right_parts = _parse_version_parts(right)
    if left_parts < right_parts:
        return -1
    if left_parts > right_parts:
        return 1
    return 0


def compare_versions(left: str, right: str) -> int:
    """Compare two semantic versions and return `-1`, `0`, or `1`."""

    return _compare_versions(left, right)


def _branch_candidates(version: str) -> list[str]:
    major, minor, _patch = _parse_version_parts(version)
    return [f"release/{major}.{minor}.x", f"release/{major}.x"]


def resolve_release_branch(version: str, branches: list[str]) -> str:
    """Resolve the best release branch for a version from most specific to least specific."""

    for candidate in _branch_candidates(version):
        if candidate in branches:
            return candidate
    raise ValueError(f"unable to resolve release branch for version: {version}")


def derive_specific_release_line(version: str) -> str:
    """Derive the most specific release line for a semantic version."""

    major, minor, _patch = _parse_version_parts(version)
    return f"{major}.{minor}.x"


def derive_rc_tag(version: str, rc_number: int) -> str:
    """Derive the exact RC tag name for a version and RC number."""

    return f"v{version}-rc{rc_number}"


def derive_final_tag(version: str) -> str:
    """Derive the exact final version tag name for a version."""

    return f"v{version}"


def version_from_final_tag(tag_name: str) -> str | None:
    """Return the semantic version encoded in one immutable final tag name."""

    if not tag_name.startswith("v"):
        return None
    version = tag_name.removeprefix("v")
    try:
        _parse_version_parts(version)
    except ValueError:
        return None
    return version


def highest_existing_rc_number_or_zero(version: str, tags: list[str]) -> int:
    """Find the highest matching RC number for a version from a supplied tag set."""

    prefix = f"v{version}-rc"
    matches = [
        int(tag[len(prefix) :])
        for tag in tags
        if tag.startswith(prefix) and tag[len(prefix) :].isdigit()
    ]
    return max(matches) if matches else 0


def next_rc_number_from_tags(version: str, tags: list[str]) -> int:
    """Derive the next RC number for a version from a supplied tag set."""

    prefix = f"v{version}-rc"
    matches = [
        int(tag[len(prefix) :])
        for tag in tags
        if tag.startswith(prefix) and tag[len(prefix) :].isdigit()
    ]
    return max(matches) + 1 if matches else 0


def latest_rc_tag_from_tags(version: str, tags: list[str]) -> str:
    """Resolve the latest matching RC tag name from a supplied tag set."""

    highest_rc = highest_existing_rc_number_or_zero(version, tags)
    candidate = derive_rc_tag(version, highest_rc)
    if candidate not in tags:
        raise ValueError(f"unable to resolve latest RC tag for version: {version}")
    return candidate


def _infer_moving_tag_family_from_targets(secondary_targets: list[str]) -> str:
    if "github-action" in secondary_targets:
        return "github-action"
    if "dockerhub" in secondary_targets:
        return "container-image"
    return "none"


def derive_moving_tags(
    version: str,
    secondary_targets: list[str],
    moving_tags_enabled: bool,
    latest_tag_enabled: bool,
) -> list[str]:
    """Derive moving aliases for supported secondary-target families."""

    if not moving_tags_enabled:
        return []
    major, minor, _patch = _parse_version_parts(version)
    family = _infer_moving_tag_family_from_targets(secondary_targets)
    if family == "github-action":
        return [f"v{major}", f"v{major}.{minor}"]
    if family == "container-image":
        tags = [str(major), f"{major}.{minor}"]
        if latest_tag_enabled:
            tags.append("latest")
        return tags
    if family == "none":
        return []
    raise ValueError(f"unsupported moving tag family: {family}")


def _is_version_in_release_line(release_line: str, version: str) -> bool:
    major, minor, _patch = _parse_version_parts(version)
    if release_line.endswith(".x") and release_line.count(".") == 1:
        release_major = release_line[:-2]
        if not release_major.isdigit():
            raise ValueError(f"invalid release line: {release_line}")
        return major == int(release_major)
    if release_line.endswith(".x") and release_line.count(".") == 2:
        major_piece, minor_piece, x_piece = release_line.split(".")
        if x_piece != "x" or not major_piece.isdigit() or not minor_piece.isdigit():
            raise ValueError(f"invalid release line: {release_line}")
        return major == int(major_piece) and minor == int(minor_piece)
    raise ValueError(f"invalid release line: {release_line}")


def is_version_in_release_line(release_line: str, version: str) -> bool:
    """Return whether one semantic version belongs to one release line."""

    return _is_version_in_release_line(release_line, version)


def versions_to_archive_for_line(
    release_line: str, current_version: str, published_versions: list[str]
) -> list[str]:
    """List published same-line versions older than the new final version."""

    return [
        candidate
        for candidate in published_versions
        if _is_version_in_release_line(release_line, candidate)
        and _compare_versions(candidate, current_version) == -1
    ]


def published_versions_from_entries(entries: list[str]) -> list[str]:
    """Parse semantic-version directory names from SVN entry listings."""

    published_versions = [
        entry.rstrip("/")
        for entry in entries
        if entry.endswith("/")
        and len(entry.rstrip("/").split(".")) == 3
        and all(piece.isdigit() for piece in entry.rstrip("/").split("."))
    ]
    return sorted(published_versions, key=_parse_version_parts)
