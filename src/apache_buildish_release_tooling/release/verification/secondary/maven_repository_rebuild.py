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

"""Local rebuild comparison helpers for Maven repository secondary artifacts."""

from __future__ import annotations

from pathlib import Path

from apache_buildish_release_tooling.release.artifact_registration.kinds.maven_repository import (
    _RepositoryFile,
)
from apache_buildish_release_tooling.release.contracts import (
    ArtifactReproducibilityCanonicalRecipeReport,
    ArtifactReproducibilityEffectiveExecutionReport,
    ArtifactReproducibilityOverrideReport,
    ArtifactReproducibilityReport,
    InspectionEvidenceReference,
    MavenRepositoryPathResultReport,
    MavenRepositoryPathRuleReport,
    MavenRepositoryInventoryV1,
    MavenRepositorySecondaryArtifact,
)
from apache_buildish_release_tooling.release.models import (
    ComponentConfig,
    VerifyRcMavenRepositoryComparisonConfig,
    VerifyRcOverrideConfig,
)
from apache_buildish_release_tooling.release.progress import ProgressReporter
from apache_buildish_release_tooling.release.verification.common import emit_info
from apache_buildish_release_tooling.release.verification.inspection_bundle import (
    write_reproducibility_metadata,
)
from apache_buildish_release_tooling.release.verification.rebuild import (
    ResolvedRebuildProfile,
    canonical_recipe_payload,
    effective_execution_payload,
    override_payload,
    resolve_effective_rebuild_profile,
    run_host_direct_profile,
)
from apache_buildish_release_tooling.release.verification.schemas import (
    MavenRepositoryReproducibilityMetadata,
)
from .maven_repository_repro import (
    compare_maven_repository_trees,
    maven_reproducibility_failure_class,
)


