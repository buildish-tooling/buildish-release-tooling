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

"""Shared helpers for secondary-artifact verifier kinds."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from buildish_release_tooling.release.contracts import (
    AnySecondaryArtifact,
    InventoryVerificationReport,
    SecondaryArtifactChecksumsRead,
    SecondaryArtifactEnvelopeRead,
    SecondaryArtifactInventoryRead,
    SecondaryArtifactSignatureReferenceRead,
    Sha256Checksums,
    Sha512Checksums,
    SignatureReference,
    SupplementalInventoryReference,
)
from buildish_release_tooling.release.path_validation import validate_simple_filename
from buildish_release_tooling.release.rc_vote_manifest import (
    DEFAULT_MANIFEST_MAX_BYTES,
    DEFAULT_SIGNATURE_MAX_BYTES,
    download_uri_to_path,
)
from buildish_release_tooling.release.source_artifact import checksum
from buildish_release_tooling.release.verification.common import (
    GpgVerifier,
    SignatureVerification,
    validate_fetch_uri,
)
from buildish_release_tooling.release.verification.secondary.readers import _RawInventoryRead
from buildish_release_tooling.shared.parsing import read_pydantic_json_file_bounded

SUPPORTED_CHECKSUMS = ("sha512", "sha256")
CHECKSUM_LENGTHS = {
    "sha256": 64,
    "sha512": 128,
}
SAFE_PATH_COMPONENT_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class DownloadedInventory:
    """One verified inventory attachment plus its parsed JSON payload."""

    path: Path
    raw_payload: _RawInventoryRead
    report_payload: InventoryVerificationReport
def preferred_checksum_payload(
    artifact_entry: AnySecondaryArtifact | SecondaryArtifactEnvelopeRead,
    *,
    source: str,
) -> tuple[str, str, str | None]:
    return required_checksum_payload(
        artifact_entry,
        source=source,
        algorithms=SUPPORTED_CHECKSUMS,
    )


def required_checksum_payload(
    artifact_entry: AnySecondaryArtifact | SecondaryArtifactEnvelopeRead,
    *,
    source: str,
    algorithms: tuple[str, ...],
) -> tuple[str, str, str | None]:
    checksums = _checksums_payload(artifact_entry)
    if checksums is None:
        raise ValueError(f"manifest secondary artifact is missing checksums: {source}")
    for algorithm in algorithms:
        checksum_payload = getattr(checksums, algorithm, None)
        if checksum_payload is None:
            continue
        checksum_value = required_hex_digest(
            checksum_payload.value,
            algorithm=algorithm,
            source=source,
        )
        checksum_uri = checksum_payload.uri
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


def verified_openpgp_signatures(
    artifact_entry: AnySecondaryArtifact | SecondaryArtifactEnvelopeRead,
    *,
    manifest_url: str,
    artifact_id: str,
    artifact_path: Path,
    work_dir: Path,
    verifier: GpgVerifier,
    allow_non_production_release_targets: bool,
    require_signature: bool,
) -> tuple[SignatureVerification, ...]:
    raw_signatures = _signature_references(artifact_entry)
    if raw_signatures is None:
        if require_signature:
            raise ValueError(f"manifest secondary artifact is missing signatures: {manifest_url}")
        return ()
    signature_uris: list[str] = []
    for signature_payload_entry in raw_signatures:
        signature_type = required_non_empty_string(
            signature_payload_entry.type,
            field_name="type",
            source=manifest_url,
        )
        if signature_type != "openpgp-detached-ascii-armored":
            raise ValueError(
                f"unsupported secondary artifact signature type for {artifact_id}: {signature_type}"
            )
        signature_uris.append(
            required_non_empty_string(
                signature_payload_entry.uri,
                field_name="uri",
                source=manifest_url,
            )
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
        download_uri_to_path(
            signature_uri,
            signature_path,
            max_bytes=DEFAULT_SIGNATURE_MAX_BYTES,
        )
        verifications.append(
            verifier.verify_detached(
                target_path=artifact_path,
                signature_path=signature_path,
            )
        )
    return tuple(verifications)


def downloaded_inventory(
    artifact_entry: AnySecondaryArtifact | SecondaryArtifactEnvelopeRead,
    *,
    manifest_url: str,
    artifact_id: str,
    work_dir: Path,
    allow_non_production_release_targets: bool,
) -> DownloadedInventory | None:
    raw_inventory = _inventory_reference(artifact_entry)
    if raw_inventory is None:
        return None
    filename = validate_simple_filename(
        required_non_empty_string(raw_inventory.filename, field_name="filename", source=manifest_url),
        field_name="secondary artifact inventory filename",
    )
    inventory_uri = required_non_empty_string(raw_inventory.uri, field_name="uri", source=manifest_url)
    inventory_sha512 = required_hex_digest(
        raw_inventory.sha512,
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
    download_uri_to_path(inventory_uri, inventory_path, max_bytes=DEFAULT_MANIFEST_MAX_BYTES)
    actual_inventory_sha512 = checksum(inventory_path, "sha512")
    if actual_inventory_sha512 != inventory_sha512:
        raise ValueError(
            "secondary artifact inventory checksum does not match the signed manifest: "
            f"{artifact_id} {actual_inventory_sha512} != {inventory_sha512}"
        )
    inventory_payload = read_pydantic_json_file_bounded(
        _RawInventoryRead,
        inventory_path,
        max_bytes=DEFAULT_MANIFEST_MAX_BYTES,
    )
    return DownloadedInventory(
        path=inventory_path,
        raw_payload=inventory_payload,
        report_payload=InventoryVerificationReport(
            filename=filename,
            uri=inventory_uri,
            sha512=actual_inventory_sha512,
        ),
    )


def _checksums_payload(
    artifact_entry: AnySecondaryArtifact | SecondaryArtifactEnvelopeRead,
) -> Sha512Checksums | Sha256Checksums | SecondaryArtifactChecksumsRead | None:
    raw_checksums = getattr(artifact_entry, "checksums", None)
    if isinstance(
        raw_checksums,
        Sha512Checksums | Sha256Checksums | SecondaryArtifactChecksumsRead,
    ):
        return raw_checksums
    return None


def _signature_references(
    artifact_entry: AnySecondaryArtifact | SecondaryArtifactEnvelopeRead,
) -> list[SignatureReference] | list[SecondaryArtifactSignatureReferenceRead] | None:
    raw_signatures = getattr(artifact_entry, "signatures", None)
    if isinstance(raw_signatures, list):
        return raw_signatures
    return None


def _inventory_reference(
    artifact_entry: AnySecondaryArtifact | SecondaryArtifactEnvelopeRead,
) -> SupplementalInventoryReference | SecondaryArtifactInventoryRead | None:
    raw_inventory = getattr(artifact_entry, "inventory", None)
    if isinstance(raw_inventory, SupplementalInventoryReference | SecondaryArtifactInventoryRead):
        return raw_inventory
    return None


def required_non_empty_string(value: object, *, field_name: str, source: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"manifest field {field_name} must be a non-empty string: {source}")
    return value.strip()


def required_hex_digest(
    value: object,
    *,
    algorithm: str,
    source: str,
) -> str:
    normalized = required_non_empty_string(value, field_name=algorithm, source=source).lower()
    expected_length = CHECKSUM_LENGTHS[algorithm]
    if (
        len(normalized) != expected_length
        or any(character not in "0123456789abcdef" for character in normalized)
    ):
        raise ValueError(
            f"manifest secondary artifact {algorithm} must be a {expected_length}-character hex digest: {source}"
        )
    return normalized


def safe_path_component(value: str) -> str:
    normalized = SAFE_PATH_COMPONENT_PATTERN.sub("-", value).strip("-")
    return normalized or "secondary-artifact"


def url_without_fragment(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.fragment:
        return url
    return parsed._replace(fragment="").geturl()
