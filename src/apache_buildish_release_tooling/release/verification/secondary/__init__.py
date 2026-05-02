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

from apache_buildish_release_tooling.release.contracts import (
    ArtifactReproducibilityBuildOverrideReport,
    ArtifactReproducibilityReport,
    AnySecondaryArtifactVerification,
    GenericFileVerificationReport,
    GenericFileSecondaryArtifact,
    GenericFileWithOpenPgpSecondaryArtifact,
    InvalidSecondaryArtifactVerificationReport,
    MavenRepositoryVerificationReport,
    MavenRepositorySecondaryArtifact,
    NpmPackageVerificationReport,
    NpmPackageSecondaryArtifact,
    OciImageVerificationReport,
    OciImageSecondaryArtifact,
    PythonDistributionVerificationReport,
    PythonDistributionSecondaryArtifact,
    RcVoteManifestReadV1,
    StrictSecondaryArtifactAdapter,
)
from apache_buildish_release_tooling.release.models import ComponentConfig, VerifyRcOverrideConfig
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
from .shared import SecondaryArtifactEntry, safe_path_component, secondary_artifact_entries
from .shared import MalformedSecondaryArtifactEntry

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
    profile_overrides: VerifyRcOverrideConfig | None,
) -> list[AnySecondaryArtifactVerification]:
    """Verify all supported secondary artifacts declared in the signed vote manifest."""

    work_dir.mkdir(parents=True, exist_ok=True)
    artifact_entries = secondary_artifact_entries(manifest_payload, source=manifest_url)
    total_artifacts = len(artifact_entries)
    emit_section(progress_reporter, "Secondary Artifacts")
    if total_artifacts == 0:
        emit_warning(progress_reporter, "No secondary artifacts declared in the signed manifest")
        return []
    verifications: list[AnySecondaryArtifactVerification] = []
    for index, artifact_entry in enumerate(artifact_entries, start=1):
        artifact_label = _artifact_label(artifact_entry, index=index)
        declared_kind = _declared_kind(artifact_entry)
        artifact_work_dir = work_dir / f"{index:02d}-{safe_path_component(artifact_label)}"
        emit_section(progress_reporter, f"Secondary Artifact {index}/{total_artifacts}: {artifact_label}")
        emit_detail(progress_reporter, "Kind", declared_kind or "n/a")
        try:
            verification: AnySecondaryArtifactVerification
            if isinstance(artifact_entry, GenericFileSecondaryArtifact):
                verification = verify_generic_file(
                    artifact_entry,
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
                    profile_overrides=profile_overrides,
                )
            elif isinstance(artifact_entry, GenericFileWithOpenPgpSecondaryArtifact):
                verification = verify_generic_file(
                    artifact_entry,
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
                    profile_overrides=profile_overrides,
                )
            elif isinstance(artifact_entry, MavenRepositorySecondaryArtifact):
                verification = verify_maven_repository(
                    artifact_entry,
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
                    profile_overrides=profile_overrides,
                )
            elif isinstance(artifact_entry, PythonDistributionSecondaryArtifact):
                verification = verify_python_distribution(
                    artifact_entry,
                    manifest_url=manifest_url,
                    work_dir=artifact_work_dir,
                    allow_non_production_release_targets=allow_non_production_release_targets,
                    component_config=component_config,
                    project_root=project_root,
                    source_date_epoch=source_date_epoch,
                    build_checks_allowed=build_checks_allowed,
                    inspection_bundle_root=inspection_bundle_root,
                    profile_overrides=profile_overrides,
                )
            elif isinstance(artifact_entry, NpmPackageSecondaryArtifact):
                verification = verify_npm_package(
                    artifact_entry,
                    manifest_url=manifest_url,
                    work_dir=artifact_work_dir,
                    allow_non_production_release_targets=allow_non_production_release_targets,
                    component_config=component_config,
                    project_root=project_root,
                    source_date_epoch=source_date_epoch,
                    build_checks_allowed=build_checks_allowed,
                    inspection_bundle_root=inspection_bundle_root,
                    profile_overrides=profile_overrides,
                )
            elif isinstance(artifact_entry, OciImageSecondaryArtifact):
                verification = verify_oci_image(
                    artifact_entry,
                    work_dir=artifact_work_dir,
                    component_config=component_config,
                    project_root=project_root,
                    source_date_epoch=source_date_epoch,
                    build_checks_allowed=build_checks_allowed,
                    inspection_bundle_root=inspection_bundle_root,
                    profile_overrides=profile_overrides,
                )
            elif isinstance(artifact_entry, MalformedSecondaryArtifactEntry):
                raise ValueError(_malformed_secondary_artifact_issue(artifact_entry, manifest_url))
            else:
                raise ValueError(
                    f"unsupported secondary artifact kind in manifest: {declared_kind or 'n/a'}"
                )
        except Exception as exc:
            verification = InvalidSecondaryArtifactVerificationReport(
                artifact_id=artifact_label,
                declared_kind=declared_kind,
                issues=[str(exc)],
            )
        _emit_secondary_artifact_summary(progress_reporter, verification)
        verifications.append(verification)
    return verifications


