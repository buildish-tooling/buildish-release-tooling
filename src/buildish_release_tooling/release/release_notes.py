# Copyright 2026 The Buildish Authors
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

"""Version-specific release-note selection and validation."""

from __future__ import annotations

import hashlib
from string import Formatter
from typing import TYPE_CHECKING

from buildish_release_tooling.release.core.models import (
    MAX_RELEASE_NOTES_BYTES,
    ReleaseNotes,
    validate_release_notes_source_path,
)
from buildish_release_tooling.release.core.naming import require_semantic_version

if TYPE_CHECKING:
    from buildish_release_tooling.release.config import ReleaseConfig
    from buildish_release_tooling.release.git_repo import GitRepository


def render_release_notes_path(template: str, version: str) -> str:
    """Render one versioned release-note path with no dynamic fields besides version."""

    require_semantic_version(version)
    fields: list[str] = []
    try:
        parsed = list(Formatter().parse(template))
    except ValueError as exc:
        raise ValueError(f"invalid release notes path template: {template}") from exc
    for _literal, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if field_name != "version" or format_spec or conversion:
            raise ValueError(
                "release notes path template supports only the `{version}` placeholder"
            )
        fields.append(field_name)
    if fields != ["version"]:
        raise ValueError(
            "release notes path template must contain `{version}` exactly once"
        )
    rendered = template.format(version=version)
    return validate_release_notes_source_path(rendered)


def resolve_release_notes(
    repo: GitRepository,
    config: ReleaseConfig,
    *,
    version: str,
    commit_sha: str,
) -> ReleaseNotes | None:
    """Read configured notes from the exact selected source commit."""

    notes_config = config.release_notes
    if notes_config is None:
        return None
    source_path = render_release_notes_path(notes_config.path_template, version)
    payload = repo.read_regular_file_at_commit(
        commit_sha,
        source_path,
        max_bytes=MAX_RELEASE_NOTES_BYTES,
    )
    try:
        markdown = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"release notes must be valid UTF-8: {source_path}") from exc
    if not markdown.strip():
        raise ValueError(f"release notes must not be empty: {source_path}")
    if "\x00" in markdown:
        raise ValueError(f"release notes must not contain NUL characters: {source_path}")
    return ReleaseNotes(
        source_path=source_path,
        sha256=hashlib.sha256(payload).hexdigest(),
        markdown=markdown,
    )


def validate_release_notes_binding(
    config: ReleaseConfig,
    notes: ReleaseNotes | None,
    *,
    version: str,
) -> None:
    """Require configured notes and their rendered source path to remain unchanged."""

    notes_config = config.release_notes
    if notes_config is None:
        return
    if notes is None:
        raise ValueError("configured release notes are missing from release state")
    expected_path = render_release_notes_path(notes_config.path_template, version)
    if notes.source_path != expected_path:
        raise ValueError("release notes path does not match release configuration")
