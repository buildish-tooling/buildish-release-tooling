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

"""Stable provider-composed candidate, vote-package, and release manifests."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer, model_validator

from buildish_release_tooling.docs.documentation import (
    SchemaExportSpecification,
    ToolingDerivedModel,
)
from buildish_release_tooling.release.core.manifests import (
    AuthenticityReference,
    ManifestDigestReference,
    PromotedCandidateReference,
    PromotionEvidence,
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
from buildish_release_tooling.release.foundations.asf.manifests import (
    AsfCandidatePublication,
    AsfFinalPublication,
    AsfVoteExtension,
)
from buildish_release_tooling.release.platforms.github.manifests import (
    GitHubCandidatePublication,
    GitHubFinalPublication,
)

CandidateExtension = Annotated[
    GitHubCandidatePublication | AsfCandidatePublication,
    Field(discriminator="kind"),
]
ReleaseExtension = Annotated[
    GitHubFinalPublication | AsfFinalPublication,
    Field(discriminator="kind"),
]


class CandidateManifestV1(ToolingDerivedModel):
    """Stable manifest binding one exact candidate to source, artifacts, and publications."""

    schema_version: Literal["1"] = Field(default="1", description="Manifest schema version.")
    kind: Literal["candidate-manifest"] = Field(
        default="candidate-manifest", description="Manifest kind discriminator."
    )
    release: ReleaseIdentity = Field(description="Exact component release identity.")
    candidate: CandidateIdentity = Field(description="Exact candidate identity.")
    source: SourceRevision = Field(description="Exact selected source revision.")
    candidate_tag: TagIdentity = Field(description="Exact immutable candidate tag identity.")
    source_date_epoch: int | None = Field(
        default=None, ge=0, description="Optional canonical selected-source timestamp."
    )
    artifacts: list[ArtifactReference] = Field(
        default_factory=list, description="Immutable candidate artifact inventory."
    )
    verification_policy_selectors: list[str] = Field(
        default_factory=list, description="Selected verification policy identifiers."
    )
    verification_results: list[VerificationResultReference] = Field(
        default_factory=list, description="Candidate verification result references."
    )
    publications: list[PublicationReference] = Field(
        default_factory=list, description="Provider-neutral candidate publication references."
    )
    tooling: ToolingInvocationProvenance = Field(
        description="Tooling revision and invocation provenance."
    )
    created_at: str = Field(description="UTC creation timestamp in RFC 3339 form.")
    extensions: list[CandidateExtension] = Field(
        default_factory=list, description="Typed platform or foundation candidate extensions."
    )

    @model_validator(mode="after")
    def _validate_exact_candidate(self) -> CandidateManifestV1:
        if self.candidate.release != self.release:
            raise ValueError("candidate manifest identities refer to different releases")
        if self.candidate.tag != self.candidate_tag:
            raise ValueError("candidate_tag must equal the exact candidate identity tag")
        if self.candidate_tag.target_commit != self.source.commit_sha:
            raise ValueError("candidate tag must target the selected source revision")
        return self


class VotePackageV1(ToolingDerivedModel):
    """Optional voting materials bound cryptographically to one exact candidate manifest."""

    schema_version: Literal["1"] = Field(default="1", description="Manifest schema version.")
    kind: Literal["vote-package"] = Field(
        default="vote-package", description="Manifest kind discriminator."
    )
    subject: str = Field(description="Human-facing vote subject.")
    profile_selector: str = Field(description="Selected vote rendering profile.")
    candidate_manifest: ManifestDigestReference = Field(
        description="Cryptographic reference to the exact candidate manifest."
    )
    embedded_candidate_manifest: CandidateManifestV1 | None = Field(
        default=None, description="Optional embedded copy of the referenced candidate manifest."
    )
    verification_instructions: str = Field(
        description="Human-facing candidate verification instructions."
    )
    opening_template: str = Field(description="Rendered or renderable vote-opening text.")
    result_template: str = Field(description="Rendered or renderable vote-result text.")
    authenticity: list[AuthenticityReference] = Field(
        default_factory=list, description="Optional signatures or attestations."
    )
    extensions: list[AsfVoteExtension] = Field(
        default_factory=list, description="Typed foundation vote extensions."
    )
    created_at: str = Field(description="UTC creation timestamp in RFC 3339 form.")


class ReleaseManifestV1(ToolingDerivedModel):
    """Stable final release manifest for either direct publication or exact promotion."""

    schema_version: Literal["1"] = Field(default="1", description="Manifest schema version.")
    kind: Literal["release-manifest"] = Field(
        default="release-manifest", description="Manifest kind discriminator."
    )
    release: ReleaseIdentity = Field(description="Exact component release identity.")
    source: SourceRevision = Field(description="Exact final release source revision.")
    final_tag: TagIdentity = Field(description="Exact immutable final tag identity.")
    artifacts: list[ArtifactReference] = Field(
        default_factory=list, description="Immutable final artifact inventory."
    )
    publications: list[PublicationReference] = Field(
        default_factory=list, description="Provider-neutral final publication references."
    )
    verification_results: list[VerificationResultReference] = Field(
        default_factory=list, description="Final verification result references."
    )
    promoted_candidate: PromotedCandidateReference | None = Field(
        default=None, description="Exact promoted candidate and manifest, absent for direct releases."
    )
    promotion_evidence: list[PromotionEvidence] = Field(
        default_factory=list, description="Per-artifact typed promotion relations."
    )
    secondary_publications: list[PublicationReference] = Field(
        default_factory=list, description="Secondary package or registry publication results."
    )
    moving_alias_results: list[PublicationReference] = Field(
        default_factory=list, description="Moving tag or alias update results."
    )
    tooling: ToolingInvocationProvenance = Field(
        description="Tooling revision and invocation provenance."
    )
    created_at: str = Field(description="UTC creation timestamp in RFC 3339 form.")
    extensions: list[ReleaseExtension] = Field(
        default_factory=list, description="Typed platform or foundation final extensions."
    )

    @model_validator(mode="after")
    def _validate_release_relations(self) -> ReleaseManifestV1:
        if self.final_tag.purpose != "final":
            raise ValueError("release manifest final_tag purpose must be final")
        if self.final_tag.target_commit != self.source.commit_sha:
            raise ValueError("final tag must target the final source revision")
        if self.promoted_candidate is None and self.promotion_evidence:
            raise ValueError("promotion_evidence requires promoted_candidate")
        if (
            self.promoted_candidate is not None
            and self.promoted_candidate.candidate.release != self.release
        ):
            raise ValueError("promoted candidate must refer to the same release")
        return self

    @model_serializer(mode="wrap")
    def _omit_absent_promotion(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        payload = handler(self)
        if not isinstance(payload, dict):
            raise TypeError("release manifest serializer expected an object")
        if self.promoted_candidate is None:
            payload.pop("promoted_candidate", None)
        return payload


CandidateManifestV1.schema_export = SchemaExportSpecification(
    filename="candidate-manifest-v1.schema.json",
    audience="supported",
    stability="stable",
    summary="Stable Buildish manifest for one exact release candidate.",
)
VotePackageV1.schema_export = SchemaExportSpecification(
    filename="vote-package-v1.schema.json",
    audience="supported",
    stability="stable",
    summary="Stable optional vote package bound to one candidate manifest digest.",
)
ReleaseManifestV1.schema_export = SchemaExportSpecification(
    filename="release-manifest-v1.schema.json",
    audience="supported",
    stability="stable",
    summary="Stable Buildish manifest for one final direct or promoted release.",
)