def _artifact_label(artifact_entry: SecondaryArtifactEntry, *, index: int) -> str:
    if isinstance(artifact_entry, BaseModel):
        return str(getattr(artifact_entry, "artifact_id", f"secondary-artifact-{index}"))
    if isinstance(artifact_entry, MalformedSecondaryArtifactEntry):
        if artifact_entry.artifact_id is not None:
            return artifact_entry.artifact_id
    return f"secondary-artifact-{index}"


def _declared_kind(artifact_entry: SecondaryArtifactEntry) -> str | None:
    if isinstance(artifact_entry, BaseModel):
        raw_kind = getattr(artifact_entry, "kind", None)
        if isinstance(raw_kind, str) and raw_kind.strip():
            return raw_kind.strip()
    if isinstance(artifact_entry, MalformedSecondaryArtifactEntry):
        return artifact_entry.declared_kind
    return None


def _malformed_secondary_artifact_issue(
    artifact_entry: MalformedSecondaryArtifactEntry,
    manifest_url: str,
) -> str:
    raw_payload = artifact_entry.raw_payload
    if not isinstance(raw_payload, dict):
        return f"manifest secondary artifact entry must be an object: {manifest_url}"
    raw_artifact_id = artifact_entry.artifact_id
    if raw_artifact_id is None:
        return f"manifest field artifact_id must be a non-empty string: {manifest_url}"
    raw_kind = artifact_entry.declared_kind
    if raw_kind is None:
        return f"manifest field kind must be a non-empty string: {manifest_url}"
    try:
        StrictSecondaryArtifactAdapter.validate_python(raw_payload)
    except Exception as exc:
        return str(exc)
    return f"manifest secondary artifact entry is malformed: {manifest_url}"


def _emit_secondary_artifact_summary(
    progress_reporter: ProgressReporter,
    verification: AnySecondaryArtifactVerification,
) -> None:
    issues = [str(issue) for issue in verification.issues]
    if isinstance(verification, InvalidSecondaryArtifactVerificationReport):
        for issue in issues:
            emit_failure(progress_reporter, issue)
        return
    if isinstance(verification, GenericFileVerificationReport):
        checksum_payload = verification.checksum
        emit_detail(progress_reporter, "File", verification.filename)
        emit_detail(progress_reporter, "URL", verification.uri)
        if (
            checksum_payload.matches_manifest
            and checksum_payload.algorithm
            and checksum_payload.value
        ):
            emit_success(
                progress_reporter,
                f"Verified checksum: {checksum_payload.algorithm}:{checksum_payload.value}",
            )
        if checksum_payload.sidecar_verified:
            emit_success(progress_reporter, "Verified checksum sidecar")
        for signature_verification in verification.signatures:
            emit_success(
                progress_reporter,
                f"Verified signature: {signature_verification.signer_fingerprint}",
            )
        if verification.inventory is not None:
            emit_success(
                progress_reporter,
                f"Verified inventory: {verification.inventory.filename}",
            )
        if verification.reproducibility is not None:
            _emit_reproducibility_details(progress_reporter, verification.reproducibility)
            if verification.reproducibility.matches_remote_bytes is True:
                emit_success(progress_reporter, "Verified rebuilt artifact matches staged bytes")
        for issue in issues:
            emit_failure(progress_reporter, issue)
        return
    if isinstance(verification, MavenRepositoryVerificationReport):
        live_repository = verification.live_repository
        emit_detail(progress_reporter, "Base URL", verification.base_url)
        if verification.inventory is not None:
            emit_detail(progress_reporter, "Inventory", verification.inventory.filename)
        if live_repository.matches_signed_inventory and live_repository.entry_count is not None:
            emit_success(
                progress_reporter,
                f"Verified live repository against signed inventory: {live_repository.entry_count} entries",
            )
        if live_repository.signature_verifications:
            emit_info(
                progress_reporter,
                f"Verified detached signatures for {len(live_repository.signature_verifications)} repository files",
            )
        if verification.reproducibility is not None:
            _emit_reproducibility_details(progress_reporter, verification.reproducibility)
            if verification.reproducibility.matches_remote_bytes is True:
                emit_success(
                    progress_reporter,
                    "Verified rebuilt repository matches the staged repository policy",
                )
        for issue in issues:
            emit_failure(progress_reporter, issue)
        return
    if isinstance(verification, PythonDistributionVerificationReport):
        checksum_payload = verification.checksum
        index_resolution = verification.index_resolution
        emit_detail(progress_reporter, "Project", f"{verification.project_name} {verification.version}")
        emit_detail(progress_reporter, "File", verification.filename)
        emit_detail(progress_reporter, "URL", verification.uri)
        emit_detail(progress_reporter, "Simple index", index_resolution.project_index_url)
        if checksum_payload.matches_manifest and checksum_payload.algorithm and checksum_payload.value:
            emit_success(
                progress_reporter,
                f"Verified checksum: {checksum_payload.algorithm}:{checksum_payload.value}",
            )
        if checksum_payload.sidecar_verified:
            emit_success(progress_reporter, "Verified checksum sidecar")
        if index_resolution.resolved_url is not None:
            emit_success(progress_reporter, "Verified simple index entry")
        if verification.reproducibility is not None:
            _emit_reproducibility_details(progress_reporter, verification.reproducibility)
            if verification.reproducibility.matches_remote_bytes is True:
                emit_success(progress_reporter, "Verified rebuilt artifact matches staged bytes")
        for issue in issues:
            emit_failure(progress_reporter, issue)
        return
    if isinstance(verification, OciImageVerificationReport):
        inspection = verification.inspection
        emit_detail(progress_reporter, "Image", inspection.image_ref)
        if inspection.digest_matches_manifest:
            emit_success(progress_reporter, f"Verified digest: {verification.digest}")
        if inspection.platform_digests_match:
            emit_success(progress_reporter, "Verified platform digests")
        if verification.reproducibility is not None:
            _emit_reproducibility_details(progress_reporter, verification.reproducibility)
            if verification.reproducibility.matches_remote_bytes is True:
                emit_success(progress_reporter, "Verified rebuilt image digests match the staged image")
        for issue in issues:
            emit_failure(progress_reporter, issue)
        return
    if isinstance(verification, NpmPackageVerificationReport):
        checksum_payload = verification.checksum
        registry_resolution = verification.registry_resolution
        emit_detail(progress_reporter, "Package", f"{verification.package_name} {verification.version}")
        emit_detail(progress_reporter, "Registry", verification.registry_url)
        emit_detail(progress_reporter, "Tarball", verification.uri)
        if verification.integrity.matches_downloaded_bytes:
            emit_success(progress_reporter, f"Verified integrity: {verification.integrity.value}")
        if checksum_payload.matches_manifest and checksum_payload.algorithm and checksum_payload.value:
            emit_success(
                progress_reporter,
                f"Verified checksum: {checksum_payload.algorithm}:{checksum_payload.value}",
            )
        if checksum_payload.sidecar_verified:
            emit_success(progress_reporter, "Verified checksum sidecar")
        if registry_resolution.metadata_url is not None:
            emit_success(
                progress_reporter,
                f"Verified registry metadata: {registry_resolution.metadata_url}",
            )
        if verification.reproducibility is not None:
            _emit_reproducibility_details(progress_reporter, verification.reproducibility)
            if verification.reproducibility.matches_remote_bytes is True:
                emit_success(progress_reporter, "Verified rebuilt artifact matches staged bytes")
        for issue in issues:
            emit_failure(progress_reporter, issue)
        return
    raise ValueError(
        "unsupported secondary artifact kind for console reporting: "
        f"{verification.artifact_id} ({verification.kind})"
    )


