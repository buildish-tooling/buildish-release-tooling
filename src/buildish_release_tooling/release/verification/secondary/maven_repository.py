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

"""Maven repository secondary-artifact verification."""

from __future__ import annotations

from pathlib import Path

from buildish_release_tooling.release.artifact_registration.kinds.maven_repository import (
    _RepositoryFile,
    _inventory_worker_count,
    _repository_files,
    _validated_repository_root,
)
from buildish_release_tooling.release.contracts import (
    ArtifactReproducibilityReport,
    InventoryVerificationReport,
    LiveMavenRepositoryReport,
    LiveRepositorySignatureVerification,
    MavenRepositoryInventoryEntry,
    MavenRepositoryInventoryV1,
    MavenRepositorySecondaryArtifact,
    MavenRepositoryVerificationReport,
)
from buildish_release_tooling.release.models import ComponentConfig, VerifyRcOverrideConfig
from buildish_release_tooling.release.progress import ProgressReporter
from buildish_release_tooling.release.verification.common import emit_info, emit_success, update_info
from buildish_release_tooling.shared.downloader import DownloadSession
from buildish_release_tooling.shared.io import hash_file
from buildish_release_tooling.release.verification.common import (
    GpgVerifier,
    SignatureVerification,
    signature_payload,
    validate_fetch_uri,
)
from .maven_repository_live import (
    maven_inventory_entries,
    validated_maven_inventory_payload,
    verified_maven_repository_signatures,
)
from .maven_repository_rebuild import verify_maven_repository_reproducibility

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
        inventory_payload = validated_maven_inventory_payload(
            fetched_inventory.raw_payload,
            artifact_id=artifact_id,
            staging_repository_id=staging_repository_id,
            base_url=base_url,
        )
    except Exception as exc:
        issues.append(str(exc))

    worker_count = _inventory_worker_count(None)
    remote_http_client: DownloadSession | None = None
    if not issues and base_url.startswith(("http://", "https://")):
        remote_http_client = DownloadSession.non_production(max_connections=worker_count)

    expected_entries: dict[str, MavenRepositoryInventoryEntry] = {}
    total_size_bytes = 0
    signature_verifications: tuple[tuple[str, str, SignatureVerification], ...] = ()
    matches_signed_inventory = False
    staged_repository_files_by_path: dict[str, _RepositoryFile] = {}
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
            staged_repository_files_by_path = {
                relative_path: repository_file
                for relative_path, repository_file in files_by_relative_path.items()
                if repository_file.local_path is not None
            }
            total_size_bytes = sum(repository_file.size_bytes for repository_file in repository_files)
            expected_entries = maven_inventory_entries(inventory_payload)
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
                    materialized_file = _materialized_repository_file(
                        repository_file,
                        work_dir=work_dir / "staged-repository",
                        remote_http_client=remote_http_client,
                    )
                    staged_repository_files_by_path[relative_path] = materialized_file
                    if materialized_file.local_path is None:
                        raise ValueError(f"repository file has no local path: {relative_path}")
                    actual_sha512 = hash_file(materialized_file.local_path)
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
            signature_verifications, signature_issues = verified_maven_repository_signatures(
                staged_repository_files_by_path,
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
        reproducibility_verification = verify_maven_repository_reproducibility(
            artifact_entry,
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


def _materialized_repository_file(
    repository_file: _RepositoryFile,
    *,
    work_dir: Path,
    remote_http_client: DownloadSession | None,
) -> _RepositoryFile:
    if repository_file.local_path is not None:
        return repository_file
    if repository_file.source_url is None:
        raise ValueError(f"repository file has no readable source: {repository_file.relative_path}")
    if remote_http_client is None:
        raise ValueError(f"remote repository file requires an HTTP client: {repository_file.relative_path}")
    local_path = work_dir / repository_file.relative_path
    remote_http_client.download_to_path(
        repository_file.source_url,
        local_path,
        max_bytes=repository_file.size_bytes,
    )
    return _RepositoryFile(
        relative_path=repository_file.relative_path,
        size_bytes=repository_file.size_bytes,
        source_url=repository_file.source_url,
        local_path=local_path,
    )
