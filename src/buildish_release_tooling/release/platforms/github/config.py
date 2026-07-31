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

"""GitHub-specific authored publication targets."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, field_validator

from buildish_release_tooling.docs.documentation import ComponentOwnedAuthoredModel

_REPOSITORY_PATTERN = re.compile(r"[^/\s]+/[^/\s]+")


class GitHubReleasePublicationConfig(ComponentOwnedAuthoredModel):
    """GitHub Release authoritative or convenience publication target."""

    kind: Literal["github-release"] = Field(
        default="github-release",
        description="Publication target discriminator.",
    )
    repository: str | None = Field(
        default=None,
        description="Optional explicit GitHub repository in owner/name form.",
    )

    @field_validator("repository")
    @classmethod
    def _validate_repository(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if _REPOSITORY_PATTERN.fullmatch(normalized) is None:
            raise ValueError("github repository must use owner/name form")
        return normalized


class GitHubActionPublicationConfig(ComponentOwnedAuthoredModel):
    """Secondary publication of immutable and moving GitHub Action refs."""

    kind: Literal["github-action"] = Field(
        default="github-action",
        description="Secondary publication target discriminator.",
    )


class GitHubReleaseAssetsPublicationConfig(ComponentOwnedAuthoredModel):
    """Secondary component-produced assets attached to a GitHub Release."""

    kind: Literal["github-release-assets"] = Field(
        default="github-release-assets",
        description="Secondary publication target discriminator.",
    )
