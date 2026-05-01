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

"""npm package secondary-artifact verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urljoin, urlparse

from apache_buildish_release_tooling.release.models import ComponentConfig, VerifyRcOverrideConfig
from apache_buildish_release_tooling.release.rc_vote_manifest import read_uri_bytes
from apache_buildish_release_tooling.release.source_artifact import checksum
from apache_buildish_release_tooling.release.verification.common import (
    validate_fetch_uri,
    verify_checksum_sidecar,
)

from .file_reproducibility import verify_host_direct_single_file_reproducibility
from .shared import (
    SUPPORTED_CHECKSUMS,
    preferred_checksum_payload,
    required_non_empty_string,
    url_without_fragment,
)


def verify_npm_package(
    artifact_entry: dict[str, Any],
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
) -> dict[str, Any]:
    artifact_id = required_non_empty_string(artifact_entry, "artifact_id", source=manifest_url)
    filename = required_non_empty_string(artifact_entry, "filename", source=manifest_url)
    artifact_uri = required_non_empty_string(artifact_entry, "uri", source=manifest_url)
    registry_url = required_non_empty_string(artifact_entry, "registry_url", source=manifest_url)
    package_name = required_non_empty_string(artifact_entry, "package_name", source=manifest_url)
    version = required_non_empty_string(artifact_entry, "version", source=manifest_url)
    issues: list[str] = []
    integrity_algorithm: str | None = None
    integrity_digest: str | None = None
    integrity_value: str | None = None
    try:
        integrity_algorithm, integrity_digest, integrity_value = _required_npm_integrity(
            artifact_entry,
            source=manifest_url,
        )
    except Exception as exc:
        issues.append(str(exc))

    authenticity = artifact_entry.get("authenticity")
    if authenticity is not None:
        try:
            scheme = required_non_empty_string(authenticity, "scheme", source=manifest_url)
            if scheme != "npm-provenance":
                raise ValueError(f"unsupported npm-package authenticity scheme: {scheme}")
            raise ValueError(
                "npm-package provenance verification is not implemented; omit authenticity metadata for now"
            )
        except Exception as exc:
            issues.append(str(exc))

    work_dir.mkdir(parents=True, exist_ok=True)
    artifact_path: Path | None = None
    try:
        validate_fetch_uri(
            artifact_uri,
            allow_non_production_release_targets=allow_non_production_release_targets,
            purpose=f"npm package URL for {artifact_id}",
        )
        downloaded_artifact_path = work_dir / filename
        downloaded_artifact_path.write_bytes(read_uri_bytes(artifact_uri))
        artifact_path = downloaded_artifact_path
    except Exception as exc:
        issues.append(str(exc))

    checksum_algorithm: str | None = None
    checksum_value: str | None = None
    checksum_uri: str | None = None
    actual_checksum: str | None = None
    checksum_matches_manifest = False
    try:
        checksum_algorithm, checksum_value, checksum_uri = preferred_checksum_payload(
            artifact_entry,
            source=manifest_url,
        )
    except Exception as exc:
        issues.append(str(exc))

    if artifact_path is not None and checksum_algorithm is not None and checksum_value is not None:
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
        and checksum_algorithm is not None
        and checksum_value is not None
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
    if artifact_path is not None and checksum_uri is not None and checksum_algorithm is not None:
        try:
            validate_fetch_uri(
                checksum_uri,
                allow_non_production_release_targets=allow_non_production_release_targets,
                purpose=f"npm package checksum sidecar URL for {artifact_id}",
            )
            sidecar_path = work_dir / f"{filename}.{checksum_algorithm}"
            sidecar_path.write_bytes(read_uri_bytes(checksum_uri))
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
    reproducibility_verification: dict[str, Any] | None = None
    try:
        metadata_url, metadata_payload, found_via = _npm_registry_package_metadata(
            registry_url,
            package_name,
            allow_non_production_release_targets=allow_non_production_release_targets,
        )
        version_payload = _npm_registry_version_payload(
            metadata_payload,
            package_name=package_name,
            version=version,
            source=metadata_url,
        )
        dist_payload = version_payload.get("dist")
        if not isinstance(dist_payload, dict):
            raise ValueError(
                f"npm-package registry metadata is missing dist for {package_name}@{version}: {metadata_url}"
            )
        tarball_url = required_non_empty_string(dist_payload, "tarball", source=metadata_url)
        tarball_url_matches_manifest = url_without_fragment(tarball_url) == url_without_fragment(artifact_uri)
        if not tarball_url_matches_manifest:
            issues.append(
                "npm-package registry tarball URL does not match the signed manifest: "
                f"{tarball_url} != {artifact_uri}"
            )
        registry_integrity = required_non_empty_string(dist_payload, "integrity", source=metadata_url)
        registry_integrity_algorithm, registry_integrity_digest, registry_integrity_value = _parsed_npm_integrity(
            registry_integrity,
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
        registry_signatures = dist_payload.get("signatures")
        if registry_signatures is None:
            signatures_count = 0
        elif isinstance(registry_signatures, list):
            signatures_count = len(registry_signatures)
        else:
            issues.append(f"npm-package registry signatures must be a list when present: {metadata_url}")
    except Exception as exc:
        issues.append(str(exc))

    if build_checks_allowed and artifact_entry.get("reproducibility") is not None:
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
        issues.extend(reproducibility_verification.get("issues", []))

    verification = {
        "artifact_id": artifact_id,
        "kind": "npm-package",
        "verdict": "failed" if issues else "verified",
        "issues": issues,
        "filename": filename,
        "uri": artifact_uri,
        "registry_url": registry_url,
        "package_name": package_name,
        "version": version,
        "integrity": {
            "algorithm": integrity_algorithm,
            "value": integrity_value,
            "matches_manifest_checksum": integrity_matches_manifest_checksum,
            "matches_downloaded_bytes": integrity_matches_downloaded_bytes,
        },
        "checksum": {
            "algorithm": checksum_algorithm,
            "value": actual_checksum,
            "matches_manifest": checksum_matches_manifest,
            "sidecar_verified": checksum_sidecar_verified,
        },
        "registry_resolution": {
            "metadata_url": metadata_url,
            "found_via": found_via,
            "tarball_url_matches_manifest": tarball_url_matches_manifest,
            "integrity_matches_manifest": registry_integrity_matches_manifest,
            "signatures_count": signatures_count,
        },
    }
    if reproducibility_verification is not None:
        verification["reproducibility"] = reproducibility_verification
    return verification


def _required_npm_integrity(
    artifact_entry: dict[str, Any],
    *,
    source: str,
) -> tuple[str, str, str]:
    integrity = artifact_entry.get("integrity")
    if not isinstance(integrity, str) or not integrity.strip():
        raise ValueError(f"npm-package manifest is missing integrity: {source}")
    return _parsed_npm_integrity(integrity, source=source)


def _parsed_npm_integrity(raw_value: str, *, source: str) -> tuple[str, str, str]:
    normalized = raw_value.strip()
    if not normalized:
        raise ValueError(f"npm-package integrity must not be empty: {source}")
    algorithm, separator, encoded_digest = normalized.partition("-")
    normalized_algorithm = algorithm.lower()
    if (
        not separator
        or not encoded_digest
        or normalized_algorithm not in SUPPORTED_CHECKSUMS
    ):
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
) -> tuple[str, dict[str, Any], str]:
    fetch_errors: list[str] = []
    for metadata_url, found_via in _npm_registry_metadata_urls(registry_url, package_name):
        validate_fetch_uri(
            metadata_url,
            allow_non_production_release_targets=allow_non_production_release_targets,
            purpose=f"npm registry metadata URL for {package_name}",
        )
        try:
            payload = json.loads(_read_npm_registry_bytes(metadata_url).decode("utf-8"))
        except Exception as exc:
            fetch_errors.append(f"{metadata_url}: {exc}")
            continue
        if not isinstance(payload, dict):
            raise ValueError(f"npm-package registry metadata must be a JSON object: {metadata_url}")
        return metadata_url, payload, found_via
    error_summary = "; ".join(fetch_errors) if fetch_errors else registry_url
    raise ValueError(f"npm-package registry metadata could not be fetched for {package_name}: {error_summary}")


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
                return candidate_path.read_bytes()
        raise ValueError(f"npm-package registry directory has no metadata JSON file: {local_path}")
    return read_uri_bytes(metadata_url)


def _npm_registry_version_payload(
    metadata_payload: dict[str, Any],
    *,
    package_name: str,
    version: str,
    source: str,
) -> dict[str, Any]:
    raw_versions = metadata_payload.get("versions")
    if not isinstance(raw_versions, dict):
        raise ValueError(f"npm-package registry metadata is missing versions: {source}")
    version_payload = raw_versions.get(version)
    if not isinstance(version_payload, dict):
        raise ValueError(f"npm-package version {version} is missing from registry metadata: {source}")
    metadata_package_name = required_non_empty_string(version_payload, "name", source=source)
    if metadata_package_name != package_name:
        raise ValueError(
            "npm-package registry metadata package name does not match the signed manifest: "
            f"{metadata_package_name} != {package_name}"
        )
    metadata_version = required_non_empty_string(version_payload, "version", source=source)
    if metadata_version != version:
        raise ValueError(
            "npm-package registry metadata version does not match the signed manifest: "
            f"{metadata_version} != {version}"
        )
    return version_payload
