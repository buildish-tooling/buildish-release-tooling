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

"""Shared host-direct reproducibility helpers for file-like secondary artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from apache_buildish_release_tooling.release.contracts import (
    ArtifactReproducibilityCanonicalRecipeReport,
    ArtifactReproducibilityEffectiveExecutionReport,
    ArtifactReproducibilityReport,
    ArtifactReproducibilityOverrideReport,
    FileLikeReproducibilityMetadata,
    GenericFileSecondaryArtifact,
    GenericFileWithOpenPgpSecondaryArtifact,
    InspectionEvidenceReference,
    NpmPackageSecondaryArtifact,
    PythonDistributionSecondaryArtifact,
    RebuiltOutputSnapshot,
    RetainedArtifactSnapshot,
    ShallowArchiveAnalysisReport,
)
from apache_buildish_release_tooling.release.models import ComponentConfig, VerifyRcOverrideConfig
from apache_buildish_release_tooling.release.source_artifact import checksum
from apache_buildish_release_tooling.release.verification.inspection_bundle import (
    retain_evidence_file,
    write_reproducibility_metadata,
)
from apache_buildish_release_tooling.release.verification.inspection.archive_shallow import (
    build_shallow_archive_analysis,
)
from apache_buildish_release_tooling.release.verification.rebuild import (
    ResolvedRebuildProfile,
    canonical_recipe_payload,
    effective_execution_payload,
    override_payload,
    resolve_effective_rebuild_profile,
    run_host_direct_profile,
)

FileLikeSecondaryArtifact = (
    GenericFileSecondaryArtifact
    | GenericFileWithOpenPgpSecondaryArtifact
    | PythonDistributionSecondaryArtifact
    | NpmPackageSecondaryArtifact
)


def verify_host_direct_single_file_reproducibility(
    artifact_entry: FileLikeSecondaryArtifact,
    *,
    manifest_url: str,
    artifact_id: str,
    kind: Literal[
        "generic-file",
        "generic-file-with-openpgp",
        "python-distribution",
        "npm-package",
    ],
    artifact_path: Path | None,
    work_dir: Path,
    component_config: ComponentConfig | None,
    project_root: Path | None,
    source_date_epoch: int | None,
    inspection_bundle_root: Path | None,
    subject_label: str,
    profile_overrides: VerifyRcOverrideConfig | None,
) -> ArtifactReproducibilityReport:
    """Run one host-direct rebuild recipe and compare its single output file against staged bytes."""

    reproducibility_selector = artifact_entry.reproducibility
    if reproducibility_selector is None:
        return ArtifactReproducibilityReport(
            profile_id="n/a",
            verdict="failed",
            comparison_mode="exact-bytes",
            failure_class="missing-profile",
            issues=[
                f"manifest secondary artifact does not declare a reproducibility profile: {artifact_id}"
            ],
        )
    profile_id = reproducibility_selector.profile_id
    issues: list[str] = []
    matches_remote_bytes: bool | None = None
    comparison_mode = "exact-bytes"
    failure_class: str | None = None
    evidence: list[InspectionEvidenceReference] = []
    resolved_profile: ResolvedRebuildProfile | None = None
    canonical_recipe: ArtifactReproducibilityCanonicalRecipeReport | None = None
    effective_execution: ArtifactReproducibilityEffectiveExecutionReport | None = None
    override: ArtifactReproducibilityOverrideReport = override_payload(None)
    archive_analysis: ShallowArchiveAnalysisReport | None = None
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
    build_result = None
    if not issues and component_config is not None:
        try:
            resolved_profile = resolve_effective_rebuild_profile(
                component_config,
                profile_id,
                expected_kinds=(kind,),
                profile_overrides=profile_overrides,
            )
            profile = resolved_profile.profile
            comparison_mode = profile.comparison.mode
            canonical_recipe = canonical_recipe_payload(resolved_profile)
            override = override_payload(resolved_profile)
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
            if len(build_result.output_paths) != 1:
                failure_class = "unexpected-output-count"
                raise ValueError(
                    f"{subject_label} reproducibility profile {profile_id!r} must produce exactly one output file"
                )
            built_artifact_path = build_result.output_paths[0]
            effective_execution = effective_execution_payload(
                build_result=build_result,
                project_root=project_root,
            )
            archive_analysis = build_shallow_archive_analysis(
                staged_path=artifact_path,
                rebuilt_path=built_artifact_path,
            )
            matches_remote_bytes = built_artifact_path.read_bytes() == artifact_path.read_bytes()
            if not matches_remote_bytes:
                failure_class = "byte-mismatch"
                raise ValueError(
                    f"{subject_label} reproducibility output does not match the staged artifact bytes: {artifact_id}"
                )
        except Exception as exc:
            issues.append(str(exc))
    if (
        inspection_bundle_root is not None
        and profile is not None
        and project_root is not None
        and artifact_path is not None
        and build_result is not None
    ):
        rebuilt_outputs = [
            RebuiltOutputSnapshot(
                path=str(path.relative_to(project_root)),
                sha512=checksum(path, "sha512"),
                size_bytes=path.stat().st_size,
            )
            for path in build_result.output_paths
        ]
        metadata_path = write_reproducibility_metadata(
            inspection_bundle_root,
            artifact_id=artifact_id,
            payload=FileLikeReproducibilityMetadata(
                artifact_id=artifact_id,
                kind=kind,
                profile_id=profile_id,
                comparison_mode=comparison_mode,
                canonical_recipe=canonical_recipe,
                effective_execution=effective_execution,
                override=override,
                failure_class=failure_class,
                archive_analysis=archive_analysis,
                staged_artifact=RetainedArtifactSnapshot(
                    filename=artifact_path.name,
                    sha512=checksum(artifact_path, "sha512"),
                    size_bytes=artifact_path.stat().st_size,
                ),
                rebuilt_outputs=rebuilt_outputs,
                matches_remote_bytes=matches_remote_bytes,
                issues=issues,
            ),
        )
        evidence.append(
            InspectionEvidenceReference(
                label="comparison-metadata",
                path=metadata_path,
            )
        )
        if issues:
            evidence.append(
                InspectionEvidenceReference(
                    label="staged-artifact",
                    path=retain_evidence_file(
                        inspection_bundle_root,
                        artifact_id=artifact_id,
                        label_directory="staged",
                        source_path=artifact_path,
                    ),
                )
            )
            for index, built_path in enumerate(build_result.output_paths, start=1):
                evidence.append(
                    InspectionEvidenceReference(
                        label="rebuilt-artifact" if index == 1 else f"rebuilt-artifact-{index}",
                        path=retain_evidence_file(
                            inspection_bundle_root,
                            artifact_id=artifact_id,
                            label_directory=f"rebuilt-{index:02d}",
                            source_path=built_path,
                        ),
                    )
                )
    return ArtifactReproducibilityReport(
        profile_id=profile_id,
        verdict="failed" if issues else "verified",
        comparison_mode=comparison_mode,
        canonical_recipe=canonical_recipe,
        effective_execution=effective_execution,
        override=override,
        matches_remote_bytes=matches_remote_bytes,
        failure_class=failure_class,
        archive_analysis=archive_analysis,
        evidence=evidence,
        issues=issues,
    )
