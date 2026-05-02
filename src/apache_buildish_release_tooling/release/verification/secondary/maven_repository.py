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

from apache_buildish_release_tooling.release.artifact_registration.kinds.maven_repository import (
    _RemoteHttpClient,
    _RepositoryFile,
    _inventory_worker_count,
    _repository_file_bytes,
    _repository_files,
    _validated_repository_root,
)
from apache_buildish_release_tooling.release.contracts import (
    ArtifactReproducibilityCanonicalRecipeReport,
    ArtifactReproducibilityEffectiveExecutionReport,
    ArtifactReproducibilityOverrideReport,
    ArtifactReproducibilityReport,
    InspectionEvidenceReference,
    InventoryVerificationReport,
    LiveMavenRepositoryReport,
    LiveRepositorySignatureVerification,
    MavenRepositoryInventoryEntry,
    MavenRepositoryInventoryV1,
    MavenRepositoryPathResultReport,
    MavenRepositoryPathRuleReport,
    MavenRepositorySecondaryArtifact,
    MavenRepositoryVerificationReport,
)
from apache_buildish_release_tooling.release.models import (
    ComponentConfig,
    VerifyRcMavenRepositoryComparisonConfig,
    VerifyRcOverrideConfig,
)
from apache_buildish_release_tooling.release.progress import ProgressReporter
from apache_buildish_release_tooling.release.verification.common import emit_info, emit_success, update_info
from apache_buildish_release_tooling.release.verification.common import (
    GpgVerifier,
    SignatureVerification,
    signature_payload,
    validate_fetch_uri,
)
from apache_buildish_release_tooling.release.verification.inspection_bundle import (
    write_reproducibility_metadata,
)
from apache_buildish_release_tooling.release.verification.schemas import (
    MavenRepositoryReproducibilityMetadata,
)
from apache_buildish_release_tooling.release.verification.rebuild import (
    ResolvedRebuildProfile,
    canonical_recipe_payload,
    effective_execution_payload,
    override_payload,
    resolve_effective_rebuild_profile,
    run_host_direct_profile,
)
from .maven_repository_repro import (
    compare_maven_repository_trees,
    maven_reproducibility_failure_class,
)
from .readers import _RawInventoryRead

from .shared import (
    downloaded_inventory,
)

