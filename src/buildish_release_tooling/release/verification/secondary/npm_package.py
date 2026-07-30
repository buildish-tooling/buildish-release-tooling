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

"""npm package secondary-artifact verification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import quote, unquote, urljoin, urlparse

from pydantic import BaseModel, ConfigDict, Field

from buildish_release_tooling.release.contracts import (
    ArtifactReproducibilityReport,
    ChecksumVerificationReport,
    IntegrityVerificationReport,
    NpmPackageSecondaryArtifact,
    NpmPackageVerificationReport,
    NpmRegistryResolutionReport,
)
from buildish_release_tooling.release.external_json import validate_json_object_model_text
from buildish_release_tooling.release.models import ComponentConfig, VerifyRcOverrideConfig
from buildish_release_tooling.release.path_validation import validate_simple_filename
from buildish_release_tooling.release.rc_vote_manifest import (
    DEFAULT_CHECKSUM_SIDECAR_MAX_BYTES,
    download_uri_to_path,
    read_uri_bytes,
)
from buildish_release_tooling.release.source_artifact import checksum
from buildish_release_tooling.release.verification.common import (
    validate_fetch_uri,
    verify_checksum_sidecar,
)
from buildish_release_tooling.shared.io import read_bytes_bounded

from .file_reproducibility import verify_host_direct_single_file_reproducibility
from .shared import url_without_fragment


@dataclass(frozen=True)
class _NpmRegistryDistEntry:
    """Stable subset of one registry `dist` payload used by the verifier."""

    tarball: str
    integrity: str
    signatures_count: int


@dataclass(frozen=True)
class _NpmRegistryVersionEntry:
    """Stable subset of one registry version document used by the verifier."""

    name: str
    version: str
    dist: _NpmRegistryDistEntry


@dataclass(frozen=True)
class _NpmRegistryMetadataEntry:
    """One fetched npm metadata document plus fetch provenance."""

    metadata_url: str
    found_via: str
    versions: dict[str, _NpmRegistryVersionEntry]


class _ExternalNpmRegistryReadModel(BaseModel):
    """Typed subset base for external npm registry payloads."""

    model_config = ConfigDict(extra="allow")


class _NpmRegistryDistRead(_ExternalNpmRegistryReadModel):
    tarball: str | None = Field(
        default=None,
        description="Registry tarball download URL for the requested npm package version.",
    )
    integrity: str | None = Field(
        default=None,
        description="Registry integrity string advertised for the requested npm package tarball.",
    )
    signatures: list[object] | None = Field(
        default=None,
        description="Registry signature objects advertised for the requested npm package tarball.",
    )


class _NpmRegistryVersionRead(_ExternalNpmRegistryReadModel):
    name: str | None = Field(
        default=None,
        description="npm package name reported for one registry version document.",
    )
    version: str | None = Field(
        default=None,
        description="npm package version reported for one registry version document.",
    )
    dist: _NpmRegistryDistRead | None = Field(
        default=None,
        description="Registry `dist` block for the requested npm package version.",
    )


class _NpmRegistryMetadataRead(_ExternalNpmRegistryReadModel):
    versions: dict[str, _NpmRegistryVersionRead] = Field(
        default_factory=dict,
        description="Package versions indexed by version string in the npm registry metadata document.",
    )


def verify_npm_package(
    artifact_entry: NpmPackageSecondaryArtifact,
    *,
    manifest_url: str,
    work_dir: Path,
    allow_non_production_release_targets: bool,
    component_config: ComponentConfig | None,
    project_root: Path | None,
    source_date_epoch: int | None,
    build_checks_allowed: bool,
    inspection_bundle_root: Path | None,
    profile_overrides: VerifyRcOverrideConfig | None,
) -> NpmPackageVerificationReport:
    artifact_id = artifact_entry.artifact_id
    filename = validate_simple_filename(
        artifact_entry.filename,
        field_name=f"npm package filename for {artifact_id}",
    )
    artifact_uri = artifact_entry.uri
    registry_url = artifact_entry.registry_url
    package_name = artifact_entry.package_name
    version = artifact_entry.version
    issues: list[str] = []
    integrity_algorithm: Literal["sha256", "sha512"] | None = None
    integrity_digest: str | None = None
    integrity_value: str | None = None
    try:
        integrity_algorithm, integrity_digest, integrity_value = _parsed_npm_integrity(
            artifact_entry.integrity,
            source=manifest_url,
        )
    except Exception as exc:
        issues.append(str(exc))

    if artifact_entry.authenticity is not None:
        issues.append(
            "npm-package provenance verification is not implemented; omit authenticity metadata for now"
        )

    work_dir.mkdir(parents=True, exist_ok=True)
    artifact_path: Path | None = None
    try:
        validate_fetch_uri(
            artifact_uri,
            allow_non_production_release_targets=allow_non_production_release_targets,
            purpose=f"npm package URL for {artifact_id}",
        )
        downloaded_artifact_path = work_dir / filename
        download_uri_to_path(artifact_uri, downloaded_artifact_path)
        artifact_path = downloaded_artifact_path
    except Exception as exc:
        issues.append(str(exc))

    if artifact_entry.checksums.sha256 is not None:
        checksum_algorithm: Literal["sha256", "sha512"] = "sha256"
        checksum_value = artifact_entry.checksums.sha256.value
        checksum_uri = artifact_entry.checksums.sha256.uri
    else:
        checksum_algorithm = "sha512"
        checksum_payload = artifact_entry.checksums.sha512
        if checksum_payload is None:
            raise ValueError("npm-package checksums must define sha256 or sha512")
        checksum_value = checksum_payload.value
        checksum_uri = checksum_payload.uri
    actual_checksum: str | None = None
    checksum_matches_manifest = False
    if artifact_path is not None:
        actual_checksum = checksum(artifact_path, checksum_algorithm)
        if actual_checksum != checksum_value:
            issues.append(
                "npm-package checksum does not match the signed manifest: "
                f"{artifact_id} {actual_checksum} != {checksum_value}"
            )
        else:
            checksum_matches_manifest = True

    actual_integrity_digest: str | None = None
    integrity_matches_manifest_checksum: bool | None = None
    integrity_matches_downloaded_bytes: bool | None = None
    if (
        artifact_path is not None
        and integrity_algorithm is not None
        and integrity_digest is not None
    ):
        if integrity_algorithm == checksum_algorithm:
            integrity_matches_manifest_checksum = integrity_digest == checksum_value
            if not integrity_matches_manifest_checksum:
                issues.append(
                    "npm-package integrity does not match the signed manifest checksum: "
                    f"{integrity_value} != {checksum_algorithm}:{checksum_value}"
                )
        actual_integrity_digest = (
            actual_checksum
            if integrity_algorithm == checksum_algorithm
            else checksum(artifact_path, integrity_algorithm)
        )
        integrity_matches_downloaded_bytes = actual_integrity_digest == integrity_digest
        if not integrity_matches_downloaded_bytes:
            issues.append(
                "npm-package integrity does not match the downloaded tarball bytes: "
                f"{artifact_id} {actual_integrity_digest} != {integrity_digest}"
            )

    checksum_sidecar_verified = False
    if artifact_path is not None and checksum_uri is not None:
        try:
            validate_fetch_uri(
                checksum_uri,
                allow_non_production_release_targets=allow_non_production_release_targets,
                purpose=f"npm package checksum sidecar URL for {artifact_id}",
            )
            sidecar_path = work_dir / f"{filename}.{checksum_algorithm}"
            download_uri_to_path(
                checksum_uri,
                sidecar_path,
                max_bytes=DEFAULT_CHECKSUM_SIDECAR_MAX_BYTES,
            )
            verify_checksum_sidecar(
                artifact_path,
                sidecar_path,
                algorithm=checksum_algorithm,
                purpose=f"npm package {artifact_id}",
            )
            checksum_sidecar_verified = True
        except Exception as exc:
            issues.append(str(exc))

    metadata_url: str | None = None
    found_via: str | None = None
    tarball_url_matches_manifest: bool | None = None
    registry_integrity_matches_manifest: bool | None = None
    signatures_count = 0
    reproducibility_verification: ArtifactReproducibilityReport | None = None
    try:
        metadata_entry = _npm_registry_package_metadata(
            registry_url,
            package_name,
            allow_non_production_release_targets=allow_non_production_release_targets,
        )
        metadata_url = metadata_entry.metadata_url
        found_via = metadata_entry.found_via
        version_entry = _npm_registry_version_entry(
            metadata_entry,
            package_name=package_name,
            version=version,
        )
        tarball_url = version_entry.dist.tarball
        tarball_url_matches_manifest = url_without_fragment(tarball_url) == url_without_fragment(artifact_uri)
        if not tarball_url_matches_manifest:
            issues.append(
                "npm-package registry tarball URL does not match the signed manifest: "
                f"{tarball_url} != {artifact_uri}"
            )
        registry_integrity_algorithm, registry_integrity_digest, registry_integrity_value = _parsed_npm_integrity(
            version_entry.dist.integrity,
            source=metadata_url,
        )
        registry_integrity_matches_manifest = (
            integrity_algorithm is not None
            and integrity_digest is not None
            and integrity_value is not None
            and registry_integrity_algorithm == integrity_algorithm
            and registry_integrity_digest == integrity_digest
            and registry_integrity_value == integrity_value
        )
        if not registry_integrity_matches_manifest:
            issues.append(
                "npm-package registry integrity does not match the signed manifest: "
                f"{registry_integrity_value} != {integrity_value}"
            )
        signatures_count = version_entry.dist.signatures_count
    except Exception as exc:
        issues.append(str(exc))

    if build_checks_allowed and artifact_entry.reproducibility is not None:
        reproducibility_verification = verify_host_direct_single_file_reproducibility(
            artifact_entry,
            manifest_url=manifest_url,
            artifact_id=artifact_id,
            kind="npm-package",
            artifact_path=artifact_path,
            work_dir=work_dir / "reproducibility",
            component_config=component_config,
            project_root=project_root,
            source_date_epoch=source_date_epoch,
            inspection_bundle_root=inspection_bundle_root,
            subject_label="npm-package",
            profile_overrides=profile_overrides,
        )
        issues.extend(reproducibility_verification.issues)

    return NpmPackageVerificationReport(
        artifact_id=artifact_id,
        verdict="failed" if issues else "verified",
        issues=issues,
        filename=filename,
        uri=artifact_uri,
        registry_url=registry_url,
        package_name=package_name,
        version=version,
        integrity=IntegrityVerificationReport(
            algorithm=integrity_algorithm,
            value=integrity_value,
            matches_manifest_checksum=integrity_matches_manifest_checksum,
            matches_downloaded_bytes=integrity_matches_downloaded_bytes,
        ),
        checksum=ChecksumVerificationReport(
            algorithm=checksum_algorithm,
            value=actual_checksum,
            matches_manifest=checksum_matches_manifest,
            sidecar_verified=checksum_sidecar_verified,
        ),
        registry_resolution=NpmRegistryResolutionReport(
            metadata_url=metadata_url,
            found_via=found_via,
            tarball_url_matches_manifest=tarball_url_matches_manifest,
            integrity_matches_manifest=registry_integrity_matches_manifest,
            signatures_count=signatures_count,
        ),
        reproducibility=reproducibility_verification,
    )


def _parsed_npm_integrity(
    raw_value: str,
    *,
    source: str,
) -> tuple[Literal["sha256", "sha512"], str, str]:
    normalized = raw_value.strip()
    if not normalized:
        raise ValueError(f"npm-package integrity must not be empty: {source}")
    algorithm, separator, encoded_digest = normalized.partition("-")
    raw_algorithm = algorithm.lower()
    if raw_algorithm == "sha256":
        normalized_algorithm: Literal["sha256", "sha512"] = "sha256"
    elif raw_algorithm == "sha512":
        normalized_algorithm = "sha512"
    else:
        raise ValueError(
            f"npm-package integrity must use sha256-<base64> or sha512-<base64>: {source}"
        )
    if not separator or not encoded_digest:
        raise ValueError(
            f"npm-package integrity must use sha256-<base64> or sha512-<base64>: {source}"
        )
    digest_bytes = _decoded_base64_bytes(encoded_digest, source=source)
    expected_length = 32 if normalized_algorithm == "sha256" else 64
    if len(digest_bytes) != expected_length:
        raise ValueError(
            f"npm-package integrity digest length does not match its declared algorithm: {source}"
        )
    canonical_value = f"{normalized_algorithm}-{encoded_digest}"
    return normalized_algorithm, digest_bytes.hex(), canonical_value


def _decoded_base64_bytes(encoded_digest: str, *, source: str) -> bytes:
    try:
        import base64
        import binascii

        return base64.b64decode(encoded_digest, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError(
            f"npm-package integrity must use sha256-<base64> or sha512-<base64>: {source}"
        ) from exc


def _npm_registry_package_metadata(
    registry_url: str,
    package_name: str,
    *,
    allow_non_production_release_targets: bool,
) -> _NpmRegistryMetadataEntry:
    fetch_errors: list[str] = []
    for metadata_url, found_via in _npm_registry_metadata_urls(registry_url, package_name):
        validate_fetch_uri(
            metadata_url,
            allow_non_production_release_targets=allow_non_production_release_targets,
            purpose=f"npm registry metadata URL for {package_name}",
        )
        try:
            payload = validate_json_object_model_text(
                _NpmRegistryMetadataRead,
                _read_npm_registry_bytes(metadata_url),
                source=f"npm-package registry metadata at {metadata_url}",
                expected_payload="npm registry metadata",
            )
        except Exception as exc:
            fetch_errors.append(f"{metadata_url}: {exc}")
            continue
        return _typed_npm_registry_metadata(payload, metadata_url=metadata_url, found_via=found_via)
    error_summary = "; ".join(fetch_errors) if fetch_errors else registry_url
    raise ValueError(f"npm-package registry metadata could not be fetched for {package_name}: {error_summary}")


def _typed_npm_registry_metadata(
    payload: _NpmRegistryMetadataRead,
    *,
    metadata_url: str,
    found_via: str,
) -> _NpmRegistryMetadataEntry:
    versions: dict[str, _NpmRegistryVersionEntry] = {}
    for raw_version, raw_version_payload in payload.versions.items():
        name = raw_version_payload.name
        version = raw_version_payload.version
        raw_dist = raw_version_payload.dist
        if name is None or version is None or raw_dist is None:
            continue
        tarball = raw_dist.tarball
        integrity = raw_dist.integrity
        if tarball is None or not tarball.strip():
            continue
        if integrity is None or not integrity.strip():
            continue
        raw_signatures = raw_dist.signatures
        if raw_signatures is None:
            signatures_count = 0
        else:
            signatures_count = len(raw_signatures)
        versions[raw_version] = _NpmRegistryVersionEntry(
            name=name.strip(),
            version=version.strip(),
            dist=_NpmRegistryDistEntry(
                tarball=tarball.strip(),
                integrity=integrity.strip(),
                signatures_count=signatures_count,
            ),
        )
    return _NpmRegistryMetadataEntry(
        metadata_url=metadata_url,
        found_via=found_via,
        versions=versions,
    )


def _npm_registry_metadata_urls(registry_url: str, package_name: str) -> tuple[tuple[str, str], ...]:
    normalized_base = registry_url.rstrip("/") + "/"
    plain_url = urljoin(normalized_base, package_name)
    encoded_url = urljoin(normalized_base, quote(package_name, safe="@"))
    if encoded_url == plain_url:
        return ((plain_url, "plain-path"),)
    return (
        (plain_url, "plain-path"),
        (encoded_url, "percent-encoded-path"),
    )


def _read_npm_registry_bytes(metadata_url: str) -> bytes:
    parsed = urlparse(metadata_url)
    if parsed.scheme != "file":
        return read_uri_bytes(metadata_url)
    local_path = Path(unquote(parsed.path))
    if local_path.is_dir():
        for candidate_name in ("index.json", "package.json"):
            candidate_path = local_path / candidate_name
            if candidate_path.is_file():
                with candidate_path.open("rb") as handle:
                    return read_bytes_bounded(handle, max_bytes=25 * 1024 * 1024)
        raise ValueError(f"npm-package registry directory has no metadata JSON file: {local_path}")
    return read_uri_bytes(metadata_url)


def _npm_registry_version_entry(
    metadata_entry: _NpmRegistryMetadataEntry,
    *,
    package_name: str,
    version: str,
) -> _NpmRegistryVersionEntry:
    version_entry = metadata_entry.versions.get(version)
    if version_entry is None:
        raise ValueError(
            f"npm-package version {version} is missing from registry metadata: {metadata_entry.metadata_url}"
        )
    if version_entry.name != package_name:
        raise ValueError(
            "npm-package registry metadata package name does not match the signed manifest: "
            f"{version_entry.name} != {package_name}"
        )
    if version_entry.version != version:
        raise ValueError(
            "npm-package registry metadata version does not match the signed manifest: "
            f"{version_entry.version} != {version}"
        )
    return version_entry
