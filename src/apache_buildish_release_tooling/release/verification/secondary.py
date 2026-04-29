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

"""Secondary-artifact verification helpers for `verify-rc`."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

from apache_buildish_release_tooling.release.artifact_registration.kinds.maven_repository import (
    _RemoteHttpClient,
    _inventory_worker_count,
    _repository_file_bytes,
    _repository_files,
    _validated_repository_root,
)
from apache_buildish_release_tooling.release.artifact_registration.kinds.oci_image import (
    _inspect_image_ref,
)
from apache_buildish_release_tooling.release.progress import ProgressReporter
from apache_buildish_release_tooling.release.rc_vote_manifest import read_uri_bytes
from apache_buildish_release_tooling.release.source_artifact import checksum
from apache_buildish_release_tooling.release.verification.common import (
    GpgVerifier,
    SignatureVerification,
    signature_payload,
    validate_fetch_uri,
    verify_checksum_sidecar,
)

_SUPPORTED_CHECKSUMS = ("sha512", "sha256")
_CHECKSUM_LENGTHS = {
    "sha256": 64,
    "sha512": 128,
}
_SAFE_PATH_COMPONENT_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class _DownloadedInventory:
    """One verified inventory attachment plus its parsed JSON payload."""

    path: Path
    raw_payload: dict[str, Any]
    report_payload: dict[str, Any]


class _SimpleIndexHtmlParser(HTMLParser):
    """Collect file links from one HTML simple-index project page."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if not href:
            return
        self.links.append({"href": href})


def verify_secondary_artifacts(
    manifest_payload: dict[str, Any],
    *,
    manifest_url: str,
    work_dir: Path,
    verifier: GpgVerifier,
    allow_non_production_release_targets: bool,
) -> list[dict[str, Any]]:
    """Verify all supported secondary artifacts declared in the signed vote manifest."""

    work_dir.mkdir(parents=True, exist_ok=True)
    artifact_entries = _secondary_artifact_entries(manifest_payload, source=manifest_url)
    verifications: list[dict[str, Any]] = []
    for index, artifact_entry in enumerate(artifact_entries, start=1):
        artifact_id = _required_non_empty_string(
            artifact_entry,
            "artifact_id",
            source=manifest_url,
        )
        kind = _required_non_empty_string(artifact_entry, "kind", source=manifest_url)
        artifact_work_dir = work_dir / f"{index:02d}-{_safe_path_component(artifact_id)}"
        if kind == "generic-file":
            verifications.append(
                _verify_generic_file(
                    artifact_entry,
                    manifest_url=manifest_url,
                    work_dir=artifact_work_dir,
                    verifier=verifier,
                    allow_non_production_release_targets=allow_non_production_release_targets,
                    require_signature=False,
                )
            )
            continue
        if kind == "generic-file-with-openpgp":
            verifications.append(
                _verify_generic_file(
                    artifact_entry,
                    manifest_url=manifest_url,
                    work_dir=artifact_work_dir,
                    verifier=verifier,
                    allow_non_production_release_targets=allow_non_production_release_targets,
                    require_signature=True,
                )
            )
            continue
        if kind == "maven-repository":
            verifications.append(
                _verify_maven_repository(
                    artifact_entry,
                    manifest_url=manifest_url,
                    work_dir=artifact_work_dir,
                    verifier=verifier,
                    allow_non_production_release_targets=allow_non_production_release_targets,
                )
            )
            continue
        if kind == "python-distribution":
            verifications.append(
                _verify_python_distribution(
                    artifact_entry,
                    manifest_url=manifest_url,
                    work_dir=artifact_work_dir,
                    allow_non_production_release_targets=allow_non_production_release_targets,
                )
            )
            continue
        if kind == "oci-image":
            verifications.append(
                _verify_oci_image(
                    artifact_entry,
                    manifest_url=manifest_url,
                )
            )
            continue
        raise ValueError(f"unsupported secondary artifact kind in manifest: {kind}")
    return verifications