def verify_maven_repository_reproducibility(
    artifact_entry: MavenRepositorySecondaryArtifact,
    *,
    artifact_id: str,
    work_dir: Path,
    component_config: ComponentConfig | None,
    project_root: Path | None,
    source_date_epoch: int | None,
    inspection_bundle_root: Path | None,
    inventory_payload: MavenRepositoryInventoryV1 | None,
    staged_by_path: dict[str, _RepositoryFile],
    staged_cache: dict[str, bytes],
    progress_reporter: ProgressReporter,
    profile_overrides: VerifyRcOverrideConfig | None,
) -> ArtifactReproducibilityReport:
    """Run one configured local Maven repository rebuild comparison."""

    reproducibility_selector = artifact_entry.reproducibility
    if reproducibility_selector is None:
        return ArtifactReproducibilityReport(
            profile_id="n/a",
            verdict="failed",
            comparison_mode="repository-tree",
            failure_class="missing-profile",
            issues=[
                f"manifest secondary artifact does not declare a reproducibility profile: {artifact_id}"
            ],
        )
    profile_id = reproducibility_selector.profile_id
    issues: list[str] = []
    matches_remote_bytes: bool | None = None
    comparison_mode = "repository-tree"
    failure_class: str | None = None
    evidence: list[InspectionEvidenceReference] = []
    repository_dir: str | None = None
    require_signatures = False
    path_rules: tuple[MavenRepositoryPathRuleReport, ...] = ()
    path_results: list[MavenRepositoryPathResultReport] = []
    rebuilt_repository_path: Path | None = None
    resolved_profile: ResolvedRebuildProfile | None = None
    canonical_recipe: ArtifactReproducibilityCanonicalRecipeReport | None = None
    effective_execution: ArtifactReproducibilityEffectiveExecutionReport | None = None
    override: ArtifactReproducibilityOverrideReport = override_payload(None)
    profile = None
    build_result = None
    if component_config is None:
        failure_class = failure_class or "missing-component-config"
        issues.append(
            f"build-based reproducibility for {artifact_id} requires --component-config to resolve profile {profile_id!r}"
        )
    if project_root is None:
        failure_class = failure_class or "missing-project-root"
        issues.append(
            "build-based reproducibility for "
            f"{artifact_id} requires one verified source checkout"
        )
    if inventory_payload is None:
        failure_class = failure_class or "missing-signed-inventory"
        issues.append(
            f"build-based reproducibility for {artifact_id} requires the signed maven inventory"
        )
    if not issues and component_config is not None:
        try:
            resolved_profile = resolve_effective_rebuild_profile(
                component_config,
                profile_id,
                expected_kinds=("maven-repository",),
                profile_overrides=profile_overrides,
            )
            profile = resolved_profile.profile
            if not isinstance(profile.comparison, VerifyRcMavenRepositoryComparisonConfig):
                raise ValueError(
                    f"verify_rc profile {profile_id!r} must use comparison.mode 'repository-tree' for maven-repository artifacts"
                )
            comparison_mode = profile.comparison.mode
            repository_dir = profile.comparison.repository_dir
            require_signatures = profile.comparison.require_signatures
            path_rules = tuple(
                MavenRepositoryPathRuleReport(
                    pattern=rule.pattern,
                    mode=rule.mode,
                )
                for rule in profile.comparison.path_rules
            )
            canonical_recipe = canonical_recipe_payload(resolved_profile)
            override = override_payload(resolved_profile)
        except Exception as exc:
            failure_class = failure_class or "invalid-profile"
            issues.append(str(exc))
    if (
        not issues
        and profile is not None
        and project_root is not None
        and inventory_payload is not None
        and repository_dir is not None
    ):
        emit_info(progress_reporter, f"Running local reproducibility profile {profile_id}")
        try:
            build_result = run_host_direct_profile(
                profile_id=profile_id,
                profile=profile,
                project_root=project_root,
                work_dir=work_dir,
                source_date_epoch=source_date_epoch,
            )
            effective_execution = effective_execution_payload(
                build_result=build_result,
                project_root=project_root,
                output_paths=[repository_dir] if repository_dir is not None else None,
            )
            rebuilt_repository_path = project_root / repository_dir
            if not rebuilt_repository_path.is_dir():
                failure_class = failure_class or "missing-repository-dir"
                raise ValueError(
                    f"maven-repository reproducibility profile {profile_id!r} did not create repository_dir {repository_dir!r}"
                )
            path_results, comparison_issues, matches_remote_bytes = compare_maven_repository_trees(
                artifact_id=artifact_id,
                staged_by_path=staged_by_path,
                staged_cache=staged_cache,
                rebuilt_repository_path=rebuilt_repository_path,
                path_rules=path_rules,
                require_signatures=require_signatures,
                progress_reporter=progress_reporter,
            )
            if comparison_issues:
                failure_class = failure_class or maven_reproducibility_failure_class(path_results)
                issues.extend(comparison_issues)
        except Exception as exc:
            if failure_class is None:
                failure_class = "build-failed"
            issues.append(str(exc))
    if inspection_bundle_root is not None:
        verified_path_count = sum(
            1 for path_result in path_results if path_result.verdict == "verified"
        )
        failed_path_count = sum(
            1 for path_result in path_results if path_result.verdict == "failed"
        )
        skipped_path_count = sum(
            1 for path_result in path_results if path_result.verdict == "skipped"
        )
        metadata_path = write_reproducibility_metadata(
            inspection_bundle_root,
            artifact_id=artifact_id,
            payload=MavenRepositoryReproducibilityMetadata(
                artifact_id=artifact_id,
                kind="maven-repository",
                profile_id=profile_id,
                comparison_mode="repository-tree",
                canonical_recipe=canonical_recipe,
                effective_execution=effective_execution,
                override=override,
                repository_dir=repository_dir,
                require_signatures=require_signatures,
                path_rules=list(path_rules),
                matches_remote_bytes=matches_remote_bytes,
                failure_class=failure_class,
                verified_path_count=verified_path_count,
                failed_path_count=failed_path_count,
                skipped_path_count=skipped_path_count,
                path_results=[
                    path_result
                    for path_result in path_results
                    if path_result.verdict == "failed"
                ],
                issues=issues,
            ),
        )
        evidence.append(
            InspectionEvidenceReference(
                label="comparison-metadata",
                path=metadata_path,
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
        evidence=evidence,
        issues=issues,
    )
