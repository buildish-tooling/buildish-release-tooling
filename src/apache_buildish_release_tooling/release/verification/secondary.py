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

import re
from pathlib import Path
from typing import Any

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
    inventory_verification = _verified_inventory(
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
        verification["inventory"] = inventory_verification
    return verification


def _preferred_checksum_payload(
    artifact_entry: dict[str, Any],
    *,
    source: str,
) -> tuple[str, str, str | None]:
    checksums = artifact_entry.get("checksums")
    if not isinstance(checksums, dict):
        raise ValueError(f"manifest secondary artifact is missing checksums: {source}")
    for algorithm in _SUPPORTED_CHECKSUMS:
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
    supported = ", ".join(_SUPPORTED_CHECKSUMS)
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


def _verified_inventory(
    artifact_entry: dict[str, Any],
    *,
    manifest_url: str,
    artifact_id: str,
    work_dir: Path,
    allow_non_production_release_targets: bool,
) -> dict[str, Any] | None:
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
    inventory_path = work_dir / filename
    inventory_path.write_bytes(read_uri_bytes(inventory_uri))
    actual_inventory_sha512 = checksum(inventory_path, "sha512")
    if actual_inventory_sha512 != inventory_sha512:
        raise ValueError(
            "secondary artifact inventory checksum does not match the signed manifest: "
            f"{artifact_id} {actual_inventory_sha512} != {inventory_sha512}"
        )
    return {
        "filename": filename,
        "uri": inventory_uri,
        "sha512": actual_inventory_sha512,
    }


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
