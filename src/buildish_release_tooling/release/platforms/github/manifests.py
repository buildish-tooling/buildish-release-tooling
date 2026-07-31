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

"""Typed GitHub publication extensions for stable release manifests."""

from typing import Literal

from pydantic import Field

from buildish_release_tooling.docs.documentation import ToolingDerivedModel


class GitHubAssetIdentity(ToolingDerivedModel):
    """Immutable observed identity of one GitHub Release asset."""

    name: str = Field(description="GitHub Release asset filename.")
    asset_id: int = Field(ge=1, description="GitHub-issued numeric asset identifier.")
    digest: str | None = Field(
        default=None, description="GitHub-observed or Buildish-verified asset digest."
    )


class GitHubCandidatePublication(ToolingDerivedModel):
    """GitHub Release publication evidence for one exact candidate."""

    kind: Literal["github-candidate-publication"] = Field(
        default="github-candidate-publication", description="Extension discriminator."
    )
    repository: str = Field(description="GitHub repository in owner/name form.")
    release_id: int = Field(ge=1, description="GitHub Release numeric identifier.")
    release_url: str = Field(description="User-facing GitHub Release URL.")
    tag: str = Field(description="Exact candidate tag attached to the release.")
    draft: bool = Field(description="Whether GitHub reports the release as a draft.")
    prerelease: bool = Field(description="Whether GitHub reports a pre-release.")
    assets: list[GitHubAssetIdentity] = Field(
        default_factory=list, description="Observed candidate asset identities."
    )


class GitHubFinalPublication(ToolingDerivedModel):
    """GitHub Release publication evidence for one final release."""

    kind: Literal["github-final-publication"] = Field(
        default="github-final-publication", description="Extension discriminator."
    )
    repository: str = Field(description="GitHub repository in owner/name form.")
    release_id: int = Field(ge=1, description="GitHub Release numeric identifier.")
    release_url: str = Field(description="User-facing GitHub Release URL.")
    tag: str = Field(description="Exact immutable final tag attached to the release.")
    draft: bool = Field(description="Whether GitHub reports the release as a draft.")
    prerelease: bool = Field(description="Whether GitHub reports a pre-release.")
    assets: list[GitHubAssetIdentity] = Field(
        default_factory=list, description="Observed final asset identities."
    )
