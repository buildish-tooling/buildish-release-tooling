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

"""Provider-neutral direct, candidate, and promotion runtime state."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import Field, field_validator, model_validator

from buildish_release_tooling.docs.documentation import (
    RuntimeDerivedModel,
    SchemaExportSpecification,
)
from buildish_release_tooling.release.core.models import (
    ArtifactReference,
    CandidateIdentity,
    PublicationReference,
    ReleaseIdentity,
    SourceRevision,
    TagIdentity,
    ToolingInvocationProvenance,
    VerificationResultReference,
)


class SourceArtifactPlan(RuntimeDerivedModel):
    """Resolved built-source archive names for one release run."""

    filename: str = Field(description="Resolved source archive filename.")
    archive_root: str = Field(description="Resolved top-level archive directory.")

    @property
    def prefix_path(self) -> str:
        """Return the archive root as a `git archive` prefix path."""

        return f"{self.archive_root}/"


class DirectReleaseState(RuntimeDerivedModel):
    """Exact source and final-tag state for a direct release."""

    release: ReleaseIdentity = Field(description="Exact component release identity.")
    source: SourceRevision = Field(description="Exact selected source revision.")
    final_tag: TagIdentity = Field(description="Exact immutable final tag.")
    source_date_epoch: int | None = Field(
        default=None, ge=0, description="Optional canonical source timestamp."
    )
    source_artifact: SourceArtifactPlan | None = Field(
        default=None, description="Optional resolved built-source archive plan."
    )
    artifacts: list[ArtifactReference] = Field(
        default_factory=list, description="Immutable release artifact references."
    )
    verification_results: list[VerificationResultReference] = Field(
        default_factory=list, description="Verification results for the release inputs."
    )
    publications: list[PublicationReference] = Field(
        default_factory=list, description="Publication results for this release."
    )
    tooling: ToolingInvocationProvenance | None = Field(
        default=None, description="Tooling revision and invocation provenance."
    )

    @model_validator(mode="after")
    def _validate_final_tag(self) -> DirectReleaseState:
        if self.final_tag.purpose != "final":
            raise ValueError("direct release final_tag purpose must be final")
        if self.final_tag.target_commit != self.source.commit_sha:
            raise ValueError("direct release final_tag must target the selected source commit")
        return self


class CandidateReleaseState(RuntimeDerivedModel):
    """Exact source, candidate, artifact naming, and publication state."""

    release: ReleaseIdentity = Field(description="Exact component release identity.")
    source: SourceRevision = Field(description="Exact selected source revision.")
    source_date_epoch: int = Field(ge=0, description="Canonical selected-source timestamp.")
    candidate: CandidateIdentity = Field(description="Exact candidate identity.")
    final_tag_identity: TagIdentity = Field(description="Intended immutable final tag.")
    source_artifact: SourceArtifactPlan | None = Field(
        default=None, description="Optional resolved built-source archive plan."
    )
    artifacts: list[ArtifactReference] = Field(
        default_factory=list, description="Immutable candidate artifact references."
    )
    verification_results: list[VerificationResultReference] = Field(
        default_factory=list, description="Verification results for candidate inputs."
    )
    publications: list[PublicationReference] = Field(
        default_factory=list, description="Candidate publication results."
    )
    tooling: ToolingInvocationProvenance | None = Field(
        default=None, description="Tooling revision and invocation provenance."
    )

    @model_validator(mode="after")
    def _validate_identity_relations(self) -> CandidateReleaseState:
        if self.candidate.release != self.release:
            raise ValueError("candidate identity must refer to the same release")
        if self.candidate.tag.target_commit != self.source.commit_sha:
            raise ValueError("candidate tag must target the selected source commit")
        if self.final_tag_identity.purpose != "final":
            raise ValueError("candidate final_tag purpose must be final")
        return self

    @property
    def resolved_release_branch(self) -> str:
        return self.source.source_ref or "explicit-source-sha"

    @property
    def resolved_source_ref(self) -> str:
        return self.source.commit_sha

    @property
    def candidate_label(self) -> str:
        return self.candidate.label

    @property
    def rc_number(self) -> int:
        return self.candidate.number

    @property
    def rc_tag(self) -> str:
        return self.candidate.tag.name

    @property
    def final_tag(self) -> str:
        return self.final_tag_identity.name

    @property
    def source_artifact_name(self) -> str:
        if self.source_artifact is None:
            raise ValueError("candidate has no built source artifact")
        return self.source_artifact.filename

    @property
    def source_artifact_root_name(self) -> str:
        if self.source_artifact is None:
            raise ValueError("candidate has no built source artifact")
        return self.source_artifact.archive_root

    @property
    def source_artifact_prefix_path(self) -> str:
        if self.source_artifact is None:
            raise ValueError("candidate has no built source artifact")
        return self.source_artifact.prefix_path

    @property
    def candidate_publication_uri(self) -> str:
        if len(self.publications) != 1:
            raise ValueError("legacy candidate flow requires exactly one publication reference")
        return self.publications[0].uri


class PromotionState(RuntimeDerivedModel):
    """Exact candidate evidence and final-tag state for promotion."""

    release: ReleaseIdentity = Field(description="Exact component release identity.")
    source: SourceRevision = Field(description="Exact source revision proven by the candidate.")
    candidate: CandidateIdentity = Field(description="Exact candidate selected for promotion.")
    candidate_manifest_digest: str = Field(
        description="Lowercase SHA-256 or SHA-512 digest of the exact candidate manifest."
    )
    final_tag: TagIdentity = Field(description="Exact immutable final tag.")
    artifacts: list[ArtifactReference] = Field(
        default_factory=list, description="Artifacts selected for final promotion."
    )
    verification_results: list[VerificationResultReference] = Field(
        default_factory=list, description="Verification results required for promotion."
    )
    publications: list[PublicationReference] = Field(
        default_factory=list, description="Final publication results."
    )
    tooling: ToolingInvocationProvenance | None = Field(
        default=None, description="Tooling revision and invocation provenance."
    )

    @field_validator("candidate_manifest_digest")
    @classmethod
    def _validate_manifest_digest(cls, value: str) -> str:
        if re.fullmatch(r"(?:[0-9a-f]{64}|[0-9a-f]{128})", value) is None:
            raise ValueError("candidate_manifest_digest must be a SHA-256 or SHA-512 hex digest")
        return value

    @model_validator(mode="after")
    def _validate_identity_relations(self) -> PromotionState:
        if self.candidate.release != self.release:
            raise ValueError("promoted candidate must refer to the same release")
        if self.candidate.tag.target_commit != self.source.commit_sha:
            raise ValueError("promoted candidate must bind the selected source commit")
        if self.final_tag.purpose != "final":
            raise ValueError("promotion final_tag purpose must be final")
        return self


@dataclass(frozen=True)
class FinalReleasePlan:
    """Transitional plan used by the pre-refactor composite finalization commands."""

    selected_candidate_tag: str
    final_tag_name: str
    archive_versions: list[str]
    primary_publication_uri: str
    moving_aliases: list[str]

    @property
    def selected_rc_tag(self) -> str:
        return self.selected_candidate_tag

    @property
    def final_tag(self) -> str:
        return self.final_tag_name

    @property
    def release_url(self) -> str:
        return self.primary_publication_uri

    @property
    def moving_tags(self) -> list[str]:
        return self.moving_aliases


DirectReleaseState.schema_export = SchemaExportSpecification(
    filename="direct-release-state.schema.json",
    audience="internal",
    stability="stable",
    summary="Resolved provider-neutral state for one direct release.",
)
CandidateReleaseState.schema_export = SchemaExportSpecification(
    filename="candidate-release-state.schema.json",
    audience="internal",
    stability="stable",
    summary="Resolved provider-neutral state for one exact release candidate.",
)
PromotionState.schema_export = SchemaExportSpecification(
    filename="promotion-state.schema.json",
    audience="internal",
    stability="stable",
    summary="Resolved provider-neutral state for exact candidate promotion.",
)
