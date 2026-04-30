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

from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints, TypeAdapter, field_validator, model_validator
from pydantic.functional_validators import AfterValidator

from apache_buildish_release_tooling.contracts import BuildishContractModel

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

    type: Literal["openpgp-detached-ascii-armored"] = "openpgp-detached-ascii-armored"
    uri: NonEmptyString


class ReproducibilitySelector(BuildishContractModel):
    """Signed manifest selector for one canonical local reproducibility profile."""

    profile_id: NonEmptyString


class SignatureVerificationPayload(BuildishContractModel):
    """Serialized detached-signature verification details."""

    signer_fingerprint: NonEmptyString
    signer_user_id: str | None = None
    trust_label: str | None = None
    key_algorithm: str | None = None
    key_size_bits: int | None = Field(default=None, ge=0)


class VerificationFailurePayload(BuildishContractModel):
    """One collected verification failure."""

    scope: NonEmptyString
    subject: NonEmptyString
    message: NonEmptyString


class Sha256ChecksumPayload(BuildishContractModel):
    """One sha256 checksum value and optional detached sidecar URI."""

    value: Sha256Hex
    uri: NonEmptyString | None = None


class Sha512ChecksumPayload(BuildishContractModel):
    """One sha512 checksum value and optional detached sidecar URI."""

    value: Sha512Hex
    uri: NonEmptyString | None = None


class Sha256Checksums(BuildishContractModel):
    """A checksum block containing one sha256 entry."""

    sha256: Sha256ChecksumPayload


class Sha512Checksums(BuildishContractModel):
    """A checksum block containing one sha512 entry."""

    sha512: Sha512ChecksumPayload


class NpmChecksums(BuildishContractModel):
    """A checksum block for npm artifacts, which may use sha256 or sha512."""

    sha256: Sha256ChecksumPayload | None = None
    sha512: Sha512ChecksumPayload | None = None

    @model_validator(mode="after")
    def validate_exactly_one_algorithm(self) -> NpmChecksums:
        algorithms = [payload for payload in (self.sha256, self.sha512) if payload is not None]
        if len(algorithms) != 1:
            raise ValueError("npm-package checksums must declare exactly one of sha256 or sha512")
        return self


class SupplementalInventoryReference(BuildishContractModel):
    """One staged supplemental inventory attachment."""

    filename: NonEmptyString
    sha512: Sha512Hex
    uri: NonEmptyString | None = None
    entry_count: int | None = Field(default=None, ge=0)
    total_size_bytes: int | None = Field(default=None, ge=0)


class NpmProvenanceAuth(BuildishContractModel):
    """Explicit npm provenance metadata."""

    scheme: Literal["npm-provenance"] = "npm-provenance"
    repository: NonEmptyString


class PyPiAttestationAuth(BuildishContractModel):
    """Explicit PyPI attestation metadata."""

    scheme: Literal["pypi-attestation"] = "pypi-attestation"
    repository: NonEmptyString


class OciPlatformDigest(BuildishContractModel):
    """One platform-specific digest declared for an OCI image."""

    platform: NonEmptyString
    digest: OciContentDigest


class SecondaryArtifactBase(BuildishContractModel):
    """Common fields shared across supported secondary artifact kinds."""

    artifact_id: NonEmptyString
    kind: str
    role: NonEmptyString | None = None
    artifact_origin: NonEmptyString | None = None
    git_commit_sha: GitCommitSha | None = None
    reproducibility: ReproducibilitySelector | None = None
    inventory: SupplementalInventoryReference | None = None


class GenericFileSecondaryArtifact(SecondaryArtifactBase):
    """A standalone file artifact tracked in the signed vote manifest."""

    kind: Literal["generic-file"] = "generic-file"
    filename: NonEmptyString
    uri: NonEmptyString
    checksums: Sha512Checksums
    signatures: list[SignatureReference] = Field(default_factory=list)


class GenericFileWithOpenPgpSecondaryArtifact(SecondaryArtifactBase):
    """A standalone file artifact that requires at least one detached signature."""

    kind: Literal["generic-file-with-openpgp"] = "generic-file-with-openpgp"
    filename: NonEmptyString
    uri: NonEmptyString
    checksums: Sha512Checksums
    signatures: list[SignatureReference] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_signature_presence(self) -> GenericFileWithOpenPgpSecondaryArtifact:
        if not self.signatures:
            raise ValueError("generic-file-with-openpgp requires at least one detached signature")
        return self


