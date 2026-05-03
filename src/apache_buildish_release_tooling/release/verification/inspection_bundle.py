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

"""Helpers for curated verify-rc reproducibility inspection bundles."""

from __future__ import annotations

import shutil
from pathlib import Path
import re

from pydantic import BaseModel

from apache_buildish_release_tooling.release.contracts import (
    ArtifactReproducibilityReport,
    InspectionBundleArtifactEntry,
)
from apache_buildish_release_tooling.release.manifest import write_manifest
from apache_buildish_release_tooling.release.verification.schemas import (
    InspectionBundleManifestV1,
    VerifyRcReportV1,
)

_SAFE_PATH_COMPONENT_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
INSPECTION_BUNDLE_MANIFEST_FILENAME = "inspection-bundle.json"


def safe_path_component(value: str) -> str:
    normalized = _SAFE_PATH_COMPONENT_PATTERN.sub("-", value).strip("-")
    return normalized or "secondary-artifact"


def reproducibility_artifact_directory(bundle_root: Path, *, artifact_id: str) -> Path:
    """Return the bundle directory reserved for one artifact's reproducibility evidence."""

    return bundle_root / "secondary-artifacts" / safe_path_component(artifact_id) / "reproducibility"


def source_artifact_reproducibility_directory(bundle_root: Path) -> Path:
    """Return the bundle directory reserved for source-artifact reproducibility evidence."""

    return bundle_root / "source-artifact" / "reproducibility"


def write_reproducibility_metadata(
    bundle_root: Path,
    *,
    artifact_id: str,
    payload: BaseModel,
) -> str:
    """Write one reproducibility metadata JSON file and return its bundle-relative path."""

    metadata_path = reproducibility_artifact_directory(bundle_root, artifact_id=artifact_id) / "metadata.json"
    write_manifest(metadata_path, payload)
    return str(metadata_path.relative_to(bundle_root))


def write_source_artifact_reproducibility_metadata(
    bundle_root: Path,
    *,
    payload: BaseModel,
) -> str:
    """Write source-artifact reproducibility metadata and return its bundle-relative path."""

    metadata_path = source_artifact_reproducibility_directory(bundle_root) / "metadata.json"
    write_manifest(metadata_path, payload)
    return str(metadata_path.relative_to(bundle_root))


def retain_evidence_file(
    bundle_root: Path,
    *,
    artifact_id: str,
    label_directory: str,
    source_path: Path,
) -> str:
    """Copy one retained evidence file into the inspection bundle and return its relative path."""

    target_path = (
        reproducibility_artifact_directory(bundle_root, artifact_id=artifact_id)
        / safe_path_component(label_directory)
        / source_path.name
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, target_path)
    return str(target_path.relative_to(bundle_root))


def retain_source_artifact_evidence_file(
    bundle_root: Path,
    *,
    label_directory: str,
    source_path: Path,
) -> str:
    """Copy one source-artifact evidence file into the inspection bundle and return its relative path."""

    target_path = (
        source_artifact_reproducibility_directory(bundle_root)
        / safe_path_component(label_directory)
        / source_path.name
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, target_path)
    return str(target_path.relative_to(bundle_root))


def write_inspection_bundle_manifest(
    bundle_root: Path,
    *,
    report_payload: VerifyRcReportV1,
) -> str:
    """Write the top-level inspection-bundle contract manifest."""

    manifest_path = bundle_root / INSPECTION_BUNDLE_MANIFEST_FILENAME
    bundle_manifest = InspectionBundleManifestV1(
        report_schema_version=report_payload.schema_version,
        component_id=report_payload.component_id,
        version=report_payload.version,
        rc_tag=report_payload.rc_tag,
        artifacts=_bundle_artifact_entries(report_payload),
    )
    write_manifest(manifest_path, bundle_manifest)
    return str(manifest_path.relative_to(bundle_root))


def _bundle_artifact_entries(report_payload: VerifyRcReportV1) -> list[InspectionBundleArtifactEntry]:
    entries: list[InspectionBundleArtifactEntry] = []
    source_reproducibility = report_payload.source_artifact_verification.reproducibility
    source_metadata_path = _comparison_metadata_path(source_reproducibility)
    if source_metadata_path is not None:
        entries.append(
            InspectionBundleArtifactEntry(
                artifact_id="source-artifact",
                kind="source-artifact",
                metadata_path=source_metadata_path,
            )
        )
    for verification in report_payload.secondary_artifact_verifications:
        reproducibility = getattr(verification, "reproducibility", None)
        metadata_path = _comparison_metadata_path(reproducibility)
        if metadata_path is None:
            continue
        entries.append(
            InspectionBundleArtifactEntry(
                artifact_id=verification.artifact_id,
                kind=verification.kind,
                metadata_path=metadata_path,
            )
        )
    return entries


def _comparison_metadata_path(
    reproducibility: ArtifactReproducibilityReport | None,
) -> str | None:
    if reproducibility is None:
        return None
    for evidence in reproducibility.evidence:
        if evidence.label == "comparison-metadata":
            return evidence.path
    return None
