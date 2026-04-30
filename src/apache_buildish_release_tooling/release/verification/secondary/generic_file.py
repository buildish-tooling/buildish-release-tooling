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

from apache_buildish_release_tooling.release.models import ComponentConfig
from apache_buildish_release_tooling.release.rc_vote_manifest import read_uri_bytes
from apache_buildish_release_tooling.release.source_artifact import checksum
from apache_buildish_release_tooling.release.verification.common import (
    GpgVerifier,
    SignatureVerification,
    signature_payload,
    validate_fetch_uri,
    verify_checksum_sidecar,
)
from apache_buildish_release_tooling.release.verification.rebuild import (
    resolve_rebuild_profile,
    run_host_direct_profile,
)

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
) -> dict[str, Any]:
    raw_reproducibility = artifact_entry.get("reproducibility")
    if not isinstance(raw_reproducibility, dict):
        return {
            "profile_id": "n/a",
            "verdict": "failed",
            "comparison_mode": "exact-bytes",
            "recipe_source": "canonical-profile",
            "execution_backend": "host-direct",
            "output_paths": [],
            "matches_remote_bytes": None,
            "issues": [f"manifest secondary artifact does not declare a reproducibility profile: {artifact_id}"],
        }
    profile_id = required_non_empty_string(raw_reproducibility, "profile_id", source=manifest_url)
    issues: list[str] = []
    output_paths: list[str] = []
    matches_remote_bytes: bool | None = None
    comparison_mode = "exact-bytes"
    if component_config is None:
        issues.append(
            f"build-based reproducibility for {artifact_id} requires --component-config to resolve profile {profile_id!r}"
        )
    if project_root is None:
        issues.append(
            f"build-based reproducibility for {artifact_id} requires one verified source checkout"
        )
    if artifact_path is None:
        issues.append(
            f"build-based reproducibility for {artifact_id} requires the staged artifact bytes"
        )
    profile = None
    if not issues and component_config is not None:
        try:
            profile = resolve_rebuild_profile(
                component_config,
                profile_id,
                expected_kinds=(kind,),
            )
            comparison_mode = str(profile.comparison.get("mode", comparison_mode))
        except Exception as exc:
            issues.append(str(exc))
    if not issues and profile is not None and project_root is not None and artifact_path is not None:
        try:
            build_result = run_host_direct_profile(
                profile_id=profile_id,
                profile=profile,
                project_root=project_root,
                work_dir=work_dir,
                source_date_epoch=source_date_epoch,
            )
            output_paths = [
                str(path.relative_to(project_root))
                for path in build_result.output_paths
            ]
            if len(build_result.output_paths) != 1:
                raise ValueError(
                    f"generic-file reproducibility profile {profile_id!r} must produce exactly one output file"
                )
            built_artifact_path = build_result.output_paths[0]
            matches_remote_bytes = built_artifact_path.read_bytes() == artifact_path.read_bytes()
            if not matches_remote_bytes:
                raise ValueError(
                    f"generic-file reproducibility output does not match the staged artifact bytes: {artifact_id}"
                )
        except Exception as exc:
            issues.append(str(exc))
    return {
        "profile_id": profile_id,
        "verdict": "failed" if issues else "verified",
        "comparison_mode": comparison_mode,
        "recipe_source": "canonical-profile",
        "execution_backend": "host-direct",
        "output_paths": output_paths,
        "matches_remote_bytes": matches_remote_bytes,
        "issues": issues,
    }


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