def _secondary_artifact_entries(manifest_payload: dict[str, Any], *, source: str) -> list[dict[str, Any]]:
    vote_materials = manifest_payload.get("vote_materials")
    if not isinstance(vote_materials, dict):
        raise ValueError(f"manifest is missing vote_materials: {source}")
    secondary_artifacts = vote_materials.get("secondary_artifacts")
    if not isinstance(secondary_artifacts, list):
        raise ValueError(f"manifest secondary_artifacts must be a list: {source}")
    entries: list[dict[str, Any]] = []
    for artifact_entry in secondary_artifacts:
        if not isinstance(artifact_entry, dict):
            raise ValueError(f"manifest secondary artifact entries must be objects: {source}")
        entries.append(artifact_entry)
    return entries


def _verify_generic_file(
    artifact_entry: dict[str, Any],
    *,
    manifest_url: str,
    work_dir: Path,
    verifier: GpgVerifier,
    allow_non_production_release_targets: bool,
    require_signature: bool,
) -> dict[str, Any]:
    artifact_id = _required_non_empty_string(artifact_entry, "artifact_id", source=manifest_url)
    kind = _required_non_empty_string(artifact_entry, "kind", source=manifest_url)
    filename = _required_non_empty_string(artifact_entry, "filename", source=manifest_url)
    artifact_uri = _required_non_empty_string(artifact_entry, "uri", source=manifest_url)
    validate_fetch_uri(
        artifact_uri,
        allow_non_production_release_targets=allow_non_production_release_targets,
        purpose=f"secondary artifact URL for {artifact_id}",
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = work_dir / filename
    artifact_path.write_bytes(read_uri_bytes(artifact_uri))

    checksum_algorithm, checksum_value, checksum_uri = _preferred_checksum_payload(
        artifact_entry,
        source=manifest_url,
    )
    actual_checksum = checksum(artifact_path, checksum_algorithm)
    if actual_checksum != checksum_value:
        raise ValueError(
            "secondary artifact checksum does not match the signed manifest: "
            f"{artifact_id} {actual_checksum} != {checksum_value}"
        )

    checksum_sidecar_verified = False
    if checksum_uri is not None:
        validate_fetch_uri(
            checksum_uri,
            allow_non_production_release_targets=allow_non_production_release_targets,
            purpose=f"secondary artifact checksum sidecar URL for {artifact_id}",
        )
        sidecar_path = work_dir / f"{filename}.{checksum_algorithm}"
        sidecar_path.write_bytes(read_uri_bytes(checksum_uri))
        verify_checksum_sidecar(
            artifact_path,
            sidecar_path,
            algorithm=checksum_algorithm,
            purpose=f"secondary artifact {artifact_id}",
        )
        checksum_sidecar_verified = True

    signature_verifications = _verified_openpgp_signatures(
        artifact_entry,
        manifest_url=manifest_url,
        artifact_id=artifact_id,
        artifact_path=artifact_path,
        work_dir=work_dir,
        verifier=verifier,
        allow_non_production_release_targets=allow_non_production_release_targets,
        require_signature=require_signature,
    )
    inventory_verification = _downloaded_inventory(
        artifact_entry,
        manifest_url=manifest_url,
        artifact_id=artifact_id,
        work_dir=work_dir,
        allow_non_production_release_targets=allow_non_production_release_targets,
    )

    verification: dict[str, Any] = {
        "artifact_id": artifact_id,
        "kind": kind,
        "verdict": "verified",
        "filename": filename,
        "uri": artifact_uri,
        "checksum": {
            "algorithm": checksum_algorithm,
            "value": actual_checksum,
            "sidecar_verified": checksum_sidecar_verified,
        },
        "signatures": [signature_payload(signature) for signature in signature_verifications],
    }
    if inventory_verification is not None:
        verification["inventory"] = inventory_verification.report_payload
    return verification


def _verify_maven_repository(
    artifact_entry: dict[str, Any],
    *,
    manifest_url: str,
    work_dir: Path,
    verifier: GpgVerifier,
    allow_non_production_release_targets: bool,
) -> dict[str, Any]:
    artifact_id = _required_non_empty_string(artifact_entry, "artifact_id", source=manifest_url)
    staging_repository_id = _required_non_empty_string(
        artifact_entry,
        "staging_repository_id",
        source=manifest_url,
    )
    base_url = _required_non_empty_string(artifact_entry, "base_url", source=manifest_url)
    validate_fetch_uri(
        base_url,
        allow_non_production_release_targets=allow_non_production_release_targets,
        purpose=f"maven repository base URL for {artifact_id}",
    )
    _validated_repository_root(base_url, staging_repository_id)
    downloaded_inventory = _downloaded_inventory(
        artifact_entry,
        manifest_url=manifest_url,
        artifact_id=artifact_id,
        work_dir=work_dir,
        allow_non_production_release_targets=allow_non_production_release_targets,
    )
    if downloaded_inventory is None:
        raise ValueError(f"manifest maven-repository artifact is missing inventory: {artifact_id}")
    inventory_payload = _validated_maven_inventory_payload(
        downloaded_inventory.raw_payload,
        artifact_id=artifact_id,
        staging_repository_id=staging_repository_id,
        base_url=base_url,
        source=manifest_url,
    )

    worker_count = _inventory_worker_count(None)
    progress_reporter = ProgressReporter.from_mode("off")
    remote_http_client: _RemoteHttpClient | None = None
    if base_url.startswith(("http://", "https://")):
        remote_http_client = _RemoteHttpClient.for_worker_count(worker_count)
    try:
        repository_files = _repository_files(
            base_url,
            worker_count=worker_count,
            remote_http_client=remote_http_client,
            progress_reporter=progress_reporter,
        )
        files_by_relative_path = {
            repository_file.relative_path: repository_file
            for repository_file in repository_files
        }
        expected_entries = _maven_inventory_entries(
            inventory_payload,
            source=manifest_url,
        )
        expected_paths = set(expected_entries)
        live_paths = set(files_by_relative_path)
        if live_paths != expected_paths:
            raise ValueError(
                "live maven repository paths do not match the signed inventory: "
                f"missing={sorted(expected_paths - live_paths)} unexpected={sorted(live_paths - expected_paths)}"
            )

        cache: dict[str, bytes] = {}
        total_size_bytes = 0
        for relative_path, expected_entry in expected_entries.items():
            repository_file = files_by_relative_path[relative_path]
            total_size_bytes += repository_file.size_bytes
            if repository_file.size_bytes != expected_entry["size_bytes"]:
                raise ValueError(
                    "live maven repository file size does not match the signed inventory: "
                    f"{relative_path} {repository_file.size_bytes} != {expected_entry['size_bytes']}"
                )
            actual_sha512 = hashlib.sha512(
                _repository_file_bytes(
                    repository_file,
                    cache=cache,
                    remote_http_client=remote_http_client,
                )
            ).hexdigest()
            if actual_sha512 != expected_entry["sha512"]:
                raise ValueError(
                    "live maven repository checksum does not match the signed inventory: "
                    f"{relative_path} {actual_sha512} != {expected_entry['sha512']}"
                )

        signature_verifications = _verified_maven_repository_signatures(
            files_by_relative_path,
            cache=cache,
            remote_http_client=remote_http_client,
            verifier=verifier,
            work_dir=work_dir / "signatures",
        )
    finally:
        if remote_http_client is not None:
            remote_http_client.close()

    inventory_report_payload = dict(downloaded_inventory.report_payload)
    inventory_metadata = artifact_entry.get("inventory")
    if isinstance(inventory_metadata, dict):
        entry_count = inventory_metadata.get("entry_count")
        if isinstance(entry_count, int):
            inventory_report_payload["entry_count"] = entry_count
            if entry_count != len(expected_entries):
                raise ValueError(
                    "manifest maven inventory entry_count does not match the signed inventory: "
                    f"{entry_count} != {len(expected_entries)}"
                )
        total_size_metadata = inventory_metadata.get("total_size_bytes")
        if isinstance(total_size_metadata, int):
            inventory_report_payload["total_size_bytes"] = total_size_metadata
            if total_size_metadata != total_size_bytes:
                raise ValueError(
                    "manifest maven inventory total_size_bytes does not match the live repository: "
                    f"{total_size_metadata} != {total_size_bytes}"
                )

    return {
        "artifact_id": artifact_id,
        "kind": "maven-repository",
        "verdict": "verified",
        "staging_repository_id": staging_repository_id,
        "base_url": base_url,
        "inventory": inventory_report_payload,
        "live_repository": {
            "entry_count": len(expected_entries),
            "total_size_bytes": total_size_bytes,
            "matches_signed_inventory": True,
            "signature_verifications": [
                {
                    "path": relative_path,
                    "target_path": target_path,
                    "signature": signature_payload(signature_verification),
                }
                for relative_path, target_path, signature_verification in signature_verifications
            ],
        },
    }


def _verify_python_distribution(
    artifact_entry: dict[str, Any],
    *,
    manifest_url: str,
    work_dir: Path,
    allow_non_production_release_targets: bool,
) -> dict[str, Any]:
    artifact_id = _required_non_empty_string(artifact_entry, "artifact_id", source=manifest_url)
    filename = _required_non_empty_string(artifact_entry, "filename", source=manifest_url)
    artifact_uri = _required_non_empty_string(artifact_entry, "uri", source=manifest_url)
    index_url = _required_non_empty_string(artifact_entry, "index_url", source=manifest_url)
    project_name = _required_non_empty_string(artifact_entry, "project_name", source=manifest_url)
    version = _required_non_empty_string(artifact_entry, "version", source=manifest_url)
    if version not in filename:
        raise ValueError(
            "python-distribution filename does not contain the declared version: "
            f"{filename} vs {version}"
        )
    authenticity = artifact_entry.get("authenticity")
    if authenticity is not None:
        scheme = _required_non_empty_string(authenticity, "scheme", source=manifest_url)
        if scheme != "pypi-attestation":
            raise ValueError(f"unsupported python-distribution authenticity scheme: {scheme}")
        raise ValueError(
            "python-distribution pypi-attestation verification is not implemented; omit authenticity metadata for now"
        )

    validate_fetch_uri(
        artifact_uri,
        allow_non_production_release_targets=allow_non_production_release_targets,
        purpose=f"python distribution URL for {artifact_id}",
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = work_dir / filename
    artifact_path.write_bytes(read_uri_bytes(artifact_uri))

    checksum_algorithm, checksum_value, checksum_uri = _required_checksum_payload(
        artifact_entry,
        source=manifest_url,
        algorithms=("sha256",),
    )
    actual_checksum = checksum(artifact_path, checksum_algorithm)
    if actual_checksum != checksum_value:
        raise ValueError(
            "python-distribution checksum does not match the signed manifest: "
            f"{artifact_id} {actual_checksum} != {checksum_value}"
        )
    checksum_sidecar_verified = False
    if checksum_uri is not None:
        validate_fetch_uri(
            checksum_uri,
            allow_non_production_release_targets=allow_non_production_release_targets,
            purpose=f"python distribution checksum sidecar URL for {artifact_id}",
        )
        sidecar_path = work_dir / f"{filename}.{checksum_algorithm}"
        sidecar_path.write_bytes(read_uri_bytes(checksum_uri))
        verify_checksum_sidecar(
            artifact_path,
            sidecar_path,
            algorithm=checksum_algorithm,
            purpose=f"python distribution {artifact_id}",
        )
        checksum_sidecar_verified = True

    project_index_url = _simple_index_project_url(index_url, project_name)
    validate_fetch_uri(
        project_index_url,
        allow_non_production_release_targets=allow_non_production_release_targets,
        purpose=f"python simple index URL for {artifact_id}",
    )
    project_index_entries = _simple_index_entries(project_index_url)
    matching_entry = next(
        (candidate for candidate in project_index_entries if candidate["filename"] == filename),
        None,
    )
    if matching_entry is None:
        raise ValueError(
            "python-distribution file is not present in the declared simple index: "
            f"{project_index_url} -> {filename}"
        )
    resolved_url = _url_without_fragment(matching_entry["url"])
    if resolved_url != _url_without_fragment(artifact_uri):
        raise ValueError(
            "python-distribution URI does not match the declared simple index entry: "
            f"{resolved_url} != {_url_without_fragment(artifact_uri)}"
        )
    index_sha256 = matching_entry["hashes"].get("sha256")
    sha256_matches_index = index_sha256 is None or index_sha256 == checksum_value
    if index_sha256 is not None and index_sha256 != checksum_value:
        raise ValueError(
            "python-distribution sha256 does not match the declared simple index entry: "
            f"{index_sha256} != {checksum_value}"
        )

    return {
        "artifact_id": artifact_id,
        "kind": "python-distribution",
        "verdict": "verified",
        "filename": filename,
        "uri": artifact_uri,
        "index_url": index_url,
        "project_name": project_name,
        "version": version,
        "checksum": {
            "algorithm": checksum_algorithm,
            "value": actual_checksum,
            "sidecar_verified": checksum_sidecar_verified,
        },
        "index_resolution": {
            "project_index_url": project_index_url,
            "resolved_url": resolved_url,
            "found_via": matching_entry["source"],
            "sha256_matches_index": sha256_matches_index,
        },
    }


def _verify_oci_image(
    artifact_entry: dict[str, Any],
    *,
    manifest_url: str,
) -> dict[str, Any]:
    artifact_id = _required_non_empty_string(artifact_entry, "artifact_id", source=manifest_url)
    registry = _required_non_empty_string(artifact_entry, "registry", source=manifest_url)
    repository = _required_non_empty_string(artifact_entry, "repository", source=manifest_url)
    declared_digest = _required_non_empty_string(artifact_entry, "digest", source=manifest_url).lower()
    uri = _required_non_empty_string(artifact_entry, "uri", source=manifest_url)
    image_ref = f"{registry}/{repository}@{declared_digest}"
    _inspected_registry, _inspected_repository, live_digest, live_platform_digests = _inspect_image_ref(image_ref)
    if live_digest != declared_digest:
        raise ValueError(
            "oci-image digest does not match the signed manifest: "
            f"{live_digest} != {declared_digest}"
        )
    expected_platform_digests = _platform_digests_from_manifest(artifact_entry, source=manifest_url)
    platform_digests_match = True
    if expected_platform_digests:
        expected_by_platform = {
            entry["platform"]: entry["digest"]
            for entry in expected_platform_digests
        }
        live_by_platform = {
            entry["platform"]: entry["digest"]
            for entry in live_platform_digests
        }
        if live_by_platform != expected_by_platform:
            raise ValueError(
                "oci-image platform digests do not match the signed manifest: "
                f"{live_by_platform} != {expected_by_platform}"
            )
    return {
        "artifact_id": artifact_id,
        "kind": "oci-image",
        "verdict": "verified",
        "uri": uri,
        "registry": registry,
        "repository": repository,
        "digest": declared_digest,
        "inspection": {
            "image_ref": image_ref,
            "digest_matches_manifest": True,
            "platform_digests_match": platform_digests_match,
            "platform_digests": live_platform_digests,
        },
    }


def _preferred_checksum_payload(
    artifact_entry: dict[str, Any],
    *,
    source: str,
) -> tuple[str, str, str | None]:
    return _required_checksum_payload(
        artifact_entry,
        source=source,
        algorithms=_SUPPORTED_CHECKSUMS,
    )


def _required_checksum_payload(
    artifact_entry: dict[str, Any],
    *,
    source: str,
    algorithms: tuple[str, ...],
) -> tuple[str, str, str | None]:
    checksums = artifact_entry.get("checksums")
    if not isinstance(checksums, dict):
        raise ValueError(f"manifest secondary artifact is missing checksums: {source}")
    for algorithm in algorithms:
        checksum_payload = checksums.get(algorithm)
        if not isinstance(checksum_payload, dict):
            continue
        checksum_value = _required_hex_digest(
            checksum_payload,
            "value",
            algorithm=algorithm,
            source=source,
        )
        checksum_uri = checksum_payload.get("uri")
        if checksum_uri is not None:
            if not isinstance(checksum_uri, str) or not checksum_uri.strip():
                raise ValueError(
                    f"manifest secondary artifact checksum uri must be a non-empty string: {source}"
                )
            return algorithm, checksum_value, checksum_uri.strip()
        return algorithm, checksum_value, None
    supported = ", ".join(algorithms)
    raise ValueError(
        f"manifest secondary artifact must declare one of {supported} checksums: {source}"
    )


def _verified_openpgp_signatures(
    artifact_entry: dict[str, Any],
    *,
    manifest_url: str,
    artifact_id: str,
    artifact_path: Path,
    work_dir: Path,
    verifier: GpgVerifier,
    allow_non_production_release_targets: bool,
    require_signature: bool,
) -> tuple[SignatureVerification, ...]:
    raw_signatures = artifact_entry.get("signatures")
    if raw_signatures is None:
        if require_signature:
            raise ValueError(f"manifest secondary artifact is missing signatures: {manifest_url}")
        return ()
    if not isinstance(raw_signatures, list):
        raise ValueError(f"manifest secondary artifact signatures must be a list: {manifest_url}")
    signature_uris: list[str] = []
    for signature_payload_entry in raw_signatures:
        if not isinstance(signature_payload_entry, dict):
            raise ValueError(f"manifest secondary artifact signatures must be objects: {manifest_url}")
        signature_type = _required_non_empty_string(
            signature_payload_entry,
            "type",
            source=manifest_url,
        )
        if signature_type != "openpgp-detached-ascii-armored":
            raise ValueError(
                f"unsupported secondary artifact signature type for {artifact_id}: {signature_type}"
            )
        signature_uris.append(
            _required_non_empty_string(signature_payload_entry, "uri", source=manifest_url)
        )
    if require_signature and not signature_uris:
        raise ValueError(
            f"manifest secondary artifact requires at least one OpenPGP detached signature: {artifact_id}"
        )
    verifications: list[SignatureVerification] = []
    for index, signature_uri in enumerate(signature_uris, start=1):
        validate_fetch_uri(
            signature_uri,
            allow_non_production_release_targets=allow_non_production_release_targets,
            purpose=f"secondary artifact signature URL for {artifact_id}",
        )
        signature_path = work_dir / f"{artifact_path.name}.{index}.asc"
        signature_path.write_bytes(read_uri_bytes(signature_uri))
        verifications.append(
            verifier.verify_detached(
                target_path=artifact_path,
                signature_path=signature_path,
            )
        )
    return tuple(verifications)


def _downloaded_inventory(
    artifact_entry: dict[str, Any],
    *,
    manifest_url: str,
    artifact_id: str,
    work_dir: Path,
    allow_non_production_release_targets: bool,
) -> _DownloadedInventory | None:
    raw_inventory = artifact_entry.get("inventory")
    if raw_inventory is None:
        return None
    if not isinstance(raw_inventory, dict):
        raise ValueError(f"manifest secondary artifact inventory must be an object: {manifest_url}")
    filename = _required_non_empty_string(raw_inventory, "filename", source=manifest_url)
    inventory_uri = _required_non_empty_string(raw_inventory, "uri", source=manifest_url)
    inventory_sha512 = _required_hex_digest(
        raw_inventory,
        "sha512",
        algorithm="sha512",
        source=manifest_url,
    )
    validate_fetch_uri(
        inventory_uri,
        allow_non_production_release_targets=allow_non_production_release_targets,
        purpose=f"secondary artifact inventory URL for {artifact_id}",
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = work_dir / filename
    inventory_path.write_bytes(read_uri_bytes(inventory_uri))
    actual_inventory_sha512 = checksum(inventory_path, "sha512")
    if actual_inventory_sha512 != inventory_sha512:
        raise ValueError(
            "secondary artifact inventory checksum does not match the signed manifest: "
            f"{artifact_id} {actual_inventory_sha512} != {inventory_sha512}"
        )
    inventory_payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    if not isinstance(inventory_payload, dict):
        raise ValueError(f"secondary artifact inventory must be a JSON object: {inventory_path}")
    return _DownloadedInventory(
        path=inventory_path,
        raw_payload=inventory_payload,
        report_payload={
            "filename": filename,
            "uri": inventory_uri,
            "sha512": actual_inventory_sha512,
        },
    )


def _validated_maven_inventory_payload(
    inventory_payload: dict[str, Any],
    *,
    artifact_id: str,
    staging_repository_id: str,
    base_url: str,
    source: str,
) -> dict[str, Any]:
    inventory_type = _required_non_empty_string(inventory_payload, "inventory_type", source=source)
    if inventory_type != "maven-repository":
        raise ValueError(f"unexpected maven inventory_type: {inventory_type}")
    if _required_non_empty_string(inventory_payload, "artifact_id", source=source) != artifact_id:
        raise ValueError("maven inventory artifact_id does not match the manifest secondary artifact")
    if _required_non_empty_string(
        inventory_payload,
        "staging_repository_id",
        source=source,
    ) != staging_repository_id:
        raise ValueError(
            "maven inventory staging_repository_id does not match the manifest secondary artifact"
        )
    if _required_non_empty_string(inventory_payload, "base_url", source=source) != base_url:
        raise ValueError("maven inventory base_url does not match the manifest secondary artifact")
    entries = inventory_payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"maven inventory entries must be a non-empty list: {source}")
    return inventory_payload


def _maven_inventory_entries(
    inventory_payload: dict[str, Any],
    *,
    source: str,
) -> dict[str, dict[str, Any]]:
    raw_entries = inventory_payload.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError(f"maven inventory entries must be a list: {source}")
    entries: dict[str, dict[str, Any]] = {}
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            raise ValueError(f"maven inventory entries must be objects: {source}")
        relative_path = _required_non_empty_string(raw_entry, "path", source=source)
        if relative_path in entries:
            raise ValueError(f"maven inventory path is duplicated: {relative_path}")
        size_bytes = raw_entry.get("size_bytes")
        if not isinstance(size_bytes, int) or size_bytes < 0:
            raise ValueError(f"maven inventory size_bytes must be a non-negative integer: {relative_path}")
        sha512_value = _required_hex_digest(
            raw_entry,
            "sha512",
            algorithm="sha512",
            source=source,
        )
        entries[relative_path] = {
            "size_bytes": size_bytes,
            "sha512": sha512_value,
        }
    return entries


def _verified_maven_repository_signatures(
    files_by_relative_path: dict[str, Any],
    *,
    cache: dict[str, bytes],
    remote_http_client: _RemoteHttpClient | None,
    verifier: GpgVerifier,
    work_dir: Path,
) -> tuple[tuple[str, str, SignatureVerification], ...]:
    verifications: list[tuple[str, str, SignatureVerification]] = []
    for relative_path in sorted(files_by_relative_path):
        if not relative_path.endswith(".asc"):
            continue
        target_relative_path = relative_path.removesuffix(".asc")
        target_file = files_by_relative_path.get(target_relative_path)
        if target_file is None:
            raise ValueError(
                f"maven repository detached signature has no matching target file: {relative_path}"
            )
        signature_file = files_by_relative_path[relative_path]
        target_local_path = work_dir / target_relative_path
        target_local_path.parent.mkdir(parents=True, exist_ok=True)
        target_local_path.write_bytes(
            _repository_file_bytes(
                target_file,
                cache=cache,
                remote_http_client=remote_http_client,
            )
        )
        signature_local_path = work_dir / relative_path
        signature_local_path.parent.mkdir(parents=True, exist_ok=True)
        signature_local_path.write_bytes(
            _repository_file_bytes(
                signature_file,
                cache=cache,
                remote_http_client=remote_http_client,
            )
        )
        verifications.append(
            (
                relative_path,
                target_relative_path,
                verifier.verify_detached(
                    target_path=target_local_path,
                    signature_path=signature_local_path,
                ),
            )
        )
    return tuple(verifications)


def _required_non_empty_string(payload: dict[str, Any], field_name: str, *, source: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"manifest field {field_name} must be a non-empty string: {source}")
    return value.strip()


def _required_hex_digest(
    payload: dict[str, Any],
    field_name: str,
    *,
    algorithm: str,
    source: str,
) -> str:
    value = _required_non_empty_string(payload, field_name, source=source).lower()
    expected_length = _CHECKSUM_LENGTHS[algorithm]
    if len(value) != expected_length or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(
            f"manifest secondary artifact {algorithm} must be a {expected_length}-character hex digest: {source}"
        )
    return value


def _safe_path_component(value: str) -> str:
    normalized = _SAFE_PATH_COMPONENT_PATTERN.sub("-", value).strip("-")
    return normalized or "secondary-artifact"


def _platform_digests_from_manifest(
    artifact_entry: dict[str, Any],
    *,
    source: str,
) -> list[dict[str, str]]:
    raw_entries = artifact_entry.get("platform_digests")
    if raw_entries is None:
        return []
    if not isinstance(raw_entries, list):
        raise ValueError(f"oci-image platform_digests must be a list: {source}")
    entries: list[dict[str, str]] = []
    seen_platforms: set[str] = set()
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            raise ValueError(f"oci-image platform_digests entries must be objects: {source}")
        platform = _required_non_empty_string(raw_entry, "platform", source=source)
        if platform in seen_platforms:
            raise ValueError(f"oci-image platform declared more than once in manifest: {platform}")
        seen_platforms.add(platform)
        digest_value = _required_non_empty_string(raw_entry, "digest", source=source).lower()
        entries.append({"platform": platform, "digest": digest_value})
    return entries


def _simple_index_project_url(index_url: str, project_name: str) -> str:
    normalized_project_name = _normalized_python_project_name(project_name)
    if index_url.endswith(".html") or index_url.endswith(".json"):
        return index_url
    return urljoin(index_url.rstrip("/") + "/", f"{normalized_project_name}/")


def _normalized_python_project_name(project_name: str) -> str:
    return re.sub(r"[-_.]+", "-", project_name).lower()


def _simple_index_entries(project_index_url: str) -> list[dict[str, Any]]:
    payload_bytes = _read_simple_index_bytes(project_index_url)
    stripped = payload_bytes.lstrip()
    if stripped.startswith(b"{"):
        return _simple_index_json_entries(project_index_url, payload_bytes)
    return _simple_index_html_entries(project_index_url, payload_bytes)


def _read_simple_index_bytes(project_index_url: str) -> bytes:
    parsed = urlparse(project_index_url)
    if parsed.scheme != "file":
        return read_uri_bytes(project_index_url)
    local_path = Path(unquote(parsed.path))
    if local_path.is_dir():
        for candidate_name in ("index.json", "index.html"):
            candidate_path = local_path / candidate_name
            if candidate_path.is_file():
                return candidate_path.read_bytes()
        raise ValueError(f"python-distribution simple index directory has no index file: {local_path}")
    return read_uri_bytes(project_index_url)


def _simple_index_json_entries(project_index_url: str, payload_bytes: bytes) -> list[dict[str, Any]]:
    payload = json.loads(payload_bytes.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"python-distribution simple index JSON must be an object: {project_index_url}")
    raw_files = payload.get("files")
    if not isinstance(raw_files, list):
        raise ValueError(f"python-distribution simple index JSON must contain a files list: {project_index_url}")
    entries: list[dict[str, Any]] = []
    for raw_file in raw_files:
        if not isinstance(raw_file, dict):
            continue
        filename = raw_file.get("filename")
        file_url = raw_file.get("url")
        if not isinstance(filename, str) or not filename.strip():
            continue
        if not isinstance(file_url, str) or not file_url.strip():
            continue
        hashes = raw_file.get("hashes")
        entries.append(
            {
                "filename": filename.strip(),
                "url": urljoin(project_index_url, file_url.strip()),
                "hashes": dict(hashes) if isinstance(hashes, dict) else {},
                "source": "simple-json",
            }
        )
    return entries


def _simple_index_html_entries(project_index_url: str, payload_bytes: bytes) -> list[dict[str, Any]]:
    parser = _SimpleIndexHtmlParser()
    parser.feed(payload_bytes.decode("utf-8"))
    entries: list[dict[str, Any]] = []
    for link in parser.links:
        href = link["href"]
        resolved_url = urljoin(project_index_url, href)
        parsed_url = urlparse(resolved_url)
        filename = Path(parsed_url.path).name
        if not filename:
            continue
        entries.append(
            {
                "filename": filename,
                "url": resolved_url,
                "hashes": _hashes_from_fragment(parsed_url.fragment),
                "source": "simple-html",
            }
        )
    return entries


def _hashes_from_fragment(fragment: str) -> dict[str, str]:
    if "=" not in fragment:
        return {}
    algorithm, digest_value = fragment.split("=", 1)
    normalized_algorithm = algorithm.strip().lower()
    normalized_digest = digest_value.strip().lower()
    if normalized_algorithm not in _CHECKSUM_LENGTHS:
        return {}
    if len(normalized_digest) != _CHECKSUM_LENGTHS[normalized_algorithm]:
        return {}
    if any(character not in "0123456789abcdef" for character in normalized_digest):
        return {}
    return {normalized_algorithm: normalized_digest}


def _url_without_fragment(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.fragment:
        return url
    return parsed._replace(fragment="").geturl()
