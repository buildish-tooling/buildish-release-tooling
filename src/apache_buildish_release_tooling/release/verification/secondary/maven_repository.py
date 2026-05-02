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
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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
    MavenRepositoryPathMode,
    MavenRepositoryPathResultReport,
    MavenRepositoryPathRuleReport,
    MavenRepositoryReproducibilityMetadata,
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
from apache_buildish_release_tooling.release.verification.rebuild import (
    ResolvedRebuildProfile,
    canonical_recipe_payload,
    effective_execution_payload,
    override_payload,
    resolve_effective_rebuild_profile,
    run_host_direct_profile,
)

from .shared import (
    _RawInventoryRead,
    downloaded_inventory,
)


@dataclass(frozen=True)
class _NormalizedZipEntry:
    """One normalized ZIP member used by Maven reproducibility comparison."""

    is_dir: bool
    mode: int | None
    sha512: str | None

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
            artifact_entry.model_dump(mode="json", exclude_none=True),
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
            path_results, comparison_issues, matches_remote_bytes = _compare_maven_repository_trees(
                artifact_id=artifact_id,
                staged_by_path=staged_by_path,
                staged_cache=staged_cache,
                rebuilt_repository_path=rebuilt_repository_path,
                path_rules=path_rules,
                require_signatures=require_signatures,
                progress_reporter=progress_reporter,
            )
            if comparison_issues:
                failure_class = failure_class or _maven_reproducibility_failure_class(path_results)
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


def _path_mode_for_repository_entry(
    relative_path: str,
    path_rules: tuple[MavenRepositoryPathRuleReport, ...],
) -> MavenRepositoryPathMode:
    for rule in path_rules:
        if re.search(rule.pattern, relative_path):
            return rule.mode
    if _is_default_remote_only_repository_entry(relative_path):
        return "remote-only"
    return "exact-bytes"


def _compare_maven_repository_trees(
    *,
    artifact_id: str,
    staged_by_path: dict[str, _RepositoryFile],
    staged_cache: dict[str, bytes],
    rebuilt_repository_path: Path,
    path_rules: tuple[MavenRepositoryPathRuleReport, ...],
    require_signatures: bool,
    progress_reporter: ProgressReporter,
) -> tuple[list[MavenRepositoryPathResultReport], list[str], bool]:
    emit_info(progress_reporter, f"Reusing staged repository snapshot for local comparison: {artifact_id}")
    emit_info(
        progress_reporter,
        f"Checking rebuilt repository output under {rebuilt_repository_path}",
    )
    if require_signatures and not any(relative_path.endswith(".asc") for relative_path in staged_by_path):
        return (
            [],
            [
                f"maven-repository reproducibility policy requires staged detached signatures for {artifact_id}"
            ],
            False,
        )
    return _compare_repository_path_sets(
        staged_by_path=staged_by_path,
        staged_cache=staged_cache,
        rebuilt_repository_path=rebuilt_repository_path,
        path_rules=path_rules,
        progress_reporter=progress_reporter,
    )


def _compare_repository_path_sets(
    *,
    staged_by_path: dict[str, _RepositoryFile],
    staged_cache: dict[str, bytes],
    rebuilt_repository_path: Path,
    path_rules: tuple[MavenRepositoryPathRuleReport, ...],
    progress_reporter: ProgressReporter,
) -> tuple[list[MavenRepositoryPathResultReport], list[str], bool]:
    issues: list[str] = []
    path_results: list[MavenRepositoryPathResultReport] = []
    rebuilt_cache: dict[str, bytes] = {}
    comparable_staged_paths = {
        relative_path
        for relative_path in staged_by_path
        if _path_mode_for_repository_entry(relative_path, path_rules) != "remote-only"
    }
    for relative_path in sorted(staged_by_path):
        mode = _path_mode_for_repository_entry(relative_path, path_rules)
        if mode != "remote-only":
            continue
        path_results.append(
            MavenRepositoryPathResultReport(
                path=relative_path,
                mode=mode,
                verdict="skipped",
                detail="excluded from local comparison by path rule",
            )
        )
    common_paths = sorted(comparable_staged_paths)
    for index, relative_path in enumerate(common_paths, start=1):
        mode = _path_mode_for_repository_entry(relative_path, path_rules)
        rebuilt_repository_file = _rebuilt_repository_file(
            rebuilt_repository_path,
            relative_path=relative_path,
        )
        if rebuilt_repository_file is None:
            issues.append(
                "maven-repository reproducibility is missing one comparable rebuilt path: "
                f"{relative_path}"
            )
            path_results.append(
                MavenRepositoryPathResultReport(
                    path=relative_path,
                    mode=mode,
                    verdict="failed",
                    detail="missing rebuilt path",
                )
            )
            continue
        staged_payload = _cached_staged_repository_bytes(
            staged_by_path[relative_path],
            cache=staged_cache,
        )
        rebuilt_payload = _repository_file_bytes(
            rebuilt_repository_file,
            cache=rebuilt_cache,
            remote_http_client=None,
        )
        raw_bytes_equal = staged_payload == rebuilt_payload
        normalized_match: bool | None = None
        detail = "raw bytes matched exactly"
        verdict: Literal["verified", "failed", "skipped"] = "verified"
        if not raw_bytes_equal:
            if mode == "exact-bytes":
                detail = "raw bytes differ"
                verdict = "failed"
                issues.append(
                    "maven-repository reproducibility exact-bytes comparison failed: "
                    f"{relative_path}"
                )
            elif mode == "content-only":
                normalized_match, detail = _compare_zip_payloads(
                    staged_payload,
                    rebuilt_payload,
                    compare_permissions=False,
                )
                if not normalized_match:
                    verdict = "failed"
                    issues.append(
                        "maven-repository reproducibility content-only comparison failed: "
                        f"{relative_path}"
                    )
            elif mode == "zip-normalized":
                normalized_match, detail = _compare_zip_payloads(
                    staged_payload,
                    rebuilt_payload,
                    compare_permissions=True,
                )
                if not normalized_match:
                    verdict = "failed"
                    issues.append(
                        "maven-repository reproducibility zip-normalized comparison failed: "
                        f"{relative_path}"
                    )
            else:
                verdict = "failed"
                detail = f"unsupported comparison mode {mode!r}"
                issues.append(
                    "maven-repository reproducibility encountered an unsupported comparison mode: "
                    f"{relative_path} -> {mode}"
                )
        path_results.append(
            MavenRepositoryPathResultReport(
                path=relative_path,
                mode=mode,
                verdict=verdict,
                detail=detail,
                raw_bytes_equal=raw_bytes_equal,
                normalized_match=normalized_match,
                staged_sha512=hashlib.sha512(staged_payload).hexdigest(),
                rebuilt_sha512=hashlib.sha512(rebuilt_payload).hexdigest(),
            )
        )
        update_info(
            progress_reporter,
            f"Compared rebuilt repository entries: {index}/{len(common_paths)}",
        )
    return path_results, issues, not issues


