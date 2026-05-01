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

"""Generic secondary-file verifier kinds."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from apache_buildish_release_tooling.release.models import ComponentConfig, VerifyRcOverrideConfig
from apache_buildish_release_tooling.release.rc_vote_manifest import read_uri_bytes
from apache_buildish_release_tooling.release.source_artifact import checksum
from apache_buildish_release_tooling.release.verification.common import (
    GpgVerifier,
    SignatureVerification,
    signature_payload,
    validate_fetch_uri,
    verify_checksum_sidecar,
)

from .file_reproducibility import verify_host_direct_single_file_reproducibility
from .shared import (
    downloaded_inventory,
    preferred_checksum_payload,
    required_non_empty_string,
)


def verify_generic_file(
    artifact_entry: dict[str, Any],
    *,
    manifest_url: str,
    work_dir: Path,
    verifier: GpgVerifier,
    allow_non_production_release_targets: bool,
    require_signature: bool,
    component_config: ComponentConfig | None,
    project_root: Path | None,
    source_date_epoch: int | None,
    build_checks_allowed: bool,
    inspection_bundle_root: Path | None,
    profile_overrides: VerifyRcOverrideConfig | None,
) -> dict[str, Any]:
    artifact_id = required_non_empty_string(artifact_entry, "artifact_id", source=manifest_url)
    kind = required_non_empty_string(artifact_entry, "kind", source=manifest_url)
    filename = required_non_empty_string(artifact_entry, "filename", source=manifest_url)
    artifact_uri = required_non_empty_string(artifact_entry, "uri", source=manifest_url)
    issues: list[str] = []
    actual_checksum: str | None = None
    checksum_algorithm: str | None = None
    checksum_value: str | None = None
    checksum_uri: str | None = None
    checksum_matches_manifest = False
    checksum_sidecar_verified = False
    reproducibility_verification: dict[str, Any] | None = None
    work_dir.mkdir(parents=True, exist_ok=True)
    artifact_path: Path | None = None
    try:
        validate_fetch_uri(
            artifact_uri,
            allow_non_production_release_targets=allow_non_production_release_targets,
            purpose=f"secondary artifact URL for {artifact_id}",
        )
        downloaded_artifact_path = work_dir / filename
        downloaded_artifact_path.write_bytes(read_uri_bytes(artifact_uri))
        artifact_path = downloaded_artifact_path
    except Exception as exc:
        issues.append(str(exc))

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
                "secondary artifact checksum does not match the signed manifest: "
                f"{artifact_id} {actual_checksum} != {checksum_value}"
            )
        else:
            checksum_matches_manifest = True

    if (
        artifact_path is not None
        and checksum_algorithm is not None
        and checksum_uri is not None
    ):
        try:
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
        except Exception as exc:
            issues.append(str(exc))

    signature_verifications: tuple[SignatureVerification, ...] = ()
    if artifact_path is not None:
        signature_verifications, signature_issues = _signature_verifications_with_issues(
            artifact_entry,
            manifest_url=manifest_url,
            artifact_id=artifact_id,
            artifact_path=artifact_path,
            work_dir=work_dir,
            verifier=verifier,
            allow_non_production_release_targets=allow_non_production_release_targets,
            require_signature=require_signature,
        )
        issues.extend(signature_issues)

    inventory_verification = None
    try:
        inventory_verification = downloaded_inventory(
            artifact_entry,
            manifest_url=manifest_url,
            artifact_id=artifact_id,
            work_dir=work_dir,
            allow_non_production_release_targets=allow_non_production_release_targets,
        )
    except Exception as exc:
        issues.append(str(exc))

    if build_checks_allowed and artifact_entry.get("reproducibility") is not None:
        reproducibility_verification = _generic_file_reproducibility(
            artifact_entry,
            manifest_url=manifest_url,
            artifact_id=artifact_id,
            kind=kind,
            artifact_path=artifact_path,
            work_dir=work_dir / "reproducibility",
            component_config=component_config,
            project_root=project_root,
            source_date_epoch=source_date_epoch,
            inspection_bundle_root=inspection_bundle_root,
            profile_overrides=profile_overrides,
        )
        issues.extend(reproducibility_verification.get("issues", []))

    verification: dict[str, Any] = {
        "artifact_id": artifact_id,
        "kind": kind,
        "verdict": "failed" if issues else "verified",
        "issues": issues,
        "filename": filename,
        "uri": artifact_uri,
        "checksum": {
            "algorithm": checksum_algorithm,
            "value": actual_checksum,
            "matches_manifest": checksum_matches_manifest,
            "sidecar_verified": checksum_sidecar_verified,
        },
        "signatures": [signature_payload(signature) for signature in signature_verifications],
    }
    if inventory_verification is not None:
        verification["inventory"] = inventory_verification.report_payload
    if reproducibility_verification is not None:
        verification["reproducibility"] = reproducibility_verification
    return verification


def _generic_file_reproducibility(
    artifact_entry: dict[str, Any],
    *,
    manifest_url: str,
    artifact_id: str,
    kind: str,
    artifact_path: Path | None,
    work_dir: Path,
    component_config: ComponentConfig | None,
    project_root: Path | None,
    source_date_epoch: int | None,
    inspection_bundle_root: Path | None,
    profile_overrides: VerifyRcOverrideConfig | None,
) -> dict[str, Any]:
    return verify_host_direct_single_file_reproducibility(
        artifact_entry,
        manifest_url=manifest_url,
        artifact_id=artifact_id,
        kind=kind,
        artifact_path=artifact_path,
        work_dir=work_dir,
        component_config=component_config,
        project_root=project_root,
        source_date_epoch=source_date_epoch,
        inspection_bundle_root=inspection_bundle_root,
        subject_label="generic-file",
        profile_overrides=profile_overrides,
    )


def _signature_verifications_with_issues(
    artifact_entry: dict[str, Any],
    *,
    manifest_url: str,
    artifact_id: str,
    artifact_path: Path,
    work_dir: Path,
    verifier: GpgVerifier,
    allow_non_production_release_targets: bool,
    require_signature: bool,
) -> tuple[tuple[SignatureVerification, ...], list[str]]:
    raw_signatures = artifact_entry.get("signatures")
    if raw_signatures is None:
        if require_signature:
            return (), [f"manifest secondary artifact is missing signatures: {manifest_url}"]
        return (), []
    if not isinstance(raw_signatures, list):
        return (), [f"manifest secondary artifact signatures must be a list: {manifest_url}"]
    issues: list[str] = []
    verifications: list[SignatureVerification] = []
    valid_signature_count = 0
    for index, signature_payload_entry in enumerate(raw_signatures, start=1):
        if not isinstance(signature_payload_entry, dict):
            issues.append(f"manifest secondary artifact signatures must be objects: {manifest_url}")
            continue
        try:
            signature_type = required_non_empty_string(
                signature_payload_entry,
                "type",
                source=manifest_url,
            )
        except Exception as exc:
            issues.append(str(exc))
            continue
        if signature_type != "openpgp-detached-ascii-armored":
            issues.append(
                f"unsupported secondary artifact signature type for {artifact_id}: {signature_type}"
            )
            continue
        try:
            signature_uri = required_non_empty_string(
                signature_payload_entry,
                "uri",
                source=manifest_url,
            )
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
            valid_signature_count += 1
        except Exception as exc:
            issues.append(str(exc))
    if require_signature and valid_signature_count == 0:
        issues.append(
            f"manifest secondary artifact requires at least one OpenPGP detached signature: {artifact_id}"
        )
    return tuple(verifications), issues