def verify_maven_repository(
    artifact_entry: MavenRepositorySecondaryArtifact,
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
) -> MavenRepositoryVerificationReport:
    artifact_id = artifact_entry.artifact_id
    staging_repository_id = artifact_entry.staging_repository_id
    base_url = artifact_entry.base_url
    issues: list[str] = []
    inventory_payload: MavenRepositoryInventoryV1 | None = None
    inventory_report_payload: InventoryVerificationReport | None = None
    try:
        validate_fetch_uri(
            base_url,
            allow_non_production_release_targets=allow_non_production_release_targets,
            purpose=f"maven repository base URL for {artifact_id}",
        )
        _validated_repository_root(base_url, staging_repository_id)
    except Exception as exc:
        issues.append(str(exc))

    try:
        fetched_inventory = downloaded_inventory(
            artifact_entry,
            manifest_url=manifest_url,
            artifact_id=artifact_id,
            work_dir=work_dir,
            allow_non_production_release_targets=allow_non_production_release_targets,
        )
        if fetched_inventory is None:
            raise ValueError(f"manifest maven-repository artifact is missing inventory: {artifact_id}")
        inventory_report_payload = fetched_inventory.report_payload
        inventory_payload = _validated_maven_inventory_payload(
            fetched_inventory.raw_payload,
            artifact_id=artifact_id,
            staging_repository_id=staging_repository_id,
            base_url=base_url,
            source=manifest_url,
        )
    except Exception as exc:
        issues.append(str(exc))

    worker_count = _inventory_worker_count(None)
    remote_http_client: _RemoteHttpClient | None = None
    if not issues and base_url.startswith(("http://", "https://")):
        remote_http_client = _RemoteHttpClient.for_worker_count(worker_count)

    expected_entries: dict[str, MavenRepositoryInventoryEntry] = {}
    total_size_bytes = 0
    signature_verifications: tuple[tuple[str, str, SignatureVerification], ...] = ()
    matches_signed_inventory = False
    staged_repository_files_by_path: dict[str, _RepositoryFile] = {}
    staged_repository_cache: dict[str, bytes] = {}
    try:
        if not issues and inventory_payload is not None:
            emit_info(progress_reporter, f"Enumerating live repository from {base_url}")
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
            staged_repository_files_by_path = dict(files_by_relative_path)
            total_size_bytes = sum(repository_file.size_bytes for repository_file in repository_files)
            expected_entries = _maven_inventory_entries(inventory_payload)
            emit_info(
                progress_reporter,
                f"Checking live repository against signed inventory ({len(expected_entries)} entries)",
            )
            expected_paths = set(expected_entries)
            live_paths = set(files_by_relative_path)
            missing_paths = sorted(expected_paths - live_paths)
            unexpected_paths = sorted(live_paths - expected_paths)
            if missing_paths or unexpected_paths:
                issues.append(
                    "live maven repository paths do not match the signed inventory: "
                    f"missing={missing_paths} unexpected={unexpected_paths}"
                )

            cache: dict[str, bytes] = {}
            staged_repository_cache = cache
            content_issues = 0
            common_paths = sorted(expected_paths & live_paths)
            for index, relative_path in enumerate(common_paths, start=1):
                repository_file = files_by_relative_path[relative_path]
                expected_entry = expected_entries[relative_path]
                if repository_file.size_bytes != expected_entry.size_bytes:
                    issues.append(
                        "live maven repository file size does not match the signed inventory: "
                        f"{relative_path} {repository_file.size_bytes} != {expected_entry.size_bytes}"
                    )
                    content_issues += 1
                try:
                    actual_sha512 = hashlib.sha512(
                        _repository_file_bytes(
                            repository_file,
                            cache=cache,
                            remote_http_client=remote_http_client,
                        )
                    ).hexdigest()
                except Exception as exc:
                    issues.append(str(exc))
                    content_issues += 1
                    continue
                if actual_sha512 != expected_entry.sha512:
                    issues.append(
                        "live maven repository checksum does not match the signed inventory: "
                        f"{relative_path} {actual_sha512} != {expected_entry.sha512}"
                    )
                    content_issues += 1
                update_info(
                    progress_reporter,
                    f"Checked live repository entries: {index}/{len(common_paths)}",
                )

            emit_info(progress_reporter, "Verifying detached signatures present in the live repository")
            signature_verifications, signature_issues = _verified_maven_repository_signatures(
                files_by_relative_path,
                cache=cache,
                remote_http_client=remote_http_client,
                verifier=verifier,
                work_dir=work_dir / "signatures",
            )
            issues.extend(signature_issues)
            matches_signed_inventory = not missing_paths and not unexpected_paths and content_issues == 0
    finally:
        if remote_http_client is not None:
            remote_http_client.close()

    inventory_metadata = artifact_entry.inventory
    if inventory_report_payload is not None:
        entry_count = inventory_metadata.entry_count
        total_size_metadata = inventory_metadata.total_size_bytes
        inventory_report_payload = inventory_report_payload.model_copy(
            update={
                "entry_count": entry_count,
                "total_size_bytes": total_size_metadata,
            }
        )
        if entry_count is not None and expected_entries and entry_count != len(expected_entries):
            issues.append(
                "manifest maven inventory entry_count does not match the signed inventory: "
                f"{entry_count} != {len(expected_entries)}"
            )
        if total_size_metadata is not None and total_size_bytes and total_size_metadata != total_size_bytes:
            issues.append(
                "manifest maven inventory total_size_bytes does not match the live repository: "
                f"{total_size_metadata} != {total_size_bytes}"
            )
    if not issues and expected_entries:
        emit_success(
            progress_reporter,
            f"Verified maven repository inventory: {len(expected_entries)} entries",
        )
    reproducibility_verification: ArtifactReproducibilityReport | None = None
    if build_checks_allowed and artifact_entry.reproducibility is not None:
        reproducibility_verification = _verify_maven_repository_reproducibility(
            artifact_entry,
            manifest_url=manifest_url,
            artifact_id=artifact_id,
            work_dir=work_dir / "reproducibility",
            component_config=component_config,
            project_root=project_root,
            source_date_epoch=source_date_epoch,
            inspection_bundle_root=inspection_bundle_root,
            inventory_payload=inventory_payload,
            staged_by_path={
                relative_path: staged_repository_files_by_path[relative_path]
                for relative_path in sorted(expected_entries)
                if relative_path in staged_repository_files_by_path
            },
            staged_cache=dict(staged_repository_cache),
            progress_reporter=progress_reporter,
            profile_overrides=profile_overrides,
        )
        issues.extend(reproducibility_verification.issues)

    return MavenRepositoryVerificationReport(
        artifact_id=artifact_id,
        verdict="failed" if issues else "verified",
        issues=issues,
        staging_repository_id=staging_repository_id,
        base_url=base_url,
        inventory=inventory_report_payload,
        live_repository=LiveMavenRepositoryReport(
            entry_count=len(expected_entries) if expected_entries else None,
            total_size_bytes=total_size_bytes,
            matches_signed_inventory=matches_signed_inventory,
            signature_verifications=[
                LiveRepositorySignatureVerification(
                    path=relative_path,
                    target_path=target_path,
                    signature=signature_payload(signature_verification),
                )
                for relative_path, target_path, signature_verification in signature_verifications
            ],
        ),
        reproducibility=reproducibility_verification,
    )


