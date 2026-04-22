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

"""Provider-neutral stable manifest primitives and promotion evidence."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import Field, model_validator

from buildish_release_tooling.docs.documentation import ToolingDerivedModel
from buildish_release_tooling.release.core.models import CandidateIdentity


class ManifestDigestReference(ToolingDerivedModel):
    """URI and cryptographic digest binding one exact manifest document."""

    uri: str = Field(description="URI of the exact manifest document.")
    algorithm: Literal["sha256", "sha512"] = Field(
        default="sha256", description="Digest algorithm."
    )
    digest: str = Field(description="Lowercase hexadecimal manifest digest.")

    @model_validator(mode="after")
    def _validate_digest_length(self) -> ManifestDigestReference:
        expected_length = 64 if self.algorithm == "sha256" else 128
        if re.fullmatch(rf"[0-9a-f]{{{expected_length}}}", self.digest) is None:
            raise ValueError(f"{self.algorithm} digest must contain {expected_length} hex digits")
        return self


class PromotedCandidateReference(ToolingDerivedModel):
    """Exact candidate identity and manifest selected for final promotion."""

    candidate: CandidateIdentity = Field(description="Exact promoted candidate identity.")
    manifest: ManifestDigestReference = Field(
        description="Cryptographic reference to the exact candidate manifest."
    )


class ByteIdenticalPromotionEvidence(ToolingDerivedModel):
    """Evidence that candidate and final artifact bytes have identical digests."""

    relation: Literal["byte-identical"] = Field(
        default="byte-identical", description="Promotion evidence discriminator."
    )
    artifact_name: str = Field(description="Logical artifact name covered by the evidence.")
    candidate_digests: dict[str, str] = Field(
        description="Candidate artifact digests keyed by algorithm."
    )
    final_digests: dict[str, str] = Field(
        description="Final artifact digests keyed by algorithm."
    )

    @model_validator(mode="after")
    def _validate_identical_digests(self) -> ByteIdenticalPromotionEvidence:
        if not self.candidate_digests or self.candidate_digests != self.final_digests:
            raise ValueError("byte-identical evidence requires matching non-empty digest sets")
        return self


class RegistryIdentityPromotionEvidence(ToolingDerivedModel):
    """Evidence that an immutable package or registry identity is unchanged."""

    relation: Literal["registry-identity"] = Field(
        default="registry-identity", description="Promotion evidence discriminator."
    )
    artifact_name: str = Field(description="Logical artifact name covered by the evidence.")
    registry_kind: str = Field(description="Package or registry ecosystem discriminator.")
    immutable_identity: str = Field(
        description="Immutable digest or ecosystem coordinate retained by promotion."
    )


class SameSourceRevisionPromotionEvidence(ToolingDerivedModel):
    """Evidence that candidate and final snapshots resolve to the same source commit."""

    relation: Literal["same-source-revision"] = Field(
        default="same-source-revision", description="Promotion evidence discriminator."
    )
    artifact_name: str = Field(description="Logical source snapshot name.")
    candidate_tag: str = Field(description="Candidate tag used for the generated snapshot.")
    final_tag: str = Field(description="Final tag used for the generated snapshot.")
    source_commit_sha: str = Field(
        description="Exact commit targeted by both candidate and final tags."
    )


PromotionEvidence = Annotated[
    ByteIdenticalPromotionEvidence
    | RegistryIdentityPromotionEvidence
    | SameSourceRevisionPromotionEvidence,
    Field(discriminator="relation"),
]


class AuthenticityReference(ToolingDerivedModel):
    """Optional signature or attestation reference for a manifest or vote package."""

    kind: str = Field(description="Authenticity mechanism discriminator.")
    uri: str = Field(description="URI of the signature or attestation.")
    signer: str | None = Field(
        default=None, description="Optional signer identity or key fingerprint."
    )
