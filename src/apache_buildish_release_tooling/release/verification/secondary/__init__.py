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

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from apache_buildish_release_tooling.release.contracts import RcVoteManifestReadV1
from apache_buildish_release_tooling.release.models import ComponentConfig
from apache_buildish_release_tooling.release.progress import ProgressReporter
from apache_buildish_release_tooling.release.verification.common import (
    GpgVerifier,
    emit_detail,
    emit_failure,
    emit_info,
    emit_section,
    emit_success,
    emit_warning,
)

from .generic_file import verify_generic_file
from .maven_repository import verify_maven_repository
from .npm_package import verify_npm_package
from .oci_image import verify_oci_image
from .python_distribution import verify_python_distribution
from .shared import required_non_empty_string, safe_path_component, secondary_artifact_entries

INVALID_SECONDARY_ARTIFACT_KIND = "_invalid-secondary-artifact-entry"

__all__ = ["INVALID_SECONDARY_ARTIFACT_KIND", "verify_secondary_artifacts"]


def verify_secondary_artifacts(
    manifest_payload: RcVoteManifestReadV1 | dict[str, Any],
    *,
    manifest_url: str,
    work_dir: Path,
    verifier: GpgVerifier,
    allow_non_production_release_targets: bool,
    progress_reporter: ProgressReporter,
    component_config: ComponentConfig | None,
    project_root: Path | None,
    source_date_epoch: int | None,
    build_checks_allowed: bool,
    inspection_bundle_root: Path | None,
) -> list[dict[str, Any]]:
    """Verify all supported secondary artifacts declared in the signed vote manifest."""

    work_dir.mkdir(parents=True, exist_ok=True)
    artifact_entries = secondary_artifact_entries(manifest_payload, source=manifest_url)
    total_artifacts = len(artifact_entries)
    emit_section(progress_reporter, "Secondary Artifacts")
    if total_artifacts == 0:
        emit_warning(progress_reporter, "No secondary artifacts declared in the signed manifest")
        return []
    verifications: list[dict[str, Any]] = []
    for index, artifact_entry in enumerate(artifact_entries, start=1):
        artifact_label = _artifact_label(artifact_entry, index=index)
        declared_kind = _declared_kind(artifact_entry)
        artifact_work_dir = work_dir / f"{index:02d}-{safe_path_component(artifact_label)}"
        emit_section(progress_reporter, f"Secondary Artifact {index}/{total_artifacts}: {artifact_label}")
        emit_detail(progress_reporter, "Kind", declared_kind or "n/a")
        try:
            artifact_payload = _artifact_payload(artifact_entry, manifest_url=manifest_url)
            required_non_empty_string(
                artifact_payload,
                "artifact_id",
                source=manifest_url,
            )
            kind = required_non_empty_string(artifact_payload, "kind", source=manifest_url)
            if kind == "generic-file":
                verification = verify_generic_file(
                    artifact_payload,
                    manifest_url=manifest_url,
                    work_dir=artifact_work_dir,
                    verifier=verifier,
                    allow_non_production_release_targets=allow_non_production_release_targets,
                    require_signature=False,
                    component_config=component_config,
                    project_root=project_root,
                    source_date_epoch=source_date_epoch,
                    build_checks_allowed=build_checks_allowed,
                    inspection_bundle_root=inspection_bundle_root,
                )
            elif kind == "generic-file-with-openpgp":
                verification = verify_generic_file(
                    artifact_payload,
                    manifest_url=manifest_url,
                    work_dir=artifact_work_dir,
                    verifier=verifier,
                    allow_non_production_release_targets=allow_non_production_release_targets,
                    require_signature=True,
                    component_config=component_config,
                    project_root=project_root,
                    source_date_epoch=source_date_epoch,
                    build_checks_allowed=build_checks_allowed,
                    inspection_bundle_root=inspection_bundle_root,
                )
            elif kind == "maven-repository":
                verification = verify_maven_repository(
                    artifact_payload,
                    manifest_url=manifest_url,
                    work_dir=artifact_work_dir,
                    verifier=verifier,
                    allow_non_production_release_targets=allow_non_production_release_targets,
                    progress_reporter=progress_reporter,
                    component_config=component_config,
                    project_root=project_root,
                    source_date_epoch=source_date_epoch,
                    build_checks_allowed=build_checks_allowed,
                    inspection_bundle_root=inspection_bundle_root,
                )
            elif kind == "python-distribution":
                verification = verify_python_distribution(
                    artifact_payload,
                    manifest_url=manifest_url,
                    work_dir=artifact_work_dir,
                    allow_non_production_release_targets=allow_non_production_release_targets,
                    component_config=component_config,
                    project_root=project_root,
                    source_date_epoch=source_date_epoch,
                    build_checks_allowed=build_checks_allowed,
                    inspection_bundle_root=inspection_bundle_root,
                )
            elif kind == "npm-package":
                verification = verify_npm_package(
                    artifact_payload,
                    manifest_url=manifest_url,
                    work_dir=artifact_work_dir,
                    allow_non_production_release_targets=allow_non_production_release_targets,
                    component_config=component_config,
                    project_root=project_root,
                    source_date_epoch=source_date_epoch,
                    build_checks_allowed=build_checks_allowed,
                    inspection_bundle_root=inspection_bundle_root,
                )
            elif kind == "oci-image":
                verification = verify_oci_image(
                    artifact_payload,
                    manifest_url=manifest_url,
                    work_dir=artifact_work_dir,
                    component_config=component_config,
                    project_root=project_root,
                    source_date_epoch=source_date_epoch,
                    build_checks_allowed=build_checks_allowed,
                    inspection_bundle_root=inspection_bundle_root,
                )
            else:
                raise ValueError(f"unsupported secondary artifact kind in manifest: {kind}")
        except Exception as exc:
            verification = {
                "artifact_id": artifact_label,
                "kind": INVALID_SECONDARY_ARTIFACT_KIND,
                "declared_kind": declared_kind,
                "verdict": "failed",
                "issues": [str(exc)],
            }
        _emit_secondary_artifact_summary(progress_reporter, verification)
        verifications.append(verification)
    return verifications


