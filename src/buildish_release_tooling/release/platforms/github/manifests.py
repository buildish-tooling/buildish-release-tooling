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

"""Typed GitHub publication extensions and stable command results."""

import re
from typing import Literal

from pydantic import Field, field_validator

from buildish_release_tooling.docs.documentation import (
    SchemaExportSpecification,
    ToolingDerivedModel,
)
from buildish_release_tooling.release.core.manifests import ManifestDigestReference
from buildish_release_tooling.release.core.models import (
    ArtifactReference,
    CandidateIdentity,
)


class GitHubAssetIdentity(ToolingDerivedModel):
    """Immutable observed identity of one GitHub Release asset."""

    name: str = Field(description="GitHub Release asset filename.")
    asset_id: int = Field(ge=1, description="GitHub-issued numeric asset identifier.")
    size_bytes: int = Field(
        ge=0, description="GitHub-observed release asset size in bytes."
    )
    digest: str = Field(description="GitHub-observed SHA-256 asset digest.")

    @field_validator("digest")
    @classmethod
    def _validate_digest(cls, value: str) -> str:
        normalized = value.lower()
        if re.fullmatch(r"sha256:[0-9a-f]{64}", normalized) is None:
            raise ValueError(
                "GitHub asset digest must use sha256:<64 lowercase hex digits>"
            )
        return normalized


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


class StageGitHubFinalReleaseResult(ToolingDerivedModel):
    """Result of converging on one exact draft GitHub final release."""

    component: str = Field(description="Released Buildish component identifier.")
    version: str = Field(description="Exact released component version.")
    source_commit: str = Field(
        description="Exact source commit targeted by the final tag."
    )
    publication: GitHubFinalPublication = Field(
        description="Observed exact GitHub final-release publication state."
    )

    action: Literal["stage-github-final-release"] = Field(
        default="stage-github-final-release",
        description="Command action discriminator.",
    )
    outcome: Literal["created", "completed", "already-complete"] = Field(
        description="Idempotent staging outcome."
    )


class ReadGitHubFinalReleaseResult(ToolingDerivedModel):
    """Exact observed state of one GitHub final release."""

    component: str = Field(description="Released Buildish component identifier.")
    version: str = Field(description="Exact released component version.")
    source_commit: str = Field(
        description="Exact source commit targeted by the final tag."
    )
    publication: GitHubFinalPublication = Field(
        description="Observed exact GitHub final-release publication state."
    )

    action: Literal["read-github-final-release"] = Field(
        default="read-github-final-release", description="Command action discriminator."
    )
    outcome: Literal["observed"] = Field(
        default="observed", description="Read-only observation outcome."
    )


class VerifyGitHubFinalReleaseResult(ToolingDerivedModel):
    """Result of verifying one GitHub final release against direct-release state."""

    component: str = Field(description="Released Buildish component identifier.")
    version: str = Field(description="Exact released component version.")
    source_commit: str = Field(
        description="Exact source commit targeted by the final tag."
    )
    publication: GitHubFinalPublication = Field(
        description="Observed exact GitHub final-release publication state."
    )

    action: Literal["verify-github-final-release"] = Field(
        default="verify-github-final-release",
        description="Command action discriminator.",
    )
    outcome: Literal["verified"] = Field(
        default="verified", description="Exact-state verification outcome."
    )


class PublishGitHubFinalReleaseResult(ToolingDerivedModel):
    """Result of publishing or revalidating one exact GitHub final release."""

    component: str = Field(description="Released Buildish component identifier.")
    version: str = Field(description="Exact released component version.")
    source_commit: str = Field(
        description="Exact source commit targeted by the final tag."
    )
    publication: GitHubFinalPublication = Field(
        description="Observed exact GitHub final-release publication state."
    )

    action: Literal["publish-github-final-release"] = Field(
        default="publish-github-final-release",
        description="Command action discriminator.",
    )
    outcome: Literal["published", "already-complete"] = Field(
        description="Idempotent final publication outcome."
    )


class AttachGitHubReleaseManifestResult(ToolingDerivedModel):
    """Result of attaching one exact durable final release manifest."""

    component: str = Field(description="Released Buildish component identifier.")
    version: str = Field(description="Exact released component version.")
    release_manifest: ManifestDigestReference = Field(
        description="Exact attached final release-manifest identity."
    )
    publication: GitHubFinalPublication = Field(
        description="Observed GitHub final publication containing the manifest asset."
    )
    action: Literal["attach-github-release-manifest"] = Field(
        default="attach-github-release-manifest",
        description="Command action discriminator.",
    )
    outcome: Literal["attached", "already-complete"] = Field(
        description="Idempotent manifest attachment outcome."
    )


class CreateGitHubCandidateTagResult(ToolingDerivedModel):
    """Result of creating or revalidating one immutable candidate tag."""

    component: str = Field(description="Released Buildish component identifier.")
    version: str = Field(description="Exact candidate version.")
    candidate: CandidateIdentity = Field(description="Exact candidate identity.")
    source_commit: str = Field(
        description="Exact commit targeted by the candidate tag."
    )
    action: Literal["create-candidate-tag"] = Field(
        default="create-candidate-tag", description="Command action discriminator."
    )
    outcome: Literal["created", "already-complete"] = Field(
        description="Idempotent tag creation outcome."
    )