def _rebuilt_repository_file(
    rebuilt_repository_path: Path,
    *,
    relative_path: str,
) -> _RepositoryFile | None:
    local_path = rebuilt_repository_path / Path(relative_path)
    if not local_path.is_file():
        return None
    return _RepositoryFile(
        relative_path=relative_path,
        size_bytes=local_path.stat().st_size,
        local_path=local_path,
    )


def _cached_staged_repository_bytes(
    repository_file: _RepositoryFile,
    *,
    cache: dict[str, bytes],
) -> bytes:
    payload = cache.get(repository_file.relative_path)
    if payload is None:
        raise ValueError(
            "staged maven repository snapshot is missing cached bytes for reproducibility comparison: "
            f"{repository_file.relative_path}"
        )
    return payload


def _is_default_remote_only_repository_entry(relative_path: str) -> bool:
    lowered = relative_path.lower()
    return lowered.endswith((".asc", ".sha512", ".sha256", ".sha1", ".md5"))


def _compare_zip_payloads(
    staged_payload: bytes,
    rebuilt_payload: bytes,
    *,
    compare_permissions: bool,
) -> tuple[bool, str]:
    try:
        staged_entries = _normalized_zip_entries(
            staged_payload,
            compare_permissions=compare_permissions,
        )
        rebuilt_entries = _normalized_zip_entries(
            rebuilt_payload,
            compare_permissions=compare_permissions,
        )
    except ValueError as exc:
        return False, str(exc)
    staged_paths = set(staged_entries)
    rebuilt_paths = set(rebuilt_entries)
    missing_paths = sorted(staged_paths - rebuilt_paths)
    unexpected_paths = sorted(rebuilt_paths - staged_paths)
    if missing_paths or unexpected_paths:
        return (
            False,
            "archive members differ: "
            f"missing={missing_paths} unexpected={unexpected_paths}",
        )
    for relative_path in sorted(staged_paths):
        staged_entry = staged_entries[relative_path]
        rebuilt_entry = rebuilt_entries[relative_path]
        if staged_entry.is_dir != rebuilt_entry.is_dir:
            return False, f"archive member type differs: {relative_path}"
        if compare_permissions and staged_entry.mode != rebuilt_entry.mode:
            return False, f"archive member permissions differ: {relative_path}"
        if staged_entry.sha512 != rebuilt_entry.sha512:
            return False, f"archive member contents differ: {relative_path}"
    if compare_permissions:
        return True, "archives matched after zip-normalized comparison"
    return True, "archives matched after content-only comparison"


def _normalized_zip_entries(
    payload: bytes,
    *,
    compare_permissions: bool,
) -> dict[str, _NormalizedZipEntry]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ValueError("comparison requires ZIP-like archives") from exc
    entries: dict[str, _NormalizedZipEntry] = {}
    with archive:
        for info in archive.infolist():
            if info.filename in entries:
                raise ValueError(f"archive member is duplicated: {info.filename}")
            entries[info.filename] = _NormalizedZipEntry(
                is_dir=info.is_dir(),
                mode=((info.external_attr >> 16) & 0o777) if compare_permissions else None,
                sha512=None if info.is_dir() else hashlib.sha512(archive.read(info)).hexdigest(),
            )
    return entries


def _maven_reproducibility_failure_class(
    path_results: list[MavenRepositoryPathResultReport],
) -> str:
    if any(result.detail in {"missing rebuilt path", "unexpected rebuilt path"} for result in path_results):
        return "path-set-mismatch"
    return "path-comparison-failed"


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