def _verify_maven_repository_reproducibility(
    artifact_entry: MavenRepositorySecondaryArtifact,
    *,
    manifest_url: str,
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
            f"build-based reproducibility for {artifact_id} requires one verified source checkout"
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


def _validated_maven_inventory_payload(
    inventory_payload: _RawInventoryRead,
    *,
    artifact_id: str,
    staging_repository_id: str,
    base_url: str,
    source: str,
) -> MavenRepositoryInventoryV1:
    inventory = MavenRepositoryInventoryV1.model_validate(
        inventory_payload.model_dump(mode="json", exclude_none=True)
    )
    if inventory.artifact_id != artifact_id:
        raise ValueError("maven inventory artifact_id does not match the manifest secondary artifact")
    if inventory.staging_repository_id != staging_repository_id:
        raise ValueError(
            "maven inventory staging_repository_id does not match the manifest secondary artifact"
        )
    if inventory.base_url != base_url:
        raise ValueError("maven inventory base_url does not match the manifest secondary artifact")
    return inventory


def _maven_inventory_entries(
    inventory_payload: MavenRepositoryInventoryV1,
) -> dict[str, MavenRepositoryInventoryEntry]:
    entries: dict[str, MavenRepositoryInventoryEntry] = {}
    for entry in inventory_payload.entries:
        relative_path = entry.path
        if relative_path in entries:
            raise ValueError(f"maven inventory path is duplicated: {relative_path}")
        entries[relative_path] = entry
    return entries


def _verified_maven_repository_signatures(
    files_by_relative_path: dict[str, _RepositoryFile],
    *,
    cache: dict[str, bytes],
    remote_http_client: _RemoteHttpClient | None,
    verifier: GpgVerifier,
    work_dir: Path,
) -> tuple[tuple[tuple[str, str, SignatureVerification], ...], list[str]]:
    verifications: list[tuple[str, str, SignatureVerification]] = []
    issues: list[str] = []
    for relative_path in sorted(files_by_relative_path):
        if not relative_path.endswith(".asc"):
            continue
        target_relative_path = relative_path.removesuffix(".asc")
        target_file = files_by_relative_path.get(target_relative_path)
        if target_file is None:
            issues.append(
                f"maven repository detached signature has no matching target file: {relative_path}"
            )
            continue
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
        try:
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
        except Exception as exc:
            issues.append(str(exc))
    return tuple(verifications), issues
