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

"""Live staged Maven repository verification helpers."""

from __future__ import annotations

from pathlib import Path

from apache_buildish_release_tooling.release.artifact_registration.kinds.maven_repository import (
    _RepositoryFile,
)
from apache_buildish_release_tooling.release.contracts import (
    MavenRepositoryInventoryEntry,
    MavenRepositoryInventoryV1,
)
from apache_buildish_release_tooling.release.verification.common import (
    GpgVerifier,
    SignatureVerification,
)
from .readers import _RawInventoryRead


def validated_maven_inventory_payload(
    inventory_payload: _RawInventoryRead,
    *,
    artifact_id: str,
    staging_repository_id: str,
    base_url: str,
) -> MavenRepositoryInventoryV1:
    """Validate one signed Maven inventory against the matching manifest entry."""

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


def maven_inventory_entries(
    inventory_payload: MavenRepositoryInventoryV1,
) -> dict[str, MavenRepositoryInventoryEntry]:
    """Index one validated inventory by staged relative path."""

    entries: dict[str, MavenRepositoryInventoryEntry] = {}
    for entry in inventory_payload.entries:
        relative_path = entry.path
        if relative_path in entries:
            raise ValueError(f"maven inventory path is duplicated: {relative_path}")
        entries[relative_path] = entry
    return entries


def verified_maven_repository_signatures(
    files_by_relative_path: dict[str, _RepositoryFile],
    *,
    verifier: GpgVerifier,
    work_dir: Path,
) -> tuple[tuple[tuple[str, str, SignatureVerification], ...], list[str]]:
    """Verify live detached signatures for one staged Maven repository tree."""

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
        signature_local_path = work_dir / relative_path
        try:
            _copy_local_repository_file(target_file, target_local_path)
            _copy_local_repository_file(signature_file, signature_local_path)
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


def _copy_local_repository_file(repository_file: _RepositoryFile, destination: Path) -> None:
    if repository_file.local_path is None:
        raise ValueError(f"repository file has no local path: {repository_file.relative_path}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with repository_file.local_path.open("rb") as source, destination.open("wb") as target:
        while chunk := source.read(1024 * 1024):
            target.write(chunk)