class MavenRepositorySecondaryArtifact(SecondaryArtifactBase):
    """A staged Maven repository validated through a signed inventory."""

    kind: Literal["maven-repository"] = "maven-repository"
    staging_repository_id: NonEmptyString
    base_url: NonEmptyString
    inventory: SupplementalInventoryReference


class NpmPackageSecondaryArtifact(SecondaryArtifactBase):
    """A published npm package tarball."""

    kind: Literal["npm-package"] = "npm-package"
    filename: NonEmptyString
    uri: NonEmptyString
    registry_url: NonEmptyString
    package_name: NonEmptyString
    version: NonEmptyString
    integrity: NonEmptyString
    checksums: NpmChecksums
    authenticity: NpmProvenanceAuth | None = None


class OciImageSecondaryArtifact(SecondaryArtifactBase):
    """An immutable OCI image reference."""

    kind: Literal["oci-image"] = "oci-image"
    uri: NonEmptyString
    registry: NonEmptyString
    repository: NonEmptyString
    digest: OciContentDigest
    platform_digests: list[OciPlatformDigest] | None = None

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

    kind: Literal["python-distribution"] = "python-distribution"
    filename: NonEmptyString
    uri: NonEmptyString
    index_url: NonEmptyString
    project_name: NonEmptyString
    version: NonEmptyString
    checksums: Sha256Checksums
    authenticity: PyPiAttestationAuth | None = None


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

    secondary_artifacts: list[AnySecondaryArtifact]


class ToolingProvenance(BuildishContractModel):
    """Tooling repository provenance embedded in emitted manifests."""

    repository: NonEmptyString
    repository_url: NonEmptyString
    git_commit_sha: GitCommitSha
    git_ref: NonEmptyString | None = None
    version: NonEmptyString | None = None


class GithubWorkflowProvenance(BuildishContractModel):
    """GitHub Actions provenance embedded in emitted manifests."""

    repository: NonEmptyString
    workflow: str
    workflow_ref: str
    run_id: int = Field(ge=0)
    run_attempt: int | None = Field(default=None, ge=0)
    run_url: NonEmptyString | None = None


class ManifestProvenance(BuildishContractModel):
    """Top-level provenance block for the RC vote manifest."""

    created_at: NonEmptyString
    tooling: ToolingProvenance
    github: GithubWorkflowProvenance | None = None


class AsfKeysTrustRoot(BuildishContractModel):
    """Pinned ASF KEYS metadata used as a trust root."""

    uri: NonEmptyString
    known_length_bytes: int = Field(ge=0)
    known_prefix_sha512: Sha512Hex


class ManifestTrustRoots(BuildishContractModel):
    """Trust roots referenced by the signed manifest."""

    asf_keys: AsfKeysTrustRoot


class DraftGithubRelease(BuildishContractModel):
    """Convenience pointer to the matching draft GitHub Release."""

    repository: NonEmptyString
    tag: NonEmptyString
    url: NonEmptyString


class SourceArtifactContract(BuildishContractModel):
    """The single source artifact under vote."""

    role: Literal["asf-source-release"] = "asf-source-release"
    filename: NonEmptyString
    uri: NonEmptyString
    artifact_origin: NonEmptyString
    git_commit_sha: GitCommitSha
    reproducibility: ReproducibilitySelector | None = None
    checksums: Sha512Checksums
    signatures: list[SignatureReference] = Field(min_length=1)


class VoteMaterialsStrict(BuildishContractModel):
    """Strict vote-materials block for authored and emitted manifests."""

    source_artifacts: list[SourceArtifactContract]
    secondary_artifacts: list[AnySecondaryArtifact] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_single_source_artifact(self) -> VoteMaterialsStrict:
        if len(self.source_artifacts) != 1:
            raise ValueError("RC vote manifests must contain exactly one source artifact")
        return self


