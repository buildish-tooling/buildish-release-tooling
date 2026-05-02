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

"""Shared helpers for artifact-registration kind handlers."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass

from apache_buildish_release_tooling.release.contracts import ReproducibilitySelector


def _optional_trimmed_text(raw_value: object | None) -> str | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, str):
        raise ValueError("artifact metadata values must be strings")
    normalized = raw_value.strip()
    if not normalized:
        return None
    return normalized


@dataclass(frozen=True)
class CommonArtifactMetadata:
    """Common optional metadata fields shared across artifact kinds."""

    role: str | None = None
    artifact_origin: str | None = None
    git_commit_sha: str | None = None
    reproducibility: ReproducibilitySelector | None = None


def common_artifact_metadata(args: Namespace) -> CommonArtifactMetadata:
    """Resolve common optional metadata fields shared across artifact kinds."""

    role = _optional_trimmed_text(getattr(args, "role", None))
    git_commit_sha = _optional_trimmed_text(getattr(args, "git_commit_sha", None))
    artifact_origin = _optional_trimmed_text(getattr(args, "artifact_origin", None))
    reproducibility_profile_id = _optional_trimmed_text(
        getattr(args, "reproducibility_profile_id", None)
    )
    if artifact_origin is None and git_commit_sha is not None:
        artifact_origin = "source-commit"
    reproducibility = (
        ReproducibilitySelector(profile_id=reproducibility_profile_id)
        if reproducibility_profile_id is not None
        else None
    )
    return CommonArtifactMetadata(
        role=role,
        artifact_origin=artifact_origin,
        git_commit_sha=git_commit_sha,
        reproducibility=reproducibility,
    )