def _artifact_label(artifact_entry: Any, *, index: int) -> str:
    if isinstance(artifact_entry, BaseModel):
        raw_artifact_id = getattr(artifact_entry, "artifact_id", None)
        if isinstance(raw_artifact_id, str) and raw_artifact_id.strip():
            return raw_artifact_id.strip()
    if isinstance(artifact_entry, dict):
        raw_artifact_id = artifact_entry.get("artifact_id")
        if isinstance(raw_artifact_id, str) and raw_artifact_id.strip():
            return raw_artifact_id.strip()
    return f"secondary-artifact-{index}"


def _declared_kind(artifact_entry: Any) -> str | None:
    if isinstance(artifact_entry, BaseModel):
        raw_kind = getattr(artifact_entry, "kind", None)
        if isinstance(raw_kind, str) and raw_kind.strip():
            return raw_kind.strip()
    if not isinstance(artifact_entry, dict):
        return None
    raw_kind = artifact_entry.get("kind")
    if not isinstance(raw_kind, str) or not raw_kind.strip():
        return None
    return raw_kind.strip()


def _artifact_payload(artifact_entry: Any, *, manifest_url: str) -> dict[str, Any]:
    if isinstance(artifact_entry, BaseModel):
        return artifact_entry.model_dump(mode="json", exclude_none=True)
    if isinstance(artifact_entry, dict):
        return dict(artifact_entry)
    raise ValueError(f"manifest secondary artifact entry must be an object: {manifest_url}")