class VoteMaterialsRead(BuildishContractModel):
    """Tolerant vote-materials block used by verify-rc readers."""

    source_artifacts: list[SourceArtifactContract]
    secondary_artifacts: list[AnySecondaryArtifact | dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_single_source_artifact(self) -> VoteMaterialsRead:
        if len(self.source_artifacts) != 1:
            raise ValueError("RC vote manifests must contain exactly one source artifact")
        return self


class AuthoritativeManifestReference(BuildishContractModel):
    """Reference to the authoritative signed manifest file and sidecars."""

    uri: NonEmptyString
    checksum_uris: dict[Literal["sha512"], NonEmptyString]
    signatures: list[SignatureReference] = Field(min_length=1)


class ManifestVerificationMetadataStrict(BuildishContractModel):
    """Strict verification metadata emitted by finalize-rc-vote-materials."""

    staging_svn_url: NonEmptyString
    authoritative_manifest: AuthoritativeManifestReference


class ManifestVerificationMetadataRead(BuildishContractModel):
    """Tolerant verification metadata accepted by verify-rc."""

    staging_svn_url: NonEmptyString
    authoritative_manifest: AuthoritativeManifestReference | None = None


class RcVoteManifestV1(BuildishContractModel):
    """Strict authoritative RC vote manifest emitted by buildish-release-tooling."""

    schema_version: SchemaVersionV1 = "1"
    manifest_type: Literal["rc-vote"] = "rc-vote"
    component_id: NonEmptyString
    version: NonEmptyString
    release_line: NonEmptyString
    release_branch: NonEmptyString
    source_repository_url: NonEmptyString
    source_commit_sha: GitCommitSha
    source_date_epoch: int = Field(ge=0)
    rc_tag: NonEmptyString
    final_tag: NonEmptyString
    final_tag_mode: NonEmptyString
    provenance: ManifestProvenance
    trust_roots: ManifestTrustRoots
    draft_github_release: DraftGithubRelease
    vote_materials: VoteMaterialsStrict
    verification: ManifestVerificationMetadataStrict
    materialized_commit_sha: GitCommitSha | None = None


class RcVoteManifestReadV1(BuildishContractModel):
    """Tolerant RC vote-manifest reader used by verify-rc."""

    schema_version: SchemaVersionV1 = "1"
    manifest_type: Literal["rc-vote"] = "rc-vote"
    component_id: NonEmptyString
    version: NonEmptyString
    release_line: NonEmptyString
    release_branch: NonEmptyString
    source_repository_url: NonEmptyString
    source_commit_sha: GitCommitSha
    source_date_epoch: int
    rc_tag: NonEmptyString | None = None
    final_tag: NonEmptyString
    final_tag_mode: NonEmptyString
    provenance: dict[str, Any]
    trust_roots: ManifestTrustRoots
    draft_github_release: DraftGithubRelease
    vote_materials: VoteMaterialsRead
    verification: ManifestVerificationMetadataRead
    materialized_commit_sha: GitCommitSha | None = None

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

    path: NonEmptyString
    size_bytes: int = Field(ge=0)
    sha512: Sha512Hex


class MavenRepositoryInventoryV1(BuildishContractModel):
    """A signed Maven repository inventory attachment."""

    schema_version: SchemaVersionV1 = "1"
    inventory_type: Literal["maven-repository"] = "maven-repository"
    artifact_id: NonEmptyString
    staging_repository_id: NonEmptyString
    base_url: NonEmptyString
    entries: list[MavenRepositoryInventoryEntry] = Field(min_length=1)


class ChecksumVerificationReport(BuildishContractModel):
    """Observed checksum verification results for one downloaded artifact."""

    algorithm: Literal["sha256", "sha512"] | None = None
    value: str | None = None
    matches_manifest: bool | None = None
    sidecar_verified: bool = False


class IntegrityVerificationReport(BuildishContractModel):
    """Observed integrity verification results for one npm package."""

    algorithm: Literal["sha256", "sha512"] | None = None
    value: str | None = None
    matches_manifest_checksum: bool | None = None
    matches_downloaded_bytes: bool | None = None


class InventoryVerificationReport(BuildishContractModel):
    """Verification results for one downloaded inventory attachment."""

    filename: NonEmptyString
    uri: NonEmptyString
    sha512: Sha512Hex
    entry_count: int | None = Field(default=None, ge=0)
    total_size_bytes: int | None = Field(default=None, ge=0)


class LiveRepositorySignatureVerification(BuildishContractModel):
    """One detached signature verified in the live Maven repository."""

    path: NonEmptyString
    target_path: NonEmptyString
    signature: SignatureVerificationPayload


class LiveMavenRepositoryReport(BuildishContractModel):
    """Observed live-repository comparison results for a Maven staging repository."""

    entry_count: int | None = Field(default=None, ge=0)
    total_size_bytes: int = Field(ge=0)
    matches_signed_inventory: bool
    signature_verifications: list[LiveRepositorySignatureVerification] = Field(default_factory=list)


class PythonIndexResolutionReport(BuildishContractModel):
    """Resolution details for one Python simple-index lookup."""

    project_index_url: NonEmptyString
    resolved_url: str | None = None
    found_via: str | None = None
    sha256_matches_index: bool | None = None


class NpmRegistryResolutionReport(BuildishContractModel):
    """Resolution details for one npm registry lookup."""

    metadata_url: str | None = None
    found_via: str | None = None
    tarball_url_matches_manifest: bool | None = None
    integrity_matches_manifest: bool | None = None
    signatures_count: int = Field(ge=0)


class OciInspectionReport(BuildishContractModel):
    """Observed registry inspection results for one OCI image."""

    image_ref: NonEmptyString
    digest_matches_manifest: bool
    platform_digests_match: bool | None = None
    platform_digests: list[OciPlatformDigest] = Field(default_factory=list)


class InspectionEvidenceReference(BuildishContractModel):
    """One retained evidence file inside the verify-rc inspection bundle."""

    label: NonEmptyString
    path: NonEmptyString


class ArtifactReproducibilityReport(BuildishContractModel):
    """Observed local rebuild comparison results for one artifact."""

    profile_id: NonEmptyString
    verdict: VerificationVerdict
    comparison_mode: NonEmptyString
    recipe_source: Literal["canonical-profile", "local-override"] = "canonical-profile"
    execution_backend: Literal["host-direct"] = "host-direct"
    output_paths: list[NonEmptyString] = Field(default_factory=list)
    matches_remote_bytes: bool | None = None
    failure_class: NonEmptyString | None = None
    evidence: list[InspectionEvidenceReference] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class GenericFileVerificationReport(BuildishContractModel):
    """Verification report for one generic secondary file."""

    artifact_id: NonEmptyString
    kind: Literal["generic-file", "generic-file-with-openpgp"]
    verdict: VerificationVerdict
    issues: list[str] = Field(default_factory=list)
    filename: NonEmptyString
    uri: NonEmptyString
    checksum: ChecksumVerificationReport
    signatures: list[SignatureVerificationPayload] = Field(default_factory=list)
    inventory: InventoryVerificationReport | None = None
    reproducibility: ArtifactReproducibilityReport | None = None


class MavenRepositoryVerificationReport(BuildishContractModel):
    """Verification report for one staged Maven repository."""

    artifact_id: NonEmptyString
    kind: Literal["maven-repository"] = "maven-repository"
    verdict: VerificationVerdict
    issues: list[str] = Field(default_factory=list)
    staging_repository_id: NonEmptyString
    base_url: NonEmptyString
    inventory: InventoryVerificationReport | None = None
    live_repository: LiveMavenRepositoryReport


class PythonDistributionVerificationReport(BuildishContractModel):
    """Verification report for one Python distribution."""

    artifact_id: NonEmptyString
    kind: Literal["python-distribution"] = "python-distribution"
    verdict: VerificationVerdict
    issues: list[str] = Field(default_factory=list)
    filename: NonEmptyString
    uri: NonEmptyString
    index_url: NonEmptyString
    project_name: NonEmptyString
    version: NonEmptyString
    checksum: ChecksumVerificationReport
    index_resolution: PythonIndexResolutionReport
    reproducibility: ArtifactReproducibilityReport | None = None


class OciImageVerificationReport(BuildishContractModel):
    """Verification report for one OCI image."""

    artifact_id: NonEmptyString
    kind: Literal["oci-image"] = "oci-image"
    verdict: VerificationVerdict
    issues: list[str] = Field(default_factory=list)
    uri: NonEmptyString
    registry: NonEmptyString
    repository: NonEmptyString
    digest: OciContentDigest
    inspection: OciInspectionReport


class NpmPackageVerificationReport(BuildishContractModel):
    """Verification report for one npm package."""

    artifact_id: NonEmptyString
    kind: Literal["npm-package"] = "npm-package"
    verdict: VerificationVerdict
    issues: list[str] = Field(default_factory=list)
    filename: NonEmptyString
    uri: NonEmptyString
    registry_url: NonEmptyString
    package_name: NonEmptyString
    version: NonEmptyString
    integrity: IntegrityVerificationReport
    checksum: ChecksumVerificationReport
    registry_resolution: NpmRegistryResolutionReport
    reproducibility: ArtifactReproducibilityReport | None = None


class InvalidSecondaryArtifactVerificationReport(BuildishContractModel):
    """Failure record used when one secondary artifact entry is malformed."""

    artifact_id: NonEmptyString
    kind: Literal["_invalid-secondary-artifact-entry"] = "_invalid-secondary-artifact-entry"
    declared_kind: str | None = None
    verdict: Literal["failed"] = "failed"
    issues: list[str] = Field(default_factory=list)


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

    verdict: VerificationVerdict
    sha512: str | None = None
    keys_url_matches_manifest: bool
    keys_url_matches_component_config: bool | None = None
    signature: SignatureVerificationPayload | None = None
    rc_tag_target_commit: str | None = None
    rc_tag_matches_source_commit_sha: bool
    issues: list[str] = Field(default_factory=list)


class SourceArtifactVerificationSection(BuildishContractModel):
    """Source-artifact verification section of the verify-rc report."""

    verdict: VerificationVerdict
    filename: str | None = None
    uri: str | None = None
    sha512: str | None = None
    sha512_sidecar_verified: bool
    signature: SignatureVerificationPayload | None = None
    rebuilt_sha512: str | None = None
    matches_source_commit_sha: bool
    issues: list[str] = Field(default_factory=list)


class ReproducibilityExecutionSection(BuildishContractModel):
    """Run-level policy and execution summary for build-based reproducibility checks."""

    requested_mode: Literal["auto", "integrity-only", "full"]
    effective_mode: Literal["integrity-only", "full"]
    build_checks_attempted: bool
    execution_backend: Literal["none", "host-direct"] = "none"
    inherits_host_home: bool | None = None
    prompt_used: bool = False
    prompt_confirmed: bool | None = None
    skipped_reason: str | None = None


class InspectionBundleSection(BuildishContractModel):
    """Location of the curated reproducibility-inspection bundle for one verify-rc run."""

    relative_path_from_report: NonEmptyString


class VerifyRcReportV1(BuildishContractModel):
    """Machine-readable Phase 1a RC verification report."""

    schema_version: SchemaVersionV1 = "1"
    report_type: Literal["verify-rc"] = "verify-rc"
    component_id: str | None = None
    version: str | None = None
    rc_tag: str | None = None
    source_commit_sha: str | None = None
    source_date_epoch: int | None = Field(default=None, ge=0)
    source_repository_url: str | None = None
    manifest_url: NonEmptyString
    keys_url: NonEmptyString
    verdict: VerificationVerdict
    work_dir: NonEmptyString
    failures: list[VerificationFailurePayload] = Field(default_factory=list)
    manifest_verification: ManifestVerificationSection
    source_artifact_verification: SourceArtifactVerificationSection
    reproducibility_execution: ReproducibilityExecutionSection
    inspection_bundle: InspectionBundleSection | None = None
    secondary_artifact_verifications: list[AnySecondaryArtifactVerification] = Field(default_factory=list)


__all__ = [
    "AnySecondaryArtifact",
    "AnySecondaryArtifactVerification",
    "BuildishContractModel",
    "DraftGithubRelease",
    "ArtifactReproducibilityReport",
    "GenericFileSecondaryArtifact",
    "GenericFileVerificationReport",
    "GenericFileWithOpenPgpSecondaryArtifact",
    "GithubWorkflowProvenance",
    "InvalidSecondaryArtifactVerificationReport",
    "InspectionBundleSection",
    "InspectionEvidenceReference",
    "MavenRepositoryInventoryV1",
    "MavenRepositorySecondaryArtifact",
    "MavenRepositoryVerificationReport",
    "NpmPackageSecondaryArtifact",
    "NpmPackageVerificationReport",
    "OciImageSecondaryArtifact",
    "OciImageVerificationReport",
    "PythonDistributionSecondaryArtifact",
    "PythonDistributionVerificationReport",
    "RcVoteManifestReadV1",
    "RcVoteManifestV1",
    "SecondaryArtifactVerificationAdapter",
    "SecondaryArtifactManifestV1",
    "StrictSecondaryArtifactAdapter",
    "SupplementalInventoryReference",
    "ReproducibilityExecutionSection",
    "VerifyRcReportV1",
]