def _emit_reproducibility_details(
    progress_reporter: ProgressReporter,
    reproducibility_payload: ArtifactReproducibilityReport,
) -> None:
    recipe_source = "local-override" if reproducibility_payload.override.applied else "canonical-profile"
    emit_detail(
        progress_reporter,
        "Reproducibility profile",
        reproducibility_payload.profile_id,
    )
    emit_detail(
        progress_reporter,
        "Recipe source",
        recipe_source,
    )
    canonical_build = reproducibility_payload.canonical_recipe.build if reproducibility_payload.canonical_recipe else None
    effective_build = reproducibility_payload.effective_execution.build if reproducibility_payload.effective_execution else None
    override_build = reproducibility_payload.override.build
    if recipe_source == "local-override" and canonical_build is not None:
        canonical_command = canonical_build.command
        if canonical_command:
            emit_detail(
                progress_reporter,
                "Canonical build command",
                " ".join(str(part) for part in canonical_command),
            )
    build_command = effective_build.command if effective_build else []
    if build_command:
        emit_detail(progress_reporter, "Build command", " ".join(str(part) for part in build_command))
    build_working_directory = effective_build.working_directory if effective_build else None
    if build_working_directory:
        emit_detail(progress_reporter, "Build working directory", str(build_working_directory))
    injected_environment_keys = effective_build.injected_environment_keys if effective_build else []
    if injected_environment_keys:
        emit_detail(
            progress_reporter,
            "Injected environment keys",
            ", ".join(str(key) for key in injected_environment_keys),
        )
    override_fields = _override_field_summary(override_build)
    if override_fields:
        emit_detail(progress_reporter, "Override fields", ", ".join(str(field) for field in override_fields))
    for output_path in (effective_build.output_paths if effective_build else []):
        emit_detail(progress_reporter, "Rebuild output", str(output_path))


def _override_field_summary(
    override_build: ArtifactReproducibilityBuildOverrideReport | None,
) -> list[str]:
    if override_build is None:
        return []
    fields: list[str] = []
    if override_build.command is not None:
        fields.append("build.command")
    if override_build.working_directory is not None:
        fields.append("build.working_directory")
    if override_build.output_globs is not None:
        fields.append("build.output_globs")
    fields.extend(f"build.env.{key}" for key in override_build.env_keys)
    return fields
