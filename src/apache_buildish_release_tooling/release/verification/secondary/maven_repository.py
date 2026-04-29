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

"""Maven repository secondary-artifact verification."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from apache_buildish_release_tooling.release.artifact_registration.kinds.maven_repository import (
    _RemoteHttpClient,
    _inventory_worker_count,
    _repository_file_bytes,
    _repository_files,
    _validated_repository_root,
)
from apache_buildish_release_tooling.release.progress import ProgressReporter
from apache_buildish_release_tooling.release.verification.common import (
    GpgVerifier,
    SignatureVerification,
    signature_payload,
    validate_fetch_uri,
)

from .shared import (
    downloaded_inventory,
    required_hex_digest,
    required_non_empty_string,
)


def verify_maven_repository(
    artifact_entry: dict[str, Any],
    *,
    manifest_url: str,
    work_dir: Path,
    verifier: GpgVerifier,
    allow_non_production_release_targets: bool,
) -> dict[str, Any]:
    artifact_id = required_non_empty_string(artifact_entry, "artifact_id", source=manifest_url)
    staging_repository_id = required_non_empty_string(
        artifact_entry,
        "staging_repository_id",
        source=manifest_url,
    )
    base_url = required_non_empty_string(artifact_entry, "base_url", source=manifest_url)
    validate_fetch_uri(
        base_url,
        allow_non_production_release_targets=allow_non_production_release_targets,
        purpose=f"maven repository base URL for {artifact_id}",
    )
    _validated_repository_root(base_url, staging_repository_id)
    fetched_inventory = downloaded_inventory(
        artifact_entry,
        manifest_url=manifest_url,
        artifact_id=artifact_id,
        work_dir=work_dir,
        allow_non_production_release_targets=allow_non_production_release_targets,
    )
    if fetched_inventory is None:
        raise ValueError(f"manifest maven-repository artifact is missing inventory: {artifact_id}")
    inventory_payload = _validated_maven_inventory_payload(
        fetched_inventory.raw_payload,
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

    inventory_report_payload = dict(fetched_inventory.report_payload)
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


def _validated_maven_inventory_payload(
    inventory_payload: dict[str, Any],
    *,
    artifact_id: str,
    staging_repository_id: str,
    base_url: str,
    source: str,
) -> dict[str, Any]:
    inventory_type = required_non_empty_string(inventory_payload, "inventory_type", source=source)
    if inventory_type != "maven-repository":
        raise ValueError(f"unexpected maven inventory_type: {inventory_type}")
    if required_non_empty_string(inventory_payload, "artifact_id", source=source) != artifact_id:
        raise ValueError("maven inventory artifact_id does not match the manifest secondary artifact")
    if required_non_empty_string(
        inventory_payload,
        "staging_repository_id",
        source=source,
    ) != staging_repository_id:
        raise ValueError(
            "maven inventory staging_repository_id does not match the manifest secondary artifact"
        )
    if required_non_empty_string(inventory_payload, "base_url", source=source) != base_url:
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
        relative_path = required_non_empty_string(raw_entry, "path", source=source)
        if relative_path in entries:
            raise ValueError(f"maven inventory path is duplicated: {relative_path}")
        size_bytes = raw_entry.get("size_bytes")
        if not isinstance(size_bytes, int) or size_bytes < 0:
            raise ValueError(f"maven inventory size_bytes must be a non-negative integer: {relative_path}")
        sha512_value = required_hex_digest(
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