class StageGitHubCandidateResult(ToolingDerivedModel):
    """Result of converging on one exact draft GitHub candidate release."""

    component: str = Field(description="Released Buildish component identifier.")
    version: str = Field(description="Exact candidate version.")
    candidate: CandidateIdentity = Field(description="Exact candidate identity.")
    source_commit: str = Field(
        description="Exact source commit targeted by the candidate tag."
    )
    artifacts: list[ArtifactReference] = Field(
        default_factory=list,
        description="Immutable staged candidate artifact inventory.",
    )
    publication: GitHubCandidatePublication = Field(
        description="Observed exact GitHub candidate publication state."
    )
    action: Literal["stage-github-candidate"] = Field(
        default="stage-github-candidate", description="Command action discriminator."
    )
    outcome: Literal["created", "completed", "already-complete"] = Field(
        description="Idempotent candidate staging outcome."
    )


class AttachGitHubCandidateManifestResult(ToolingDerivedModel):
    """Result of attaching one exact durable candidate manifest."""

    component: str = Field(description="Released Buildish component identifier.")
    version: str = Field(description="Exact candidate version.")
    candidate: CandidateIdentity = Field(description="Exact candidate identity.")
    candidate_manifest: ManifestDigestReference = Field(
        description="Exact attached candidate-manifest identity."
    )
    publication: GitHubCandidatePublication = Field(
        description="Observed GitHub candidate publication including the manifest asset."
    )
    action: Literal["attach-github-candidate-manifest"] = Field(
        default="attach-github-candidate-manifest",
        description="Command action discriminator.",
    )
    outcome: Literal["attached", "already-complete"] = Field(
        description="Idempotent manifest attachment outcome."
    )


class VerifyGitHubCandidateResult(ToolingDerivedModel):
    """Result of verifying one exact candidate and durable manifest."""

    component: str = Field(description="Released Buildish component identifier.")
    version: str = Field(description="Exact candidate version.")
    candidate: CandidateIdentity = Field(description="Exact candidate identity.")
    candidate_manifest: ManifestDigestReference = Field(
        description="Verified candidate-manifest identity."
    )
    publication: GitHubCandidatePublication = Field(
        description="Verified GitHub candidate publication state."
    )
    action: Literal["verify-github-candidate"] = Field(
        default="verify-github-candidate", description="Command action discriminator."
    )
    outcome: Literal["verified"] = Field(
        default="verified", description="Exact-state verification outcome."
    )


class FinalizeGitHubCandidateResult(ToolingDerivedModel):
    """Result of applying configured visibility to one verified candidate."""

    component: str = Field(description="Released Buildish component identifier.")
    version: str = Field(description="Exact candidate version.")
    candidate: CandidateIdentity = Field(description="Exact candidate identity.")
    candidate_manifest: ManifestDigestReference = Field(
        description="Verified candidate-manifest identity."
    )
    publication: GitHubCandidatePublication = Field(
        description="Observed finalized GitHub candidate publication state."
    )
    action: Literal["finalize-github-candidate"] = Field(
        default="finalize-github-candidate", description="Command action discriminator."
    )
    outcome: Literal["published", "retained-draft", "already-complete"] = Field(
        description="Idempotent candidate finalization outcome."
    )


def _result_export(filename: str, summary: str) -> SchemaExportSpecification:
    return SchemaExportSpecification(
        filename=filename,
        summary=summary,
        reference_group="supported-emitted-root",
    )


StageGitHubFinalReleaseResult.schema_export = _result_export(
    "stage-github-final-release-result.schema.json",
    "Stable result of staging a direct GitHub final release.",
)
ReadGitHubFinalReleaseResult.schema_export = _result_export(
    "read-github-final-release-result.schema.json",
    "Stable exact observation of a direct GitHub final release.",
)
VerifyGitHubFinalReleaseResult.schema_export = _result_export(
    "verify-github-final-release-result.schema.json",
    "Stable verification result for a direct GitHub final release.",
)
PublishGitHubFinalReleaseResult.schema_export = _result_export(
    "publish-github-final-release-result.schema.json",
    "Stable publication result for a direct GitHub final release.",
)
AttachGitHubReleaseManifestResult.schema_export = _result_export(
    "attach-github-release-manifest-result.schema.json",
    "Stable result of attaching one exact final release manifest.",
)
CreateGitHubCandidateTagResult.schema_export = _result_export(
    "create-github-candidate-tag-result.schema.json",
    "Stable result of creating one exact candidate tag.",
)
StageGitHubCandidateResult.schema_export = _result_export(
    "stage-github-candidate-result.schema.json",
    "Stable result of staging one exact GitHub release candidate.",
)
AttachGitHubCandidateManifestResult.schema_export = _result_export(
    "attach-github-candidate-manifest-result.schema.json",
    "Stable result of attaching one exact candidate manifest.",
)
VerifyGitHubCandidateResult.schema_export = _result_export(
    "verify-github-candidate-result.schema.json",
    "Stable verification result for one exact GitHub release candidate.",
)
FinalizeGitHubCandidateResult.schema_export = _result_export(
    "finalize-github-candidate-result.schema.json",
    "Stable finalization result for one exact GitHub release candidate.",
)
