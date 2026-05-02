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

"""GitHub Git-tag and ref helpers used by the release-tooling CLI."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, ValidationError

from apache_buildish_release_tooling.release.process import run_logged_command


class _ExternalGithubReadModel(BaseModel):
    """Tolerant GitHub Git API subset reader."""

    model_config = ConfigDict(extra="allow")


class _GitHubGitObjectRead(_ExternalGithubReadModel):
    sha: str | None = None
    ref: str | None = None


def _json_object_output(stdout: str, *, source: str) -> dict[str, object]:
    payload = json.loads(stdout)
    if not isinstance(payload, dict):
        raise ValueError(f"{source} did not return an object payload")
    try:
        parsed = _GitHubGitObjectRead.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"{source} returned an invalid payload") from exc
    return parsed.model_dump(mode="python", exclude_none=True)


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
