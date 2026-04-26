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

from apache_buildish_release_tooling.release.process import run_logged_command


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
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise ValueError("GitHub tag-object creation did not return an object payload")
    return payload


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
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise ValueError("GitHub ref creation did not return an object payload")
    return payload


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
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise ValueError("GitHub ref update did not return an object payload")
    return payload
