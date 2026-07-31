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

"""GitHub Git-tag and ref helpers used by the release-tooling CLI."""

from __future__ import annotations

import json

from pydantic import Field

from buildish_release_tooling.release.external_json import validate_json_object_model_text
from buildish_release_tooling.release.platforms.github.models import ExternalGitHubReadModel
from buildish_release_tooling.release.process import run_logged_command


class _GitHubGitObjectRead(ExternalGitHubReadModel):
    sha: str | None = Field(
        default=None,
        description="Git object SHA returned by the GitHub Git tags or refs API.",
    )
    ref: str | None = Field(
        default=None,
        description="Fully qualified Git ref name returned by the GitHub Git refs API.",
    )


class _GitHubGitObjectIdentityRead(ExternalGitHubReadModel):
    sha: str = Field(description="Git object SHA returned by the GitHub API.")
    type: str = Field(description="Git object type returned by the GitHub API.")


class _GitHubGitReferenceRead(ExternalGitHubReadModel):
    ref: str = Field(description="Fully qualified Git ref returned by the GitHub API.")
    object: _GitHubGitObjectIdentityRead = Field(
        description="Git object targeted by the ref."
    )


class _GitHubAnnotatedTagRead(ExternalGitHubReadModel):
    object: _GitHubGitObjectIdentityRead = Field(
        description="Git object targeted by the annotated tag."
    )


def _json_object_output(stdout: str, *, source: str) -> dict[str, object]:
    parsed = validate_json_object_model_text(
        _GitHubGitObjectRead,
        stdout,
        source=source,
        expected_payload="GitHub Git object",
    )
    return parsed.model_dump(mode="python", exclude_none=True)


def resolve_annotated_tag_target_commit(
    repository_slug: str,
    *,
    tag_name: str,
) -> str:
    """Resolve an existing GitHub annotated tag to its exact target commit."""

    ref_completed = run_logged_command(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github+json",
            f"repos/{repository_slug}/git/ref/tags/{tag_name}",
        ]
    )
    ref_payload = validate_json_object_model_text(
        _GitHubGitReferenceRead,
        ref_completed.stdout,
        source="GitHub tag-ref read",
        expected_payload="GitHub Git ref",
    )
    if ref_payload.ref != f"refs/tags/{tag_name}":
        raise ValueError("GitHub tag-ref response does not match the requested final tag")
    if ref_payload.object.type != "tag":
        raise ValueError(f"GitHub final tag is not an annotated tag: {tag_name}")
    tag_completed = run_logged_command(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github+json",
            f"repos/{repository_slug}/git/tags/{ref_payload.object.sha}",
        ]
    )
    tag_payload = validate_json_object_model_text(
        _GitHubAnnotatedTagRead,
        tag_completed.stdout,
        source="GitHub annotated-tag read",
        expected_payload="GitHub annotated tag",
    )
    if tag_payload.object.type != "commit":
        raise ValueError(f"GitHub final tag does not target a commit: {tag_name}")
    return tag_payload.object.sha


def create_annotated_tag_object(
    repository_slug: str,
    *,
    tag_name: str,
    target_commit: str,
    message: str,
) -> dict[str, object]:
    """Create an annotated Git tag object through the GitHub API."""

    completed = run_logged_command(
        [
            "gh",
            "api",
            "-X",
            "POST",
            "-H",
            "Accept: application/vnd.github+json",
            f"repos/{repository_slug}/git/tags",
            "--input",
            "-",
        ],
        input_text=json.dumps(
            {
                "tag": tag_name,
                "message": message,
                "object": target_commit,
                "type": "commit",
            }
        ),
    )
    return _json_object_output(completed.stdout, source="GitHub tag-object creation")


def create_ref(
    repository_slug: str,
    *,
    ref_name: str,
    target_sha: str,
) -> dict[str, object]:
    """Create a Git ref through the GitHub API."""

    completed = run_logged_command(
        [
            "gh",
            "api",
            "-X",
            "POST",
            "-H",
            "Accept: application/vnd.github+json",
            f"repos/{repository_slug}/git/refs",
            "--input",
            "-",
        ],
        input_text=json.dumps(
            {
                "ref": ref_name,
                "sha": target_sha,
            }
        ),
    )
    return _json_object_output(completed.stdout, source="GitHub ref creation")


def update_ref(
    repository_slug: str,
    *,
    ref_name: str,
    target_sha: str,
    force: bool,
) -> dict[str, object]:
    """Update an existing Git ref through the GitHub API."""

    completed = run_logged_command(
        [
            "gh",
            "api",
            "-X",
            "PATCH",
            "-H",
            "Accept: application/vnd.github+json",
            f"repos/{repository_slug}/git/{ref_name}",
            "--input",
            "-",
        ],
        input_text=json.dumps(
            {
                "sha": target_sha,
                "force": force,
            }
        ),
    )
    return _json_object_output(completed.stdout, source="GitHub ref update")
