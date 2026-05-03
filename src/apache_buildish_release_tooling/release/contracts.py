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

"""Owned release-tooling contract models for emitted JSON documents."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, field_validator, model_validator
from pydantic.functional_validators import AfterValidator

from apache_buildish_release_tooling.docs.documentation import (
    SchemaExportSpecification,
    ToolingDerivedModel as BuildishContractModel,
)

SchemaVersionV1 = Literal["1"]
VerificationVerdict = Literal["verified", "failed"]
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ArtifactKind = Literal[
    "generic-file",
    "generic-file-with-openpgp",
    "maven-repository",
    "npm-package",
    "oci-image",
    "python-distribution",
]
SecondaryVerificationKind = Literal[
    "generic-file",
    "generic-file-with-openpgp",
    "maven-repository",
    "npm-package",
    "oci-image",
    "python-distribution",
    "_invalid-secondary-artifact-entry",
]


def _normalized_hex_digest(value: str, *, expected_length: int, label: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != expected_length or any(character not in "0123456789abcdef" for character in normalized):
        raise ValueError(f"{label} must be a {expected_length}-character hexadecimal digest")
    return normalized


def _normalize_sha256(value: str) -> str:
    return _normalized_hex_digest(value, expected_length=64, label="sha256")


def _normalize_sha512(value: str) -> str:
    return _normalized_hex_digest(value, expected_length=128, label="sha512")


def _normalize_git_commit_sha(value: str) -> str:
    return _normalized_hex_digest(value, expected_length=40, label="git_commit_sha")


def _normalize_oci_digest(value: str) -> str:
    normalized = value.strip().lower()
    algorithm, separator, encoded_digest = normalized.partition(":")
    if not separator or not algorithm or not encoded_digest:
        raise ValueError("OCI digest must use the form algorithm:<hex>")
    if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_+.-" for character in algorithm):
        raise ValueError("OCI digest algorithm contains unsupported characters")
    if len(encoded_digest) < 32 or any(character not in "0123456789abcdef" for character in encoded_digest):
        raise ValueError("OCI digest payload must be hexadecimal")
    return normalized


Sha256Hex = Annotated[str, AfterValidator(_normalize_sha256)]
Sha512Hex = Annotated[str, AfterValidator(_normalize_sha512)]
GitCommitSha = Annotated[str, AfterValidator(_normalize_git_commit_sha)]
OciContentDigest = Annotated[str, AfterValidator(_normalize_oci_digest)]


class SignatureReference(BuildishContractModel):
    """One detached OpenPGP signature reference."""

    type: Literal["openpgp-detached-ascii-armored"] = Field(default="openpgp-detached-ascii-armored", description="Stable subtype discriminator or signature-reference type for the related payload.")
    uri: NonEmptyString = Field(description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")


class ReproducibilitySelector(BuildishContractModel):
    """Signed manifest selector for one canonical local reproducibility profile."""

    profile_id: NonEmptyString = Field(description="Reproducibility profile identifier selected for the related artifact or source verification.")


class SignatureVerificationPayload(BuildishContractModel):
    """Serialized detached-signature verification details."""

    signer_fingerprint: NonEmptyString = Field(description="OpenPGP fingerprint of the key that verified the related detached signature.")
    signer_user_id: str | None = Field(default=None, description="Primary user id string reported by GnuPG for the key that verified the related detached signature.")
    trust_label: str | None = Field(default=None, description="Human-readable GnuPG trust label returned by signature verification.")
    key_algorithm: str | None = Field(default=None, description="Public-key algorithm reported for the signing key that verified the related detached signature.")
    key_size_bits: int | None = Field(description="Public-key size, in bits, reported for the signing key that verified the related detached signature.", default=None, ge=0)


class VerificationFailurePayload(BuildishContractModel):
    """One collected verification failure."""

    scope: NonEmptyString = Field(description="Machine-readable scope label that identifies which verification surface produced the related failure record.")
    subject: NonEmptyString = Field(description="Human-facing verification failure subject that identifies what failed.")
    message: NonEmptyString = Field(description="Human-readable message body associated with the related verification failure, harness tag object, or fixture definition.")


class Sha256ChecksumPayload(BuildishContractModel):
    """One sha256 checksum value and optional detached sidecar URI."""

    value: Sha256Hex = Field(description="Declared checksum or digest value recorded in the related payload.")
    uri: NonEmptyString | None = Field(default=None, description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")


class Sha512ChecksumPayload(BuildishContractModel):
    """One sha512 checksum value and optional detached sidecar URI."""

    value: Sha512Hex = Field(description="Declared checksum or digest value recorded in the related payload.")
    uri: NonEmptyString | None = Field(default=None, description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")


class Sha256Checksums(BuildishContractModel):
    """A checksum block containing one sha256 entry."""

    sha256: Sha256ChecksumPayload = Field(description="SHA-256 checksum payload associated with the related artifact.")


class Sha512Checksums(BuildishContractModel):
    """A checksum block containing one sha512 entry."""

    sha512: Sha512ChecksumPayload = Field(description="SHA-512 checksum payload associated with the related artifact.")


class NpmChecksums(BuildishContractModel):
    """A checksum block for npm artifacts, which may use sha256 or sha512."""

    sha256: Sha256ChecksumPayload | None = Field(default=None, description="SHA-256 checksum payload associated with the related artifact.")
    sha512: Sha512ChecksumPayload | None = Field(default=None, description="SHA-512 checksum payload associated with the related artifact.")

    @model_validator(mode="after")
    def validate_exactly_one_algorithm(self) -> NpmChecksums:
        algorithms = [payload for payload in (self.sha256, self.sha512) if payload is not None]
        if len(algorithms) != 1:
            raise ValueError("npm-package checksums must declare exactly one of sha256 or sha512")
        return self


class SupplementalInventoryReference(BuildishContractModel):
    """One staged supplemental inventory attachment."""

    filename: NonEmptyString = Field(description="Artifact filename as seen in staging, manifests, or retained evidence.")
    sha512: Sha512Hex = Field(description="SHA-512 checksum payload associated with the related artifact.")
    uri: NonEmptyString | None = Field(default=None, description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")
    entry_count: int | None = Field(description="Number of entries recorded in the related inventory, repository snapshot, or artifact collection.", default=None, ge=0)
    total_size_bytes: int | None = Field(description="Total size, in bytes, recorded for the related artifact collection or inventory.", default=None, ge=0)


class NpmProvenanceAuth(BuildishContractModel):
    """Explicit npm provenance metadata."""

    scheme: Literal["npm-provenance"] = Field(default="npm-provenance", description="Stable scheme identifier that names the authenticity or provenance mechanism represented by the related payload.")
    repository: NonEmptyString = Field(description="Repository identifier or repository name associated with the related provenance or external-auth record.")


class PyPiAttestationAuth(BuildishContractModel):
    """Explicit PyPI attestation metadata."""

    scheme: Literal["pypi-attestation"] = Field(default="pypi-attestation", description="Stable scheme identifier that names the authenticity or provenance mechanism represented by the related payload.")
    repository: NonEmptyString = Field(description="Repository identifier or repository name associated with the related provenance or external-auth record.")


class OciPlatformDigest(BuildishContractModel):
    """One platform-specific digest declared for an OCI image."""

    platform: NonEmptyString = Field(description="OCI platform identifier in `os/arch[/variant]` form.")
    digest: OciContentDigest = Field(description="OCI content digest or similar immutable digest string for the related artifact.")


class SecondaryArtifactBase(BuildishContractModel):
    """Common fields shared across supported secondary artifact kinds."""

    artifact_id: NonEmptyString = Field(description="Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling.")
    kind: str = Field(description="Declared artifact or report kind discriminator.")
    role: NonEmptyString | None = Field(default=None, description="Artifact role within the RC manifest, such as source artifact, vote-manifest supplement, or convenience artifact.")
    artifact_origin: NonEmptyString | None = Field(default=None, description="Origin classification describing whether the artifact came from a source build, registry, or repository staging area.")
    git_commit_sha: GitCommitSha | None = Field(default=None, description="Git commit SHA recorded for the related artifact, manifest, or provenance block.")
    reproducibility: ReproducibilitySelector | None = Field(default=None, description="Reproducibility policy or result block associated with the related source or secondary artifact.")
    inventory: SupplementalInventoryReference | None = Field(default=None, description="Signed inventory or supplemental staging metadata associated with the related artifact.")


class GenericFileSecondaryArtifact(SecondaryArtifactBase):
    """A standalone file artifact tracked in the signed vote manifest."""

    kind: Literal["generic-file"] = Field(default="generic-file", description="Declared artifact or report kind discriminator.")
    filename: NonEmptyString = Field(description="Artifact filename as seen in staging, manifests, or retained evidence.")
    uri: NonEmptyString = Field(description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")
    checksums: Sha512Checksums = Field(description="Declared checksum sidecars or signed checksum values associated with this artifact.")
    signatures: list[SignatureReference] = Field(description="Declared detached signature references associated with the related artifact or manifest.", default_factory=list)


class GenericFileWithOpenPgpSecondaryArtifact(SecondaryArtifactBase):
    """A standalone file artifact that requires at least one detached signature."""

    kind: Literal["generic-file-with-openpgp"] = Field(default="generic-file-with-openpgp", description="Declared artifact or report kind discriminator.")
    filename: NonEmptyString = Field(description="Artifact filename as seen in staging, manifests, or retained evidence.")
    uri: NonEmptyString = Field(description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")
    checksums: Sha512Checksums = Field(description="Declared checksum sidecars or signed checksum values associated with this artifact.")
    signatures: list[SignatureReference] = Field(description="Declared detached signature references associated with the related artifact or manifest.", default_factory=list)

    @model_validator(mode="after")
    def validate_signature_presence(self) -> GenericFileWithOpenPgpSecondaryArtifact:
        if not self.signatures:
            raise ValueError("generic-file-with-openpgp requires at least one detached signature")
        return self


class MavenRepositorySecondaryArtifact(SecondaryArtifactBase):
    """A staged Maven repository validated through a signed inventory."""

    kind: Literal["maven-repository"] = Field(default="maven-repository", description="Declared artifact or report kind discriminator.")
    staging_repository_id: NonEmptyString = Field(description="Repository identifier of the staged Maven repository under verification.")
    base_url: NonEmptyString = Field(description="Base URL used to discover or publish the related artifact or service resource.")
    inventory: SupplementalInventoryReference = Field(description="Signed inventory or supplemental staging metadata associated with the related artifact.")


class NpmPackageSecondaryArtifact(SecondaryArtifactBase):
    """A published npm package tarball."""

    kind: Literal["npm-package"] = Field(default="npm-package", description="Declared artifact or report kind discriminator.")
    filename: NonEmptyString = Field(description="Artifact filename as seen in staging, manifests, or retained evidence.")
    uri: NonEmptyString = Field(description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")
    registry_url: NonEmptyString = Field(description="Registry metadata URL used for npm package verification.")
    package_name: NonEmptyString = Field(description="Normalized npm package name associated with the related package artifact or registry lookup.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    integrity: NonEmptyString = Field(description="Integrity verification details derived from registry metadata or sidecar checksums.")
    checksums: NpmChecksums = Field(description="Declared checksum sidecars or signed checksum values associated with this artifact.")
    authenticity: NpmProvenanceAuth | None = Field(default=None, description="Authenticity metadata, such as provenance or attestation references, associated with the related package artifact.")


class OciImageSecondaryArtifact(SecondaryArtifactBase):
    """An immutable OCI image reference."""

    kind: Literal["oci-image"] = Field(default="oci-image", description="Declared artifact or report kind discriminator.")
    uri: NonEmptyString = Field(description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")
    registry: NonEmptyString = Field(description="Container registry host or namespace that serves the related OCI image.")
    repository: NonEmptyString = Field(description="Repository identifier or repository name associated with the related provenance or external-auth record.")
    digest: OciContentDigest = Field(description="OCI content digest or similar immutable digest string for the related artifact.")
    platform_digests: list[OciPlatformDigest] | None = Field(default=None, description="Per-platform OCI digests declared or observed for a multi-platform image.")

    @model_validator(mode="after")
    def validate_unique_platforms(self) -> OciImageSecondaryArtifact:
        if self.platform_digests is None:
            return self
        platforms = [entry.platform for entry in self.platform_digests]
        if len(platforms) != len(set(platforms)):
            raise ValueError("oci-image platform_digests must not contain duplicate platforms")
        return self


class PythonDistributionSecondaryArtifact(SecondaryArtifactBase):
    """A published Python distribution file."""

    kind: Literal["python-distribution"] = Field(default="python-distribution", description="Declared artifact or report kind discriminator.")
    filename: NonEmptyString = Field(description="Artifact filename as seen in staging, manifests, or retained evidence.")
    uri: NonEmptyString = Field(description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")
    index_url: NonEmptyString = Field(description="Base Python simple-index URL that Buildish used for package verification.")
    project_name: NonEmptyString = Field(description="Python package project name associated with the related distribution artifact.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    checksums: Sha256Checksums = Field(description="Declared checksum sidecars or signed checksum values associated with this artifact.")
    authenticity: PyPiAttestationAuth | None = Field(default=None, description="Authenticity metadata, such as provenance or attestation references, associated with the related package artifact.")


AnySecondaryArtifact = Annotated[
    GenericFileSecondaryArtifact
    | GenericFileWithOpenPgpSecondaryArtifact
    | MavenRepositorySecondaryArtifact
    | NpmPackageSecondaryArtifact
    | OciImageSecondaryArtifact
    | PythonDistributionSecondaryArtifact,
    Field(discriminator="kind"),
]
StrictSecondaryArtifactAdapter: TypeAdapter[AnySecondaryArtifact] = TypeAdapter(
    AnySecondaryArtifact
)


class SecondaryArtifactManifestV1(BuildishContractModel):
    """A reusable secondary-artifact manifest fragment."""

    secondary_artifacts: list[AnySecondaryArtifact] = Field(description="Declared secondary artifacts retained in the RC vote manifest or secondary-artifact manifest.")


class ToolingProvenance(BuildishContractModel):
    """Tooling repository provenance embedded in emitted manifests."""

    repository: NonEmptyString = Field(description="Repository identifier or repository name associated with the related provenance or external-auth record.")
    repository_url: NonEmptyString = Field(description="Canonical clone or browser URL for the related repository.")
    git_commit_sha: GitCommitSha = Field(description="Git commit SHA recorded for the related artifact, manifest, or provenance block.")
    git_ref: NonEmptyString | None = Field(default=None, description="Git ref name recorded in tooling provenance for the related manifest or emitted file.")
    version: NonEmptyString | None = Field(default=None, description="Release version string without a leading `v` prefix.")


class GithubWorkflowProvenance(BuildishContractModel):
    """GitHub Actions provenance embedded in emitted manifests."""

    repository: NonEmptyString = Field(description="Repository identifier or repository name associated with the related provenance or external-auth record.")
    workflow: str = Field(description="Nested workflow block for an `act` harness scenario, or the workflow name recorded in provenance.")
    workflow_ref: str = Field(description="GitHub Actions workflow ref associated with the related provenance record.")
    run_id: int = Field(description="GitHub Actions run id associated with the related provenance record.", ge=0)
    run_attempt: int | None = Field(description="GitHub Actions run attempt number associated with the related provenance record.", default=None, ge=0)
    run_url: NonEmptyString | None = Field(default=None, description="Browser URL of the related GitHub Actions workflow run.")


class ManifestProvenance(BuildishContractModel):
    """Top-level provenance block for the RC vote manifest."""

    created_at: NonEmptyString = Field(description="Timestamp when Buildish created the enclosing manifest or provenance record.")
    tooling: ToolingProvenance = Field(description="Buildish tooling provenance details embedded in the authoritative manifest.")
    github: GithubWorkflowProvenance | None = Field(default=None, description="GitHub workflow provenance metadata embedded in or read from the RC vote manifest.")


class _BuildishTolerantReadModel(BaseModel):
    """Base model for tolerant read-side subsets with forward-compatible extra fields."""

    model_config = ConfigDict(extra="allow")


class ToolingProvenanceRead(_BuildishTolerantReadModel):
    """Tolerant tooling provenance subset accepted by verify-rc readers."""

    repository: str | None = Field(default=None, description="Repository identifier or repository name associated with the related provenance or external-auth record.")
    repository_url: NonEmptyString | None = Field(default=None, description="Canonical clone or browser URL for the related repository.")
    git_commit_sha: GitCommitSha | None = Field(default=None, description="Git commit SHA recorded for the related artifact, manifest, or provenance block.")
    git_ref: str | None = Field(default=None, description="Git ref name recorded in tooling provenance for the related manifest or emitted file.")
    version: str | None = Field(default=None, description="Release version string without a leading `v` prefix.")


class GithubWorkflowProvenanceRead(_BuildishTolerantReadModel):
    """Tolerant GitHub workflow provenance subset accepted by verify-rc readers."""

    repository: str | None = Field(default=None, description="Repository identifier or repository name associated with the related provenance or external-auth record.")
    workflow: str | None = Field(default=None, description="Nested workflow block for an `act` harness scenario, or the workflow name recorded in provenance.")
    workflow_ref: str | None = Field(default=None, description="GitHub Actions workflow ref associated with the related provenance record.")
    run_id: int | None = Field(description="GitHub Actions run id associated with the related provenance record.", default=None, ge=0)
    run_attempt: int | None = Field(description="GitHub Actions run attempt number associated with the related provenance record.", default=None, ge=0)
    run_url: str | None = Field(default=None, description="Browser URL of the related GitHub Actions workflow run.")


class ManifestProvenanceRead(_BuildishTolerantReadModel):
    """Tolerant top-level provenance block accepted by verify-rc readers."""

    created_at: str | None = Field(default=None, description="Timestamp when Buildish created the enclosing manifest or provenance record.")
    tooling: ToolingProvenanceRead = Field(description="Buildish tooling provenance details embedded in the authoritative manifest.")
    github: GithubWorkflowProvenanceRead | None = Field(default=None, description="GitHub workflow provenance metadata embedded in or read from the RC vote manifest.")


class AsfKeysTrustRoot(BuildishContractModel):
    """Pinned ASF KEYS metadata used as a trust root."""

    uri: NonEmptyString = Field(description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")
    known_length_bytes: int = Field(description="Expected byte length of the pinned ASF KEYS file when Buildish establishes the trust root.", ge=0)
    known_prefix_sha512: Sha512Hex = Field(description="Pinned SHA-512 digest prefix that Buildish expects the ASF KEYS file to start with.")


class ManifestTrustRoots(BuildishContractModel):
    """Trust roots referenced by the signed manifest."""

    asf_keys: AsfKeysTrustRoot = Field(description="Pinned ASF KEYS trust-root details that Buildish should use when verifying the RC manifest signature chain.")


class AsfKeysTrustRootRead(AsfKeysTrustRoot):
    """Tolerant ASF KEYS trust-root subset accepted by verify-rc readers."""

    model_config = ConfigDict(extra="allow")


class ManifestTrustRootsRead(_BuildishTolerantReadModel):
    """Tolerant trust-root block accepted by verify-rc readers."""

    asf_keys: AsfKeysTrustRootRead = Field(description="Pinned ASF KEYS trust-root details that Buildish should use when verifying the RC manifest signature chain.")


class DraftGithubRelease(BuildishContractModel):
    """Convenience pointer to the matching draft GitHub Release."""

    repository: NonEmptyString = Field(description="Repository identifier or repository name associated with the related provenance or external-auth record.")
    tag: NonEmptyString = Field(description="Tag name associated with the related release, workflow fixture, or synthetic GitHub tag-object payload.")
    url: NonEmptyString = Field(description="Canonical browser or download URL associated with the related record.")


class DraftGithubReleaseRead(DraftGithubRelease):
    """Tolerant draft-release pointer accepted by verify-rc readers."""

    model_config = ConfigDict(extra="allow")


class SourceArtifactContract(BuildishContractModel):
    """The single source artifact under vote."""

    role: Literal["asf-source-release"] = Field(default="asf-source-release", description="Artifact role within the RC manifest, such as source artifact, vote-manifest supplement, or convenience artifact.")
    filename: NonEmptyString = Field(description="Artifact filename as seen in staging, manifests, or retained evidence.")
    uri: NonEmptyString = Field(description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")
    artifact_origin: NonEmptyString = Field(description="Origin classification describing whether the artifact came from a source build, registry, or repository staging area.")
    git_commit_sha: GitCommitSha = Field(description="Git commit SHA recorded for the related artifact, manifest, or provenance block.")
    reproducibility: ReproducibilitySelector | None = Field(default=None, description="Reproducibility policy or result block associated with the related source or secondary artifact.")
    checksums: Sha512Checksums = Field(description="Declared checksum sidecars or signed checksum values associated with this artifact.")
    signatures: list[SignatureReference] = Field(description="Declared detached signature references associated with the related artifact or manifest.", min_length=1)


class SourceArtifactContractRead(SourceArtifactContract):
    """Tolerant source-artifact contract accepted by verify-rc readers."""

    model_config = ConfigDict(extra="allow")


class SecondaryArtifactChecksumPayloadRead(_BuildishTolerantReadModel):
    """Tolerant checksum payload used while reading secondary artifacts."""

    value: str | None = Field(default=None, description="Declared checksum or digest value recorded in the related payload.")
    uri: str | None = Field(default=None, description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")


class SecondaryArtifactChecksumsRead(_BuildishTolerantReadModel):
    """Tolerant checksum block accepted by verify-rc secondary-artifact readers."""

    sha256: SecondaryArtifactChecksumPayloadRead | None = Field(default=None, description="SHA-256 checksum payload associated with the related artifact.")
    sha512: SecondaryArtifactChecksumPayloadRead | None = Field(default=None, description="SHA-512 checksum payload associated with the related artifact.")


class SecondaryArtifactSignatureReferenceRead(_BuildishTolerantReadModel):
    """Tolerant detached-signature reference accepted by verify-rc readers."""

    type: str | None = Field(default=None, description="Stable subtype discriminator or signature-reference type for the related payload.")
    uri: str | None = Field(default=None, description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")


class SecondaryArtifactInventoryRead(_BuildishTolerantReadModel):
    """Tolerant supplemental inventory reference accepted by verify-rc readers."""

    filename: str | None = Field(default=None, description="Artifact filename as seen in staging, manifests, or retained evidence.")
    sha512: str | None = Field(default=None, description="SHA-512 checksum payload associated with the related artifact.")
    uri: str | None = Field(default=None, description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")
    entry_count: int | None = Field(default=None, description="Number of entries recorded in the related inventory, repository snapshot, or artifact collection.")
    total_size_bytes: int | None = Field(default=None, description="Total size, in bytes, recorded for the related artifact collection or inventory.")


class SecondaryArtifactEnvelopeRead(_BuildishTolerantReadModel):
    """Tolerant secondary-artifact envelope used before strict kind validation."""

    artifact_id: str | None = Field(default=None, description="Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling.")
    kind: str | None = Field(default=None, description="Declared artifact or report kind discriminator.")
    filename: str | None = Field(default=None, description="Artifact filename as seen in staging, manifests, or retained evidence.")
    uri: str | None = Field(default=None, description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")
    checksums: SecondaryArtifactChecksumsRead | None = Field(default=None, description="Declared checksum sidecars or signed checksum values associated with this artifact.")
    signatures: list[SecondaryArtifactSignatureReferenceRead] | None = Field(default=None, description="Declared detached signature references associated with the related artifact or manifest.")
    inventory: SecondaryArtifactInventoryRead | None = Field(default=None, description="Signed inventory or supplemental staging metadata associated with the related artifact.")


class VoteMaterialsStrict(BuildishContractModel):
    """Strict vote-materials block for authored and emitted manifests."""

    source_artifacts: list[SourceArtifactContract] = Field(description="Manifest entries that describe the primary staged source artifact and any additional source-release materials.")
    secondary_artifacts: list[AnySecondaryArtifact] = Field(description="Declared secondary artifacts retained in the RC vote manifest or secondary-artifact manifest.", default_factory=list)

    @model_validator(mode="after")
    def validate_single_source_artifact(self) -> VoteMaterialsStrict:
        if len(self.source_artifacts) != 1:
            raise ValueError("RC vote manifests must contain exactly one source artifact")
        return self


class VoteMaterialsRead(BuildishContractModel):
    """Tolerant vote-materials block used by verify-rc readers."""

    model_config = ConfigDict(extra="allow")

    source_artifacts: list[SourceArtifactContractRead] = Field(description="Manifest entries that describe the primary staged source artifact and any additional source-release materials.")
    secondary_artifacts: list[AnySecondaryArtifact | SecondaryArtifactEnvelopeRead] = Field(
        description="Declared secondary artifacts retained in the RC vote manifest or secondary-artifact manifest, including tolerant read-side envelopes for malformed entries.",
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_single_source_artifact(self) -> VoteMaterialsRead:
        if len(self.source_artifacts) != 1:
            raise ValueError("RC vote manifests must contain exactly one source artifact")
        return self


class AuthoritativeManifestReference(BuildishContractModel):
    """Reference to the authoritative signed manifest file and sidecars."""

    uri: NonEmptyString = Field(description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")
    checksum_uris: dict[Literal["sha512"], NonEmptyString] = Field(description="Manifest-relative or absolute URIs of checksum sidecars associated with the authoritative staged manifest.")
    signatures: list[SignatureReference] = Field(description="Declared detached signature references associated with the related artifact or manifest.", min_length=1)


class AuthoritativeManifestReferenceRead(AuthoritativeManifestReference):
    """Tolerant authoritative-manifest reference accepted by verify-rc readers."""

    model_config = ConfigDict(extra="allow")


class ManifestVerificationMetadataStrict(BuildishContractModel):
    """Strict verification metadata emitted by finalize-rc-vote-materials."""

    staging_svn_url: NonEmptyString = Field(description="ASF SVN staging directory URL associated with the authoritative RC materials.")
    authoritative_manifest: AuthoritativeManifestReference = Field(description="Canonical authoritative RC vote-manifest reference or verification block associated with the enclosing payload.")


class ManifestVerificationMetadataRead(_BuildishTolerantReadModel):
    """Tolerant verification metadata accepted by verify-rc."""

    staging_svn_url: NonEmptyString = Field(description="ASF SVN staging directory URL associated with the authoritative RC materials.")
    authoritative_manifest: AuthoritativeManifestReferenceRead | None = Field(default=None, description="Canonical authoritative RC vote-manifest reference or verification block associated with the enclosing payload.")


class RcVoteManifestV1(BuildishContractModel):
    """Strict authoritative RC vote manifest emitted by buildish-release-tooling."""

    schema_version: SchemaVersionV1 = Field(default="1", description="Schema version of the enclosing Buildish JSON or YAML contract.")
    manifest_type: Literal["rc-vote"] = Field(default="rc-vote", description="Stable manifest contract discriminator for one Buildish file format.")
    component_id: NonEmptyString = Field(description="Stable component identifier used across Buildish manifests, reports, and release-state records.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    release_line: NonEmptyString = Field(description="Maintenance-line identifier used to group related versions, branches, and moving tags.")
    release_branch: NonEmptyString = Field(description="Git branch name that Buildish resolved as the authoritative release branch.")
    source_repository_url: NonEmptyString = Field(description="Canonical source repository URL recorded in the RC vote manifest or verification report.")
    source_commit_sha: GitCommitSha = Field(description="Resolved source Git commit SHA recorded in the authoritative RC manifest or verify-rc report.")
    source_date_epoch: int = Field(description="Canonical `SOURCE_DATE_EPOCH` integer carried through RC production and verification.", ge=0)
    rc_tag: NonEmptyString = Field(description="Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix.")
    final_tag: NonEmptyString = Field(description="Final immutable Git tag that Buildish intends to publish for the released version.")
    final_tag_mode: NonEmptyString = Field(description="Configured or recorded policy describing how the final immutable release tag should be created for this component or release run.")
    provenance: ManifestProvenance = Field(description="Tooling, workflow, or publication provenance block embedded in or read from the related Buildish contract.")
    trust_roots: ManifestTrustRoots = Field(description="Pinned trust-root material that verify-rc uses to establish authenticity for the authoritative RC vote manifest.")
    draft_github_release: DraftGithubRelease = Field(description="Draft GitHub release metadata embedded in or read from the RC vote manifest.")
    vote_materials: VoteMaterialsStrict = Field(description="Vote-materials reference block embedded in or read from the authoritative RC vote manifest.")
    verification: ManifestVerificationMetadataStrict = Field(description="Verification metadata block nested inside the authoritative RC vote manifest.")
    materialized_commit_sha: GitCommitSha | None = Field(default=None, description="Git commit SHA of the materialized tree that Buildish created for the RC tagging workflow.")


class RcVoteManifestReadV1(_BuildishTolerantReadModel):
    """Tolerant RC vote-manifest reader used by verify-rc."""

    schema_version: SchemaVersionV1 = Field(default="1", description="Schema version of the enclosing Buildish JSON or YAML contract.")
    manifest_type: Literal["rc-vote"] = Field(default="rc-vote", description="Stable manifest contract discriminator for one Buildish file format.")
    component_id: NonEmptyString = Field(description="Stable component identifier used across Buildish manifests, reports, and release-state records.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    release_line: NonEmptyString = Field(description="Maintenance-line identifier used to group related versions, branches, and moving tags.")
    release_branch: NonEmptyString = Field(description="Git branch name that Buildish resolved as the authoritative release branch.")
    source_repository_url: NonEmptyString = Field(description="Canonical source repository URL recorded in the RC vote manifest or verification report.")
    source_commit_sha: GitCommitSha = Field(description="Resolved source Git commit SHA recorded in the authoritative RC manifest or verify-rc report.")
    source_date_epoch: int = Field(description="Canonical `SOURCE_DATE_EPOCH` integer carried through RC production and verification.")
    rc_tag: NonEmptyString | None = Field(default=None, description="Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix.")
    final_tag: NonEmptyString = Field(description="Final immutable Git tag that Buildish intends to publish for the released version.")
    final_tag_mode: NonEmptyString = Field(description="Configured or recorded policy describing how the final immutable release tag should be created for this component or release run.")
    provenance: ManifestProvenanceRead = Field(description="Tooling, workflow, or publication provenance block embedded in or read from the related Buildish contract.")
    trust_roots: ManifestTrustRootsRead = Field(description="Pinned trust-root material that verify-rc uses to establish authenticity for the authoritative RC vote manifest.")
    draft_github_release: DraftGithubReleaseRead = Field(description="Draft GitHub release metadata embedded in or read from the RC vote manifest.")
    vote_materials: VoteMaterialsRead = Field(description="Vote-materials reference block embedded in or read from the authoritative RC vote manifest.")
    verification: ManifestVerificationMetadataRead = Field(description="Verification metadata block nested inside the authoritative RC vote manifest.")
    materialized_commit_sha: GitCommitSha | None = Field(default=None, description="Git commit SHA of the materialized tree that Buildish created for the RC tagging workflow.")

    @field_validator("source_date_epoch", mode="before")
    @classmethod
    def normalize_epoch(cls, value: object) -> int:
        if isinstance(value, int) and value >= 0:
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        raise ValueError("source_date_epoch must be a non-negative integer Unix epoch")


class MavenRepositoryInventoryEntry(BuildishContractModel):
    """One file entry in a signed Maven repository inventory."""

    path: NonEmptyString = Field(description="Filesystem path, relative artifact path, or retained evidence path associated with the related record.")
    size_bytes: int = Field(description="Byte size recorded for the related artifact, retained snapshot, or inventory entry.", ge=0)
    sha512: Sha512Hex = Field(description="SHA-512 checksum payload associated with the related artifact.")


class MavenRepositoryInventoryV1(BuildishContractModel):
    """A signed Maven repository inventory attachment."""

    schema_version: SchemaVersionV1 = Field(default="1", description="Schema version of the enclosing Buildish JSON or YAML contract.")
    inventory_type: Literal["maven-repository"] = Field(default="maven-repository", description="Stable manifest discriminator for the signed Maven repository inventory file.")
    artifact_id: NonEmptyString = Field(description="Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling.")
    staging_repository_id: NonEmptyString = Field(description="Repository identifier of the staged Maven repository under verification.")
    base_url: NonEmptyString = Field(description="Base URL used to discover or publish the related artifact or service resource.")
    entries: list[MavenRepositoryInventoryEntry] = Field(description="Typed entries recorded in the related manifest, inventory, or report payload.", min_length=1)


class ChecksumVerificationReport(BuildishContractModel):
    """Observed checksum verification results for one downloaded artifact."""

    algorithm: Literal["sha256", "sha512"] | None = Field(default=None, description="Checksum or digest algorithm name that Buildish used for the related verification or report entry.")
    value: str | None = Field(default=None, description="Declared checksum or digest value recorded in the related payload.")
    matches_manifest: bool | None = Field(default=None, description="Whether the observed checksum or digest matched the value declared in the authoritative manifest or inventory.")
    sidecar_verified: bool = Field(default=False, description="Whether the detached checksum sidecar associated with this report entry was fetched and verified successfully.")


class IntegrityVerificationReport(BuildishContractModel):
    """Observed integrity verification results for one npm package."""

    algorithm: Literal["sha256", "sha512"] | None = Field(default=None, description="Checksum or digest algorithm name that Buildish used for the related verification or report entry.")
    value: str | None = Field(default=None, description="Declared checksum or digest value recorded in the related payload.")
    matches_manifest_checksum: bool | None = Field(default=None, description="Whether the resolved checksum value matched the checksum declared in the signed manifest.")
    matches_downloaded_bytes: bool | None = Field(default=None, description="Whether the checksum or integrity value matched the bytes that Buildish actually downloaded.")


class InventoryVerificationReport(BuildishContractModel):
    """Verification results for one downloaded inventory attachment."""

    filename: NonEmptyString = Field(description="Artifact filename as seen in staging, manifests, or retained evidence.")
    uri: NonEmptyString = Field(description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")
    sha512: Sha512Hex = Field(description="SHA-512 checksum payload associated with the related artifact.")
    entry_count: int | None = Field(description="Number of entries recorded in the related inventory, repository snapshot, or artifact collection.", default=None, ge=0)
    total_size_bytes: int | None = Field(description="Total size, in bytes, recorded for the related artifact collection or inventory.", default=None, ge=0)


class LiveRepositorySignatureVerification(BuildishContractModel):
    """One detached signature verified in the live Maven repository."""

    path: NonEmptyString = Field(description="Filesystem path, relative artifact path, or retained evidence path associated with the related record.")
    target_path: NonEmptyString = Field(description="Target path that the related detached signature or copy operation refers to.")
    signature: SignatureVerificationPayload = Field(description="Signature verification details for the related artifact or manifest.")


class LiveMavenRepositoryReport(BuildishContractModel):
    """Observed live-repository comparison results for a Maven staging repository."""

    entry_count: int | None = Field(description="Number of entries recorded in the related inventory, repository snapshot, or artifact collection.", default=None, ge=0)
    total_size_bytes: int = Field(description="Total size, in bytes, recorded for the related artifact collection or inventory.", ge=0)
    matches_signed_inventory: bool = Field(description="Whether the live staged Maven repository contents matched the signed inventory metadata.")
    signature_verifications: list[LiveRepositorySignatureVerification] = Field(description="Detached-signature verification results collected for live Maven repository sidecars.", default_factory=list)


class PythonIndexResolutionReport(BuildishContractModel):
    """Resolution details for one Python simple-index lookup."""

    project_index_url: NonEmptyString = Field(description="Resolved Python simple-index page URL that Buildish used to discover the expected distribution artifact.")
    resolved_url: str | None = Field(default=None, description="Resolved direct distribution or tarball URL that Buildish selected from the related package index.")
    found_via: str | None = Field(default=None, description="Short note describing how the related package URL or artifact metadata was discovered during verification.")
    sha256_matches_index: bool | None = Field(default=None, description="Whether the distribution hash from the Python simple index matched the digest declared in the signed manifest.")


class NpmRegistryResolutionReport(BuildishContractModel):
    """Resolution details for one npm registry lookup."""

    metadata_url: str | None = Field(default=None, description="Registry metadata URL that Buildish fetched while resolving npm package verification data.")
    found_via: str | None = Field(default=None, description="Short note describing how the related package URL or artifact metadata was discovered during verification.")
    tarball_url_matches_manifest: bool | None = Field(default=None, description="Whether the tarball URL resolved from the npm registry metadata matched the URL declared in the signed manifest.")
    integrity_matches_manifest: bool | None = Field(default=None, description="Whether the integrity string or digest resolved from the registry matched the value declared in the signed manifest.")
    signatures_count: int = Field(description="Number of signature records or provenance signatures that the registry metadata exposed for the related npm package artifact.", ge=0)


class OciInspectionReport(BuildishContractModel):
    """Observed registry inspection results for one OCI image."""

    image_ref: NonEmptyString = Field(description="Fully qualified OCI image reference used for inspection or local rebuild comparison.")
    digest_matches_manifest: bool = Field(description="Whether the inspected OCI image digest matched the digest declared in the signed manifest.")
    platform_digests_match: bool | None = Field(default=None, description="Whether all inspected OCI platform digests matched the platform digests declared in the signed manifest.")
    platform_digests: list[OciPlatformDigest] = Field(description="Per-platform OCI digests declared or observed for a multi-platform image.", default_factory=list)


class InspectionEvidenceReference(BuildishContractModel):
    """One retained evidence file inside the verify-rc inspection bundle."""

    label: NonEmptyString = Field(description="Human-readable label used to name one evidence file or report section.")
    path: NonEmptyString = Field(description="Filesystem path, relative artifact path, or retained evidence path associated with the related record.")


ArchiveAnalysisFormat = Literal["tar", "zip", "non-archive"]


class ShallowArchiveAnalysisReport(BuildishContractModel):
    """Durable shallow archive-comparison findings for one retained artifact pair."""

    classification: NonEmptyString = Field(description="High-level shallow-comparison classification that summarizes the most important archive drift pattern Buildish observed.")
    raw_bytes_equal: bool = Field(description="Whether raw staged and rebuilt bytes matched before any archive-aware normalization.")
    archive_format: Literal["tar", "zip"] | None = Field(default=None, description="Detected top-level archive format of the compared artifact when shallow archive inspection succeeded.")
    staged_archive_format: ArchiveAnalysisFormat = Field(description="Detected top-level archive format of the staged artifact retained for shallow archive inspection.")
    rebuilt_archive_format: ArchiveAnalysisFormat = Field(description="Detected top-level archive format of the rebuilt artifact retained for shallow archive inspection.")
    staged_entry_count: int | None = Field(description="Number of top-level archive entries found in the staged artifact during shallow inspection.", default=None, ge=0)
    rebuilt_entry_count: int | None = Field(description="Number of top-level archive entries found in the rebuilt artifact during shallow inspection.", default=None, ge=0)
    missing_paths: list[NonEmptyString] = Field(description="Archive or repository paths that were present in the staged artifact but missing from the rebuilt artifact.", default_factory=list)
    unexpected_paths: list[NonEmptyString] = Field(description="Archive or repository paths that were present only in the rebuilt artifact and not in the staged artifact.", default_factory=list)
    entry_order_mismatches: list[NonEmptyString] = Field(description="Archive-entry ordering differences detected between the staged and rebuilt artifacts during shallow comparison.", default_factory=list)
    metadata_mismatches: list[NonEmptyString] = Field(description="Archive-entry metadata differences, such as timestamps, modes, owners, or file-type drift, found during shallow comparison.", default_factory=list)
    content_mismatches: list[NonEmptyString] = Field(description="Archive member paths whose direct top-level content bytes differed between the staged and rebuilt artifacts during shallow comparison.", default_factory=list)


class RetainedArtifactSnapshot(BuildishContractModel):
    """One retained file snapshot described inside an inspection-bundle metadata document."""

    filename: NonEmptyString = Field(description="Artifact filename as seen in staging, manifests, or retained evidence.")
    sha512: Sha512Hex = Field(description="SHA-512 checksum payload associated with the related artifact.")
    size_bytes: int = Field(description="Byte size recorded for the related artifact, retained snapshot, or inventory entry.", ge=0)


class RebuiltOutputSnapshot(BuildishContractModel):
    """One rebuilt output file described inside an inspection-bundle metadata document."""

    path: NonEmptyString = Field(description="Filesystem path, relative artifact path, or retained evidence path associated with the related record.")
    sha512: Sha512Hex = Field(description="SHA-512 checksum payload associated with the related artifact.")
    size_bytes: int = Field(description="Byte size recorded for the related artifact, retained snapshot, or inventory entry.", ge=0)


class ArtifactReproducibilityCanonicalBuildRecipeReport(BuildishContractModel):
    """Canonical build recipe declared by the verified source tree for one profile."""

    command: list[NonEmptyString] = Field(description="Literal argv list that Buildish executed or recommends for the related step.", default_factory=list)
    working_directory: NonEmptyString | None = Field(default=None, description="Repository-root-relative working directory that Buildish recorded in the related canonical recipe, effective execution, or local override block.")
    output_globs: list[NonEmptyString] = Field(description="Repository-root-relative glob patterns that identify expected outputs of the related build recipe.", default_factory=list)
    # Environment variable names only. Values are intentionally never recorded in
    # verification reports or inspection bundles so reproducibility output cannot
    # leak secrets or machine-local credentials.
    env_keys: list[NonEmptyString] = Field(description="Environment variable names referenced by the related recipe or override without exposing their values.", default_factory=list)


class ArtifactReproducibilityCanonicalRecipeReport(BuildishContractModel):
    """Canonical repo-defined recipe for one reproducibility profile."""

    build: ArtifactReproducibilityCanonicalBuildRecipeReport = Field(description="Nested build recipe or effective build execution block for one reproducibility contract.")


class ArtifactReproducibilityEffectiveBuildExecutionReport(BuildishContractModel):
    """Observed build invocation details for one executed reproducibility profile."""

    command: list[NonEmptyString] = Field(description="Literal argv list that Buildish executed or recommends for the related step.", default_factory=list)
    working_directory: NonEmptyString | None = Field(default=None, description="Repository-root-relative working directory that Buildish recorded in the related canonical recipe, effective execution, or local override block.")
    output_paths: list[NonEmptyString] = Field(description="Concrete output paths that Buildish observed from the effective rebuild execution.", default_factory=list)
    # Environment variable names only. Values are intentionally never recorded in
    # verification reports or inspection bundles so reproducibility output cannot
    # leak secrets or machine-local credentials.
    injected_environment_keys: list[NonEmptyString] = Field(description="Environment variable names that Buildish injected into the effective rebuild subprocess.", default_factory=list)


class ArtifactReproducibilityEffectiveExecutionReport(BuildishContractModel):
    """Effective execution details for one reproducibility run."""

    backend: Literal["host-direct"] = Field(default="host-direct", description="Execution backend name that performed the related Buildish action or reproducibility run.")
    build: ArtifactReproducibilityEffectiveBuildExecutionReport = Field(description="Nested build recipe or effective build execution block for one reproducibility contract.")


class ArtifactReproducibilityBuildOverrideReport(BuildishContractModel):
    """Sparse local override delta applied to one canonical build recipe."""

    command: list[NonEmptyString] | None = Field(default=None, description="Literal argv list that Buildish executed or recommends for the related step.")
    working_directory: NonEmptyString | None = Field(default=None, description="Repository-root-relative working directory that Buildish recorded in the related canonical recipe, effective execution, or local override block.")
    output_globs: list[NonEmptyString] | None = Field(default=None, description="Repository-root-relative glob patterns that identify expected outputs of the related build recipe.")
    # Environment variable names only. Values are intentionally never recorded in
    # verification reports or inspection bundles so reproducibility output cannot
    # leak secrets or machine-local credentials.
    env_keys: list[NonEmptyString] = Field(description="Environment variable names referenced by the related recipe or override without exposing their values.", default_factory=list)


class ArtifactReproducibilityOverrideReport(BuildishContractModel):
    """Structured local override metadata for one reproducibility run."""

    applied: bool = Field(default=False, description="Whether the related local override block was applied to the effective rebuild execution.")
    build: ArtifactReproducibilityBuildOverrideReport | None = Field(default=None, description="Nested build recipe or effective build execution block for one reproducibility contract.")


class ArtifactReproducibilityReport(BuildishContractModel):
    """Observed local rebuild comparison results for one artifact."""

    profile_id: NonEmptyString = Field(description="Reproducibility profile identifier selected for the related artifact or source verification.")
    verdict: VerificationVerdict = Field(description="Structured verification or reproducibility verdict for the related subject.")
    comparison_mode: NonEmptyString = Field(description="Declared reproducibility comparison mode used for the related artifact or profile.")
    canonical_recipe: ArtifactReproducibilityCanonicalRecipeReport | None = Field(default=None, description="Canonical rebuild recipe resolved from the verified source tree or other authoritative Buildish configuration.")
    effective_execution: ArtifactReproducibilityEffectiveExecutionReport | None = Field(default=None, description="Effective build execution details that Buildish actually ran after applying local overrides or runtime defaults.")
    override: ArtifactReproducibilityOverrideReport = Field(
        description="Explicit local reproducibility override details applied on top of the canonical recipe.",
        default_factory=ArtifactReproducibilityOverrideReport
    )
    matches_remote_bytes: bool | None = Field(default=None, description="Whether the rebuilt artifact bytes matched the staged or signed remote bytes exactly.")
    failure_class: NonEmptyString | None = Field(default=None, description="Structured failure classification that summarizes the main reason why verification or reproducibility failed.")
    archive_analysis: ShallowArchiveAnalysisReport | None = Field(default=None, description="Shallow top-level archive comparison details retained for reproducibility inspection.")
    evidence: list[InspectionEvidenceReference] = Field(description="Inspection-bundle evidence references retained for one reproducibility result.", default_factory=list)
    issues: list[str] = Field(description="Collected human-readable issues observed for the related verification, inspection, or reproducibility subject.", default_factory=list)


class FileLikeReproducibilityMetadata(BuildishContractModel):
    """Retained comparison metadata for one file-like reproducibility failure or drift."""

    artifact_id: NonEmptyString = Field(description="Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling.")
    kind: Literal[
        "generic-file",
        "generic-file-with-openpgp",
        "python-distribution",
        "npm-package",
    ] = Field(description="Declared artifact or report kind discriminator.")
    profile_id: NonEmptyString = Field(description="Reproducibility profile identifier selected for the related artifact or source verification.")
    comparison_mode: NonEmptyString = Field(description="Declared reproducibility comparison mode used for the related artifact or profile.")
    canonical_recipe: ArtifactReproducibilityCanonicalRecipeReport | None = Field(default=None, description="Canonical rebuild recipe resolved from the verified source tree or other authoritative Buildish configuration.")
    effective_execution: ArtifactReproducibilityEffectiveExecutionReport | None = Field(default=None, description="Effective build execution details that Buildish actually ran after applying local overrides or runtime defaults.")
    override: ArtifactReproducibilityOverrideReport = Field(
        description="Explicit local reproducibility override details applied on top of the canonical recipe.",
        default_factory=ArtifactReproducibilityOverrideReport
    )
    failure_class: NonEmptyString | None = Field(default=None, description="Structured failure classification that summarizes the main reason why verification or reproducibility failed.")
    archive_analysis: ShallowArchiveAnalysisReport | None = Field(default=None, description="Shallow top-level archive comparison details retained for reproducibility inspection.")
    staged_artifact: RetainedArtifactSnapshot = Field(description="Retained snapshot metadata for the staged artifact bytes used as the comparison target.")
    rebuilt_outputs: list[RebuiltOutputSnapshot] = Field(description="Snapshot metadata for files or trees produced by a local rebuild step.", default_factory=list)
    matches_remote_bytes: bool | None = Field(default=None, description="Whether the rebuilt artifact bytes matched the staged or signed remote bytes exactly.")
    issues: list[str] = Field(description="Collected human-readable issues observed for the related verification, inspection, or reproducibility subject.", default_factory=list)


class SourceArtifactReproducibilityMetadata(BuildishContractModel):
    """Retained comparison metadata for source-artifact reproducibility inspection."""

    profile_id: NonEmptyString = Field(description="Reproducibility profile identifier selected for the related artifact or source verification.")
    comparison_mode: NonEmptyString = Field(description="Declared reproducibility comparison mode used for the related artifact or profile.")
    failure_class: NonEmptyString | None = Field(default=None, description="Structured failure classification that summarizes the main reason why verification or reproducibility failed.")
    archive_analysis: ShallowArchiveAnalysisReport | None = Field(default=None, description="Shallow top-level archive comparison details retained for reproducibility inspection.")
    staged_artifact: RetainedArtifactSnapshot = Field(description="Retained snapshot metadata for the staged artifact bytes used as the comparison target.")
    rebuilt_artifact: RetainedArtifactSnapshot | None = Field(default=None, description="Retained snapshot metadata for one rebuilt artifact copy in the inspection bundle.")
    matches_remote_bytes: bool | None = Field(default=None, description="Whether the rebuilt artifact bytes matched the staged or signed remote bytes exactly.")
    issues: list[str] = Field(description="Collected human-readable issues observed for the related verification, inspection, or reproducibility subject.", default_factory=list)


MavenRepositoryPathMode = Literal[
    "exact-bytes",
    "zip-normalized",
    "content-only",
    "remote-only",
]
MavenRepositoryPathVerdict = Literal["verified", "failed", "skipped"]


class MavenRepositoryPathRuleReport(BuildishContractModel):
    """One regex-based Maven repository path rule retained for inspection."""

    pattern: NonEmptyString = Field(description="Regular-expression pattern used to match one family of repository paths.")
    mode: MavenRepositoryPathMode = Field(description="Comparison mode that the associated regex path rule applies to matching staged Maven repository paths.")


class MavenRepositoryPathResultReport(BuildishContractModel):
    """One comparable staged Maven repository path result retained for inspection."""

    path: NonEmptyString = Field(description="Filesystem path, relative artifact path, or retained evidence path associated with the related record.")
    mode: MavenRepositoryPathMode = Field(description="Comparison mode that Buildish applied when comparing this staged Maven repository path to the rebuilt local path.")
    verdict: MavenRepositoryPathVerdict = Field(description="Structured verification or reproducibility verdict for the related subject.")
    detail: NonEmptyString = Field(description="Human-readable comparison detail for one verification or reproducibility result entry.")
    raw_bytes_equal: bool | None = Field(default=None, description="Whether raw staged and rebuilt bytes matched before any archive-aware normalization.")
    normalized_match: bool | None = Field(default=None, description="Whether the staged and rebuilt repository path matched after applying the selected normalization mode.")
    staged_sha512: Sha512Hex | None = Field(default=None, description="SHA-512 digest computed from the staged repository entry or retained artifact bytes.")
    rebuilt_sha512: Sha512Hex | None = Field(default=None, description="SHA-512 digest computed from the rebuilt source or secondary artifact bytes.")


class MavenRepositoryReproducibilityMetadata(BuildishContractModel):
    """Retained comparison metadata for one Maven repository reproducibility run."""

    artifact_id: NonEmptyString = Field(description="Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling.")
    kind: Literal["maven-repository"] = Field(default="maven-repository", description="Declared artifact or report kind discriminator.")
    profile_id: NonEmptyString = Field(description="Reproducibility profile identifier selected for the related artifact or source verification.")
    comparison_mode: Literal["repository-tree"] = Field(default="repository-tree", description="Declared reproducibility comparison mode used for the related artifact or profile.")
    canonical_recipe: ArtifactReproducibilityCanonicalRecipeReport | None = Field(default=None, description="Canonical rebuild recipe resolved from the verified source tree or other authoritative Buildish configuration.")
    effective_execution: ArtifactReproducibilityEffectiveExecutionReport | None = Field(default=None, description="Effective build execution details that Buildish actually ran after applying local overrides or runtime defaults.")
    override: ArtifactReproducibilityOverrideReport = Field(
        description="Explicit local reproducibility override details applied on top of the canonical recipe.",
        default_factory=ArtifactReproducibilityOverrideReport
    )
    repository_dir: NonEmptyString | None = Field(default=None, description="Repository-root-relative rebuild output directory that should contain the local Maven repository tree.")
    require_signatures: bool = Field(default=False, description="Whether Maven repository reproducibility should require detached signature files to exist and compare successfully.")
    path_rules: list[MavenRepositoryPathRuleReport] = Field(description="Regex-based per-path comparison rules that specialize the default Maven repository comparison behavior.", default_factory=list)
    matches_remote_bytes: bool | None = Field(default=None, description="Whether the rebuilt artifact bytes matched the staged or signed remote bytes exactly.")
    failure_class: NonEmptyString | None = Field(default=None, description="Structured failure classification that summarizes the main reason why verification or reproducibility failed.")
    verified_path_count: int | None = Field(description="Number of Maven repository paths that Buildish compared locally under the active repository-tree policy.", default=None, ge=0)
    failed_path_count: int | None = Field(description="Number of Maven repository paths whose reproducibility comparison ended in a failure state.", default=None, ge=0)
    skipped_path_count: int | None = Field(description="Number of Maven repository paths that Buildish skipped from local comparison because policy marked them remote-only.", default=None, ge=0)
    path_results: list[MavenRepositoryPathResultReport] = Field(description="Per-path Maven repository reproducibility results retained for later inspection or reporting.", default_factory=list)
    issues: list[str] = Field(description="Collected human-readable issues observed for the related verification, inspection, or reproducibility subject.", default_factory=list)


class OciImageReproducibilityMetadata(BuildishContractModel):
    """Retained comparison metadata for one OCI image reproducibility run."""

    artifact_id: NonEmptyString = Field(description="Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling.")
    kind: Literal["oci-image"] = Field(default="oci-image", description="Declared artifact or report kind discriminator.")
    profile_id: NonEmptyString = Field(description="Reproducibility profile identifier selected for the related artifact or source verification.")
    comparison_mode: Literal["platform-digest", "provenance-only"] = Field(description="Declared reproducibility comparison mode used for the related artifact or profile.")
    canonical_recipe: ArtifactReproducibilityCanonicalRecipeReport | None = Field(default=None, description="Canonical rebuild recipe resolved from the verified source tree or other authoritative Buildish configuration.")
    effective_execution: ArtifactReproducibilityEffectiveExecutionReport | None = Field(default=None, description="Effective build execution details that Buildish actually ran after applying local overrides or runtime defaults.")
    override: ArtifactReproducibilityOverrideReport = Field(
        description="Explicit local reproducibility override details applied on top of the canonical recipe.",
        default_factory=ArtifactReproducibilityOverrideReport
    )
    image_ref: NonEmptyString | None = Field(default=None, description="Fully qualified OCI image reference used for inspection or local rebuild comparison.")
    declared_digest: OciContentDigest = Field(description="Signed or declared digest that the rebuilt value is compared against.")
    expected_platform_digests: list[OciPlatformDigest] = Field(description="Platform-specific OCI digests that the reproducibility check expected to reproduce for the rebuilt image.", default_factory=list)
    rebuilt_digest: OciContentDigest | None = Field(default=None, description="Digest produced by rebuilding the related OCI image locally.")
    rebuilt_platform_digests: list[OciPlatformDigest] = Field(description="Platform digests produced by rebuilding the related multi-platform OCI image.", default_factory=list)
    matches_remote_bytes: bool | None = Field(default=None, description="Whether the rebuilt artifact bytes matched the staged or signed remote bytes exactly.")
    failure_class: NonEmptyString | None = Field(default=None, description="Structured failure classification that summarizes the main reason why verification or reproducibility failed.")
    issues: list[str] = Field(description="Collected human-readable issues observed for the related verification, inspection, or reproducibility subject.", default_factory=list)


class GenericFileVerificationReport(BuildishContractModel):
    """Verification report for one generic secondary file."""

    artifact_id: NonEmptyString = Field(description="Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling.")
    kind: Literal["generic-file", "generic-file-with-openpgp"] = Field(description="Declared artifact or report kind discriminator.")
    verdict: VerificationVerdict = Field(description="Structured verification or reproducibility verdict for the related subject.")
    issues: list[str] = Field(description="Collected human-readable issues observed for the related verification, inspection, or reproducibility subject.", default_factory=list)
    filename: NonEmptyString = Field(description="Artifact filename as seen in staging, manifests, or retained evidence.")
    uri: NonEmptyString = Field(description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")
    checksum: ChecksumVerificationReport = Field(description="Checksum verification details for one downloaded or rebuilt artifact.")
    signatures: list[SignatureVerificationPayload] = Field(description="Declared detached signature references associated with the related artifact or manifest.", default_factory=list)
    inventory: InventoryVerificationReport | None = Field(default=None, description="Signed inventory or supplemental staging metadata associated with the related artifact.")
    reproducibility: ArtifactReproducibilityReport | None = Field(default=None, description="Reproducibility policy or result block associated with the related source or secondary artifact.")


class MavenRepositoryVerificationReport(BuildishContractModel):
    """Verification report for one staged Maven repository."""

    artifact_id: NonEmptyString = Field(description="Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling.")
    kind: Literal["maven-repository"] = Field(default="maven-repository", description="Declared artifact or report kind discriminator.")
    verdict: VerificationVerdict = Field(description="Structured verification or reproducibility verdict for the related subject.")
    issues: list[str] = Field(description="Collected human-readable issues observed for the related verification, inspection, or reproducibility subject.", default_factory=list)
    staging_repository_id: NonEmptyString = Field(description="Repository identifier of the staged Maven repository under verification.")
    base_url: NonEmptyString = Field(description="Base URL used to discover or publish the related artifact or service resource.")
    inventory: InventoryVerificationReport | None = Field(default=None, description="Signed inventory or supplemental staging metadata associated with the related artifact.")
    live_repository: LiveMavenRepositoryReport = Field(description="Live staged Maven repository verification details collected alongside the signed inventory checks.")
    reproducibility: ArtifactReproducibilityReport | None = Field(default=None, description="Reproducibility policy or result block associated with the related source or secondary artifact.")


class PythonDistributionVerificationReport(BuildishContractModel):
    """Verification report for one Python distribution."""

    artifact_id: NonEmptyString = Field(description="Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling.")
    kind: Literal["python-distribution"] = Field(default="python-distribution", description="Declared artifact or report kind discriminator.")
    verdict: VerificationVerdict = Field(description="Structured verification or reproducibility verdict for the related subject.")
    issues: list[str] = Field(description="Collected human-readable issues observed for the related verification, inspection, or reproducibility subject.", default_factory=list)
    filename: NonEmptyString = Field(description="Artifact filename as seen in staging, manifests, or retained evidence.")
    uri: NonEmptyString = Field(description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")
    index_url: NonEmptyString = Field(description="Base Python simple-index URL that Buildish used for package verification.")
    project_name: NonEmptyString = Field(description="Python package project name associated with the related distribution artifact.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    checksum: ChecksumVerificationReport = Field(description="Checksum verification details for one downloaded or rebuilt artifact.")
    index_resolution: PythonIndexResolutionReport = Field(description="Python package-index resolution details collected while locating the staged distribution artifact.")
    reproducibility: ArtifactReproducibilityReport | None = Field(default=None, description="Reproducibility policy or result block associated with the related source or secondary artifact.")


class OciImageVerificationReport(BuildishContractModel):
    """Verification report for one OCI image."""

    artifact_id: NonEmptyString = Field(description="Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling.")
    kind: Literal["oci-image"] = Field(default="oci-image", description="Declared artifact or report kind discriminator.")
    verdict: VerificationVerdict = Field(description="Structured verification or reproducibility verdict for the related subject.")
    issues: list[str] = Field(description="Collected human-readable issues observed for the related verification, inspection, or reproducibility subject.", default_factory=list)
    uri: NonEmptyString = Field(description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")
    registry: NonEmptyString = Field(description="Container registry host or namespace that serves the related OCI image.")
    repository: NonEmptyString = Field(description="Repository identifier or repository name associated with the related provenance or external-auth record.")
    digest: OciContentDigest = Field(description="OCI content digest or similar immutable digest string for the related artifact.")
    inspection: OciInspectionReport = Field(description="Live inspection result block for the related artifact or platform resource.")
    reproducibility: ArtifactReproducibilityReport | None = Field(default=None, description="Reproducibility policy or result block associated with the related source or secondary artifact.")


class NpmPackageVerificationReport(BuildishContractModel):
    """Verification report for one npm package."""

    artifact_id: NonEmptyString = Field(description="Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling.")
    kind: Literal["npm-package"] = Field(default="npm-package", description="Declared artifact or report kind discriminator.")
    verdict: VerificationVerdict = Field(description="Structured verification or reproducibility verdict for the related subject.")
    issues: list[str] = Field(description="Collected human-readable issues observed for the related verification, inspection, or reproducibility subject.", default_factory=list)
    filename: NonEmptyString = Field(description="Artifact filename as seen in staging, manifests, or retained evidence.")
    uri: NonEmptyString = Field(description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")
    registry_url: NonEmptyString = Field(description="Registry metadata URL used for npm package verification.")
    package_name: NonEmptyString = Field(description="Normalized npm package name associated with the related package artifact or registry lookup.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    integrity: IntegrityVerificationReport = Field(description="Integrity verification details derived from registry metadata or sidecar checksums.")
    checksum: ChecksumVerificationReport = Field(description="Checksum verification details for one downloaded or rebuilt artifact.")
    registry_resolution: NpmRegistryResolutionReport = Field(description="Registry-resolution details collected while verifying the related npm package tarball.")
    reproducibility: ArtifactReproducibilityReport | None = Field(default=None, description="Reproducibility policy or result block associated with the related source or secondary artifact.")


class InvalidSecondaryArtifactVerificationReport(BuildishContractModel):
    """Failure record used when one secondary artifact entry is malformed."""

    artifact_id: NonEmptyString = Field(description="Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling.")
    kind: Literal["_invalid-secondary-artifact-entry"] = Field(default="_invalid-secondary-artifact-entry", description="Declared artifact or report kind discriminator.")
    declared_kind: str | None = Field(default=None, description="Artifact kind string declared by the malformed secondary-artifact entry that verify-rc could not process normally.")
    verdict: Literal["failed"] = Field(default="failed", description="Structured verification or reproducibility verdict for the related subject.")
    issues: list[str] = Field(description="Collected human-readable issues observed for the related verification, inspection, or reproducibility subject.", default_factory=list)


AnySecondaryArtifactVerification = Annotated[
    GenericFileVerificationReport
    | MavenRepositoryVerificationReport
    | PythonDistributionVerificationReport
    | OciImageVerificationReport
    | NpmPackageVerificationReport
    | InvalidSecondaryArtifactVerificationReport,
    Field(discriminator="kind"),
]
SecondaryArtifactVerificationAdapter: TypeAdapter[AnySecondaryArtifactVerification] = TypeAdapter(
    AnySecondaryArtifactVerification
)


class ManifestVerificationSection(BuildishContractModel):
    """Manifest-authenticity and tag-binding section of the verify-rc report."""

    verdict: VerificationVerdict = Field(description="Structured verification or reproducibility verdict for the related subject.")
    sha512: str | None = Field(default=None, description="SHA-512 checksum payload associated with the related artifact.")
    keys_url_matches_manifest: bool = Field(description="Whether the verified KEYS URL matched the authoritative manifest's own recorded KEYS URL.")
    keys_url_matches_component_config: bool | None = Field(default=None, description="Whether the manifest's KEYS URL matched the current component configuration.")
    signature: SignatureVerificationPayload | None = Field(default=None, description="Signature verification details for the related artifact or manifest.")
    rc_tag_target_commit: str | None = Field(default=None, description="Git commit SHA that the RC tag resolved to during verification or publication.")
    rc_tag_matches_source_commit_sha: bool = Field(description="Whether the RC tag resolved to the same commit SHA that the manifest recorded as the authoritative source commit.")
    issues: list[str] = Field(description="Collected human-readable issues observed for the related verification, inspection, or reproducibility subject.", default_factory=list)


class SourceArtifactVerificationSection(BuildishContractModel):
    """Source-artifact verification section of the verify-rc report."""

    verdict: VerificationVerdict = Field(description="Structured verification or reproducibility verdict for the related subject.")
    filename: str | None = Field(default=None, description="Artifact filename as seen in staging, manifests, or retained evidence.")
    uri: str | None = Field(default=None, description="Canonical artifact or signature URI recorded in a Buildish manifest or verification report.")
    sha512: str | None = Field(default=None, description="SHA-512 checksum payload associated with the related artifact.")
    sha512_sidecar_verified: bool = Field(description="Whether the staged source-artifact `.sha512` sidecar was fetched and verified successfully.")
    signature: SignatureVerificationPayload | None = Field(default=None, description="Signature verification details for the related artifact or manifest.")
    rebuilt_sha512: str | None = Field(default=None, description="SHA-512 digest computed from the rebuilt source or secondary artifact bytes.")
    matches_source_commit_sha: bool = Field(description="Whether the rebuilt source artifact bytes matched the source commit selected by the authoritative manifest.")
    reproducibility: ArtifactReproducibilityReport | None = Field(default=None, description="Reproducibility policy or result block associated with the related source or secondary artifact.")
    issues: list[str] = Field(description="Collected human-readable issues observed for the related verification, inspection, or reproducibility subject.", default_factory=list)


class ReproducibilityExecutionSection(BuildishContractModel):
    """Run-level policy and execution summary for build-based reproducibility checks."""

    requested_mode: Literal["auto", "integrity-only", "full"] = Field(description="Verify-rc mode explicitly requested by the caller.")
    effective_mode: Literal["integrity-only", "full"] = Field(description="Verify mode that Buildish actually executed after evaluating prompts, runtime policy, and caller intent.")
    build_checks_attempted: bool = Field(description="Whether the command attempted local reproducibility or rebuild checks during this run.")
    execution_backend: Literal["none", "host-direct"] = Field(default="none", description="Execution backend that verify-rc used for the recorded reproducibility run.")
    inherits_host_home: bool | None = Field(default=None, description="Whether the reproducibility execution inherited the caller's existing `HOME` rather than using an isolated home directory.")
    prompt_used: bool = Field(default=False, description="Whether Buildish prompted before enabling the recorded reproducibility execution mode.")
    prompt_confirmed: bool | None = Field(default=None, description="Whether the caller confirmed a prompt before Buildish escalated from integrity-only verification to full local rebuild checks.")
    skipped_reason: str | None = Field(default=None, description="Reason why Buildish skipped local rebuild execution after evaluating the requested verify mode and runtime constraints.")


class InspectionBundleSection(BuildishContractModel):
    """Location of the curated reproducibility-inspection bundle for one verify-rc run."""

    relative_path_from_report: NonEmptyString = Field(description="Path from the verify-rc report directory to the retained inspection bundle directory.")
    bundle_schema_version: SchemaVersionV1 | None = Field(default=None, description="Supported schema version of the retained inspection-bundle manifest that inspect-repro consumed.")
    manifest_relative_path: NonEmptyString | None = Field(default=None, description="Bundle-relative path to the top-level inspection bundle manifest file.")


class InspectionBundleArtifactEntry(BuildishContractModel):
    """One artifact-specific metadata document retained inside an inspection bundle."""

    artifact_id: NonEmptyString = Field(description="Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling.")
    kind: NonEmptyString = Field(description="Declared artifact or report kind discriminator.")
    metadata_path: NonEmptyString = Field(description="Bundle-relative path to the metadata file for one retained inspection target.")


class InspectionBundleManifestV1(BuildishContractModel):
    """Top-level contract manifest for one curated verify-rc inspection bundle."""

    schema_version: SchemaVersionV1 = Field(default="1", description="Schema version of the enclosing Buildish JSON or YAML contract.")
    bundle_type: Literal["verify-rc-inspection"] = Field(default="verify-rc-inspection", description="Stable inspection-bundle manifest discriminator.")
    report_type: Literal["verify-rc"] = Field(default="verify-rc", description="Stable report discriminator for one Buildish JSON report contract.")
    report_schema_version: SchemaVersionV1 = Field(default="1", description="Supported schema version of the related Buildish report payload.")
    component_id: str | None = Field(default=None, description="Stable component identifier used across Buildish manifests, reports, and release-state records.")
    version: str | None = Field(default=None, description="Release version string without a leading `v` prefix.")
    rc_tag: str | None = Field(default=None, description="Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix.")
    artifacts: list[InspectionBundleArtifactEntry] = Field(description="Artifact entries retained in the related inspection bundle manifest.", default_factory=list)


class InspectReproCountSummary(BuildishContractModel):
    """One count bucket emitted by inspect-repro machine-readable summaries."""

    key: NonEmptyString = Field(description="Stable grouping or category key used in one Buildish summary object.")
    count: int = Field(description="Count value reported for one grouped summary bucket.", ge=0)


class InspectReproSummaryV1(BuildishContractModel):
    """Top-level summary block for machine-readable inspect-repro output."""

    failure_count: int = Field(description="Total number of failing source or secondary reproducibility targets selected for inspect-repro output.", ge=0)
    source_failure_count: int = Field(description="Number of failing source-artifact reproducibility targets selected for inspect-repro output.", ge=0)
    secondary_failure_count: int = Field(description="Number of failing secondary-artifact reproducibility targets selected for inspect-repro output.", ge=0)
    failure_kinds: list[InspectReproCountSummary] = Field(description="Count summary grouped by artifact kind across all selected inspect-repro targets.", default_factory=list)
    failure_classes: list[InspectReproCountSummary] = Field(description="Count summary grouped by failure-class identifier across all selected inspect-repro targets.", default_factory=list)
    failure_groups: list[InspectReproCountSummary] = Field(description="Count summary grouped by high-level inspect-repro failure group.", default_factory=list)


class InspectReproTargetV1(BuildishContractModel):
    """One selected reproducibility failure reported by inspect-repro JSON mode."""

    section_label: NonEmptyString = Field(description="Human-facing section label that groups related inspect-repro targets.")
    artifact_id: NonEmptyString = Field(description="Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling.")
    kind: NonEmptyString = Field(description="Declared artifact or report kind discriminator.")
    failure_class: NonEmptyString | None = Field(default=None, description="Structured failure classification that summarizes the main reason why verification or reproducibility failed.")
    failure_group: NonEmptyString = Field(description="Higher-level grouping bucket that inspect-repro assigned to the target, such as source-artifact or secondary artifact family.")
    profile_id: NonEmptyString = Field(description="Reproducibility profile identifier selected for the related artifact or source verification.")
    comparison_mode: NonEmptyString = Field(description="Declared reproducibility comparison mode used for the related artifact or profile.")
    recipe_source: Literal["verifier-internal", "canonical-profile", "local-override"] = Field(description="Origin of the reproducibility recipe used for this target, such as verifier-internal logic, the canonical profile, or a local override.")
    execution_backend: NonEmptyString | None = Field(default=None, description="Execution backend that verify-rc used for the recorded reproducibility run.")
    build_command: list[NonEmptyString] = Field(description="Literal argv list that inspect-repro or verify-rc recorded as the effective build command for this target.", default_factory=list)
    build_working_directory: NonEmptyString | None = Field(default=None, description="Repository-root-relative working directory that inspect-repro or verify-rc recorded for the effective build command.")
    injected_environment_keys: list[NonEmptyString] = Field(description="Environment variable names that Buildish injected into the effective rebuild subprocess.", default_factory=list)
    evidence_labels: list[NonEmptyString] = Field(description="Short labels naming the retained evidence files that inspect-repro associated with this target.", default_factory=list)
    evidence: list[InspectionEvidenceReference] = Field(description="Inspection-bundle evidence references retained for one reproducibility result.", default_factory=list)
    override_fields: list[NonEmptyString] = Field(description="Sparse list of build-recipe fields that a local reproducibility override changed for this target.", default_factory=list)


class InspectReproReportV1(BuildishContractModel):
    """Machine-readable inspect-repro output for automation and post-processing."""

    schema_version: SchemaVersionV1 = Field(default="1", description="Schema version of the enclosing Buildish JSON or YAML contract.")
    report_type: Literal["inspect-repro"] = Field(default="inspect-repro", description="Stable report discriminator for one Buildish JSON report contract.")
    verify_rc_report_schema_version: SchemaVersionV1 = Field(description="Schema version of the verify-rc JSON report that inspect-repro read before generating its own output.")
    bundle_schema_version: SchemaVersionV1 | None = Field(default=None, description="Supported schema version of the retained inspection-bundle manifest that inspect-repro consumed.")
    component_id: str | None = Field(default=None, description="Stable component identifier used across Buildish manifests, reports, and release-state records.")
    rc_tag: str | None = Field(default=None, description="Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix.")
    verify_rc_verdict: VerificationVerdict = Field(description="Final verify-rc verdict that inspect-repro observed in the input verification report.")
    build_checks_attempted: bool = Field(description="Whether the command attempted local reproducibility or rebuild checks during this run.")
    report_json_path: NonEmptyString = Field(description="Filesystem path of the verify-rc JSON report consumed by inspect-repro.")
    inspection_bundle_path: NonEmptyString = Field(description="Filesystem path of the retained inspection bundle directory.")
    selected_artifact_ids: list[NonEmptyString] = Field(description="Artifact ids that inspect-repro selected for detailed output.", default_factory=list)
    selected_failure_classes: list[NonEmptyString] = Field(description="Failure-class filters that inspect-repro applied when selecting targets.", default_factory=list)
    summary_only: bool = Field(default=False, description="Whether inspect-repro emitted only grouped summaries rather than full per-target detail sections.")
    summary: InspectReproSummaryV1 = Field(description="Human-readable short summary for the related result or mocked tool behavior.")
    targets: list[InspectReproTargetV1] = Field(description="Selected inspect-repro target entries that Buildish included in the machine-readable report.", default_factory=list)


class VerifyRcReportV1(BuildishContractModel):
    """Machine-readable Phase 1a RC verification report."""

    schema_version: SchemaVersionV1 = Field(default="1", description="Schema version of the enclosing Buildish JSON or YAML contract.")
    report_type: Literal["verify-rc"] = Field(default="verify-rc", description="Stable report discriminator for one Buildish JSON report contract.")
    component_id: str | None = Field(default=None, description="Stable component identifier used across Buildish manifests, reports, and release-state records.")
    version: str | None = Field(default=None, description="Release version string without a leading `v` prefix.")
    rc_tag: str | None = Field(default=None, description="Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix.")
    source_commit_sha: str | None = Field(default=None, description="Resolved source Git commit SHA recorded in the authoritative RC manifest or verify-rc report.")
    source_date_epoch: int | None = Field(description="Canonical `SOURCE_DATE_EPOCH` integer carried through RC production and verification.", default=None, ge=0)
    source_repository_url: str | None = Field(default=None, description="Canonical source repository URL recorded in the RC vote manifest or verification report.")
    manifest_url: NonEmptyString = Field(description="URL of the RC vote manifest that Buildish fetched or verified.")
    keys_url: NonEmptyString = Field(description="ASF KEYS URL that Buildish used or expected while establishing the RC trust roots.")
    verdict: VerificationVerdict = Field(description="Structured verification or reproducibility verdict for the related subject.")
    work_dir: NonEmptyString = Field(description="Filesystem path of the verify-rc working directory where retained reports, logs, and downloaded artifacts were stored.")
    failures: list[VerificationFailurePayload] = Field(description="Collected verification failures that caused the enclosing report verdict to fail.", default_factory=list)
    manifest_verification: ManifestVerificationSection = Field(description="Manifest trust-chain verification section of the verify-rc report.")
    source_artifact_verification: SourceArtifactVerificationSection = Field(description="Source-artifact verification section of the verify-rc report.")
    reproducibility_execution: ReproducibilityExecutionSection = Field(description="Run-level reproducibility execution policy and outcome block retained in the verify-rc report.")
    inspection_bundle: InspectionBundleSection | None = Field(default=None, description="Inspection-bundle location block retained in the verify-rc report for later inspect-repro analysis.")
    secondary_artifact_verifications: list[AnySecondaryArtifactVerification] = Field(description="Per-artifact verification sections for all secondary artifacts processed during verify-rc.", default_factory=list)


SecondaryArtifactBase.schema_export = SchemaExportSpecification(
    audience="internal",
    stability="stable",
    summary="Common base shape shared across supported secondary-artifact manifest entries.",
)
SecondaryArtifactManifestV1.schema_export = SchemaExportSpecification(
    audience="internal",
    stability="stable",
    file_path="artifact-manifest.json",
    summary="Typed secondary-artifact registration manifest fragment written by `record-artifact`.",
)
AsfKeysTrustRootRead.schema_export = SchemaExportSpecification(
    audience="internal",
    stability="stable",
    summary="Tolerant read model for ASF KEYS trust-root references carried through vote-materials loading.",
)
DraftGithubReleaseRead.schema_export = SchemaExportSpecification(
    audience="internal",
    stability="stable",
    summary="Tolerant read model for draft GitHub release coordinates recorded in vote materials.",
)
VoteMaterialsStrict.schema_export = SchemaExportSpecification(
    audience="internal",
    stability="stable",
    summary="Strict typed vote-materials bundle assembled by release-tooling before RC publication.",
)
VoteMaterialsRead.schema_export = SchemaExportSpecification(
    audience="internal",
    stability="stable",
    summary="Tolerant read model for vote materials consumed during verification and bootstrap workflows.",
)
AuthoritativeManifestReferenceRead.schema_export = SchemaExportSpecification(
    audience="internal",
    stability="stable",
    summary="Tolerant read model for the authoritative signed manifest reference used by vote-materials loading.",
)
RcVoteManifestV1.schema_export = SchemaExportSpecification(
    file_path="rc-vote-manifest.json",
    summary="Signed RC vote manifest that declares the source artifact, trust roots, and secondary artifacts that verifiers must inspect.",
)
MavenRepositoryInventoryV1.schema_export = SchemaExportSpecification(
    audience="internal",
    stability="stable",
    summary="Signed Maven repository inventory contract emitted for staged Maven repository verification.",
)
RetainedArtifactSnapshot.schema_export = SchemaExportSpecification(
    audience="internal",
    stability="stable",
    summary="Snapshot of one retained staged or rebuilt artifact captured in reproducibility metadata.",
)
RebuiltOutputSnapshot.schema_export = SchemaExportSpecification(
    audience="internal",
    stability="stable",
    summary="Snapshot of one rebuilt output retained in reproducibility metadata.",
)
FileLikeReproducibilityMetadata.schema_export = SchemaExportSpecification(
    audience="internal",
    stability="stable",
    summary="Inspection-bundle metadata payload for file-like reproducibility comparisons.",
)
SourceArtifactReproducibilityMetadata.schema_export = SchemaExportSpecification(
    audience="internal",
    stability="stable",
    summary="Inspection-bundle metadata payload for source-artifact reproducibility evidence.",
)
MavenRepositoryPathRuleReport.schema_export = SchemaExportSpecification(
    audience="internal",
    stability="stable",
    summary="Rendered Maven repository per-path comparison rule retained in reproducibility metadata.",
)
MavenRepositoryPathResultReport.schema_export = SchemaExportSpecification(
    audience="internal",
    stability="stable",
    summary="Per-path Maven repository reproducibility comparison result retained in bundle metadata.",
)
MavenRepositoryReproducibilityMetadata.schema_export = SchemaExportSpecification(
    audience="internal",
    stability="stable",
    summary="Inspection-bundle metadata payload for Maven repository reproducibility evidence.",
)
OciImageReproducibilityMetadata.schema_export = SchemaExportSpecification(
    audience="internal",
    stability="stable",
    summary="Inspection-bundle metadata payload for OCI image reproducibility evidence.",
)
InspectionBundleManifestV1.schema_export = SchemaExportSpecification(
    file_path="inspection-bundle.json",
    summary="Top-level manifest for a retained verify-rc inspection bundle.",
)
InspectReproReportV1.schema_export = SchemaExportSpecification(
    summary="Machine-readable `inspect-repro --json` output contract.",
)
VerifyRcReportV1.schema_export = SchemaExportSpecification(
    summary="Machine-readable `verify-rc` report contract, typically written through `--report-json`.",
)


__all__ = [
    "AnySecondaryArtifact",
    "AnySecondaryArtifactVerification",
    "BuildishContractModel",
    "DraftGithubRelease",
    "ArtifactReproducibilityReport",
    "GenericFileSecondaryArtifact",
    "GenericFileVerificationReport",
    "FileLikeReproducibilityMetadata",
    "GenericFileWithOpenPgpSecondaryArtifact",
    "GithubWorkflowProvenance",
    "InvalidSecondaryArtifactVerificationReport",
    "InspectReproCountSummary",
    "InspectReproReportV1",
    "InspectReproSummaryV1",
    "InspectReproTargetV1",
    "InspectionBundleSection",
    "InspectionBundleArtifactEntry",
    "InspectionBundleManifestV1",
    "InspectionEvidenceReference",
    "MavenRepositoryPathResultReport",
    "MavenRepositoryReproducibilityMetadata",
    "MavenRepositoryInventoryV1",
    "MavenRepositorySecondaryArtifact",
    "MavenRepositoryVerificationReport",
    "NpmPackageSecondaryArtifact",
    "NpmPackageVerificationReport",
    "OciImageSecondaryArtifact",
    "OciImageReproducibilityMetadata",
    "OciImageVerificationReport",
    "PythonDistributionSecondaryArtifact",
    "PythonDistributionVerificationReport",
    "RcVoteManifestReadV1",
    "RcVoteManifestV1",
    "RetainedArtifactSnapshot",
    "RebuiltOutputSnapshot",
    "SecondaryArtifactVerificationAdapter",
    "SecondaryArtifactManifestV1",
    "ShallowArchiveAnalysisReport",
    "SourceArtifactReproducibilityMetadata",
    "StrictSecondaryArtifactAdapter",
    "SupplementalInventoryReference",
    "ReproducibilityExecutionSection",
    "VerifyRcReportV1",
]