def _emit_secondary_artifact_summary(
    progress_reporter: ProgressReporter,
    verification: dict[str, Any],
) -> None:
    kind = verification["kind"]
    issues = [str(issue) for issue in verification.get("issues", [])]
    if kind == INVALID_SECONDARY_ARTIFACT_KIND:
        for issue in issues:
            emit_failure(progress_reporter, issue)
        return
    if kind in {"generic-file", "generic-file-with-openpgp"}:
        checksum_payload = verification.get("checksum")
        emit_detail(progress_reporter, "File", verification.get("filename", "n/a"))
        emit_detail(progress_reporter, "URL", verification.get("uri", "n/a"))
        if (
            isinstance(checksum_payload, dict)
            and checksum_payload.get("matches_manifest")
            and checksum_payload.get("algorithm")
            and checksum_payload.get("value")
        ):
            emit_success(
                progress_reporter,
                f"Verified checksum: {checksum_payload['algorithm']}:{checksum_payload['value']}",
            )
        if isinstance(checksum_payload, dict) and checksum_payload.get("sidecar_verified"):
            emit_success(progress_reporter, "Verified checksum sidecar")
        signature_verifications = verification.get("signatures", [])
        for signature_verification in signature_verifications:
            emit_success(
                progress_reporter,
                f"Verified signature: {signature_verification['signer_fingerprint']}",
            )
        inventory_payload = verification.get("inventory")
        if isinstance(inventory_payload, dict):
            emit_success(
                progress_reporter,
                f"Verified inventory: {inventory_payload['filename']}",
            )
        reproducibility_payload = verification.get("reproducibility")
        if isinstance(reproducibility_payload, dict):
            emit_detail(
                progress_reporter,
                "Reproducibility profile",
                str(reproducibility_payload.get("profile_id", "n/a")),
            )
            for output_path in reproducibility_payload.get("output_paths", []):
                emit_detail(progress_reporter, "Rebuild output", str(output_path))
            if reproducibility_payload.get("matches_remote_bytes") is True:
                emit_success(progress_reporter, "Verified rebuilt artifact matches staged bytes")
        for issue in issues:
            emit_failure(progress_reporter, issue)
        return
    if kind == "maven-repository":
        inventory_payload = verification["inventory"]
        live_repository = verification["live_repository"]
        emit_detail(progress_reporter, "Base URL", verification["base_url"])
        if isinstance(inventory_payload, dict):
            emit_detail(progress_reporter, "Inventory", inventory_payload["filename"])
        if live_repository.get("matches_signed_inventory") and live_repository.get("entry_count") is not None:
            emit_success(
                progress_reporter,
                f"Verified live repository against signed inventory: {live_repository['entry_count']} entries",
            )
        signature_verifications = live_repository.get("signature_verifications", [])
        if signature_verifications:
            emit_info(
                progress_reporter,
                f"Verified detached signatures for {len(signature_verifications)} repository files",
            )
        reproducibility_payload = verification.get("reproducibility")
        if isinstance(reproducibility_payload, dict):
            emit_detail(
                progress_reporter,
                "Reproducibility profile",
                str(reproducibility_payload.get("profile_id", "n/a")),
            )
            for output_path in reproducibility_payload.get("output_paths", []):
                emit_detail(progress_reporter, "Rebuild output", str(output_path))
            if reproducibility_payload.get("matches_remote_bytes") is True:
                emit_success(
                    progress_reporter,
                    "Verified rebuilt repository matches the staged repository policy",
                )
        for issue in issues:
            emit_failure(progress_reporter, issue)
        return
    if kind == "python-distribution":
        checksum_payload = verification["checksum"]
        index_resolution = verification["index_resolution"]
        emit_detail(progress_reporter, "Project", f"{verification['project_name']} {verification['version']}")
        emit_detail(progress_reporter, "File", verification["filename"])
        emit_detail(progress_reporter, "URL", verification["uri"])
        emit_detail(progress_reporter, "Simple index", index_resolution["project_index_url"])
        if checksum_payload.get("matches_manifest") and checksum_payload.get("algorithm") and checksum_payload.get("value"):
            emit_success(
                progress_reporter,
                f"Verified checksum: {checksum_payload['algorithm']}:{checksum_payload['value']}",
            )
        if checksum_payload["sidecar_verified"]:
            emit_success(progress_reporter, "Verified checksum sidecar")
        if index_resolution.get("resolved_url") is not None:
            emit_success(progress_reporter, "Verified simple index entry")
        reproducibility_payload = verification.get("reproducibility")
        if isinstance(reproducibility_payload, dict):
            emit_detail(
                progress_reporter,
                "Reproducibility profile",
                str(reproducibility_payload.get("profile_id", "n/a")),
            )
            for output_path in reproducibility_payload.get("output_paths", []):
                emit_detail(progress_reporter, "Rebuild output", str(output_path))
            if reproducibility_payload.get("matches_remote_bytes") is True:
                emit_success(progress_reporter, "Verified rebuilt artifact matches staged bytes")
        for issue in issues:
            emit_failure(progress_reporter, issue)
        return
    if kind == "oci-image":
        inspection = verification["inspection"]
        emit_detail(progress_reporter, "Image", inspection["image_ref"])
        if inspection.get("digest_matches_manifest"):
            emit_success(progress_reporter, f"Verified digest: {verification['digest']}")
        if inspection.get("platform_digests_match"):
            emit_success(progress_reporter, "Verified platform digests")
        reproducibility_payload = verification.get("reproducibility")
        if isinstance(reproducibility_payload, dict):
            emit_detail(
                progress_reporter,
                "Reproducibility profile",
                str(reproducibility_payload.get("profile_id", "n/a")),
            )
            for output_path in reproducibility_payload.get("output_paths", []):
                emit_detail(progress_reporter, "Rebuild output", str(output_path))
            if reproducibility_payload.get("matches_remote_bytes") is True:
                emit_success(progress_reporter, "Verified rebuilt image digests match the staged image")
        for issue in issues:
            emit_failure(progress_reporter, issue)
        return
    if kind == "npm-package":
        checksum_payload = verification["checksum"]
        registry_resolution = verification["registry_resolution"]
        emit_detail(progress_reporter, "Package", f"{verification['package_name']} {verification['version']}")
        emit_detail(progress_reporter, "Registry", verification["registry_url"])
        emit_detail(progress_reporter, "Tarball", verification["uri"])
        if verification["integrity"].get("matches_downloaded_bytes"):
            emit_success(progress_reporter, f"Verified integrity: {verification['integrity']['value']}")
        if checksum_payload.get("matches_manifest") and checksum_payload.get("algorithm") and checksum_payload.get("value"):
            emit_success(
                progress_reporter,
                f"Verified checksum: {checksum_payload['algorithm']}:{checksum_payload['value']}",
            )
        if checksum_payload["sidecar_verified"]:
            emit_success(progress_reporter, "Verified checksum sidecar")
        if registry_resolution.get("metadata_url") is not None:
            emit_success(
                progress_reporter,
                f"Verified registry metadata: {registry_resolution['metadata_url']}",
            )
        reproducibility_payload = verification.get("reproducibility")
        if isinstance(reproducibility_payload, dict):
            emit_detail(
                progress_reporter,
                "Reproducibility profile",
                str(reproducibility_payload.get("profile_id", "n/a")),
            )
            for output_path in reproducibility_payload.get("output_paths", []):
                emit_detail(progress_reporter, "Rebuild output", str(output_path))
            if reproducibility_payload.get("matches_remote_bytes") is True:
                emit_success(progress_reporter, "Verified rebuilt artifact matches staged bytes")
        for issue in issues:
            emit_failure(progress_reporter, issue)
        return
    raise ValueError(
        "unsupported secondary artifact kind for console reporting: "
        f"{verification['artifact_id']} ({kind})"
    )
