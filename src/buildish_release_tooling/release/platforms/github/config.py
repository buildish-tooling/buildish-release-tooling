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

from pydantic import Field, field_validator, model_validator

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


class GitHubSourceChecksConfig(ComponentOwnedAuthoredModel):
    """GitHub check runs or status contexts required for one source revision."""

    platform: Literal["github"] = Field(
        description="Source-check hosting-platform discriminator.",
    )
    required: list[str] = Field(
        min_length=1,
        description=(
            "Exact GitHub check-run or legacy status-context names required on the "
            "selected revision."
        ),
    )
    trusted_workflow_path: str | None = Field(
        default=None,
        description=(
            "Optional repository-relative GitHub Actions workflow path that must "
            "have produced every required check run."
        ),
    )
    trusted_event: str | None = Field(
        default=None,
        description=(
            "Optional GitHub Actions event name required for the trusted workflow run."
        ),
    )
    trusted_branch: str | None = Field(
        default=None,
        description=(
            "Optional head branch required for the trusted GitHub Actions workflow run."
        ),
    )

    @field_validator("required")
    @classmethod
    def _normalize_required_checks(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("required GitHub check names must not be empty")
        if len(set(normalized)) != len(normalized):
            raise ValueError("required GitHub check names must be unique")
        return normalized

    @field_validator("trusted_workflow_path")
    @classmethod
    def _validate_trusted_workflow_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if (
            not normalized.startswith(".github/workflows/")
            or not normalized.endswith((".yml", ".yaml"))
            or "@" in normalized
        ):
            raise ValueError(
                "trusted_workflow_path must name a .github/workflows YAML file"
            )
        return normalized

    @field_validator("trusted_event", "trusted_branch")
    @classmethod
    def _validate_trusted_event(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("trusted workflow event or branch must not be empty")
        return normalized

    @model_validator(mode="after")
    def _validate_trusted_producer(self) -> GitHubSourceChecksConfig:
        if (
            self.trusted_event is not None or self.trusted_branch is not None
        ) and self.trusted_workflow_path is None:
            raise ValueError(
                "trusted workflow event or branch requires trusted_workflow_path"
            )
        return self


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
