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

"""inspect-repro analyzers for OCI image artifacts."""

from __future__ import annotations

from pathlib import Path

from apache_buildish_release_tooling.release.contracts import (
    ArtifactReproducibilityReport,
    OciPlatformDigest,
    OciImageVerificationReport,
)
from apache_buildish_release_tooling.release.progress import ProgressReporter
from apache_buildish_release_tooling.release.verification.schemas import OciImageReproducibilityMetadata
from apache_buildish_release_tooling.release.verification.common import (
    emit_detail,
    emit_failure,
    emit_info,
    emit_success,
    emit_warning,
)
from apache_buildish_release_tooling.release.verification.inspection.shared import (
    evidence_path,
    load_inspection_metadata_model,
)


def inspect_oci_image_reproducibility(
    progress_reporter: ProgressReporter,
    *,
    verification: OciImageVerificationReport,
    reproducibility: ArtifactReproducibilityReport,
    bundle_root: Path,
) -> None:
    """Inspect retained evidence for one OCI image reproducibility failure."""

    metadata_path = evidence_path(
        reproducibility.evidence,
        label="comparison-metadata",
        bundle_root=bundle_root,
    )
    if metadata_path is None:
        emit_warning(progress_reporter, "No comparison metadata was retained for this artifact")
        return
    metadata = load_inspection_metadata_model(
        OciImageReproducibilityMetadata,
        metadata_path,
        payload_label="OCI image reproducibility metadata",
    )
    emit_detail(progress_reporter, "Metadata", str(metadata_path))
    if metadata.image_ref is not None:
        emit_detail(progress_reporter, "Rebuilt image ref", metadata.image_ref)
    rebuilt_digest = metadata.rebuilt_digest
    if rebuilt_digest is not None:
        emit_detail(progress_reporter, "Rebuilt digest", rebuilt_digest)
    declared_digest = metadata.declared_digest
    emit_detail(progress_reporter, "Expected digest", declared_digest)
    top_level_digest_matches = (
        rebuilt_digest is not None and rebuilt_digest == declared_digest
    )
    if rebuilt_digest is not None:
        if top_level_digest_matches:
            emit_success(progress_reporter, "Top-level image digest matched the signed manifest")
        else:
            emit_failure(progress_reporter, "Top-level image digest differs from the signed manifest")
    expected_by_platform = _platform_digest_map(metadata.expected_platform_digests)
    rebuilt_by_platform = _platform_digest_map(metadata.rebuilt_platform_digests)
    changed_platforms: list[str] = []
    missing_platforms: list[str] = []
    unexpected_platforms: list[str] = []
    if expected_by_platform is not None and rebuilt_by_platform is not None:
        emit_detail(progress_reporter, "Expected platforms", str(len(expected_by_platform)))
        emit_detail(progress_reporter, "Rebuilt platforms", str(len(rebuilt_by_platform)))
        changed_platforms = sorted(
            platform
            for platform in expected_by_platform
            if platform in rebuilt_by_platform
            and expected_by_platform[platform] != rebuilt_by_platform[platform]
        )
        missing_platforms = sorted(set(expected_by_platform) - set(rebuilt_by_platform))
        unexpected_platforms = sorted(set(rebuilt_by_platform) - set(expected_by_platform))
        if not changed_platforms and not missing_platforms and not unexpected_platforms:
            emit_success(progress_reporter, "Platform digests matched the signed manifest")
        else:
            emit_failure(
                progress_reporter,
                "Platform digests differ from the signed manifest: "
                f"changed={len(changed_platforms)} "
                f"missing={len(missing_platforms)} "
                f"unexpected={len(unexpected_platforms)}"
            )
            emit_detail(progress_reporter, "Changed platform count", str(len(changed_platforms)))
            emit_detail(progress_reporter, "Missing platform count", str(len(missing_platforms)))
            emit_detail(progress_reporter, "Unexpected platform count", str(len(unexpected_platforms)))
            emit_detail(
                progress_reporter,
                "Platform drift summary",
                f"changed={len(changed_platforms)} missing={len(missing_platforms)} unexpected={len(unexpected_platforms)}",
            )
            for platform in changed_platforms:
                emit_detail(
                    progress_reporter,
                    "Changed platform",
                    f"{platform}: {expected_by_platform[platform]} -> {rebuilt_by_platform[platform]}",
                )
            if missing_platforms:
                emit_detail(progress_reporter, "Missing platforms", ", ".join(missing_platforms))
            if unexpected_platforms:
                emit_detail(progress_reporter, "Unexpected platforms", ", ".join(unexpected_platforms))
    classification = _drift_classification(
        top_level_digest_matches=top_level_digest_matches,
        changed_platforms=changed_platforms,
        missing_platforms=missing_platforms,
        unexpected_platforms=unexpected_platforms,
        platform_details_available=(
            expected_by_platform is not None and rebuilt_by_platform is not None
        ),
    )
    if classification is not None:
        emit_detail(progress_reporter, "Drift classification", classification)
        if classification == "metadata-only":
            emit_info(
                progress_reporter,
                "Likely OCI index/config metadata drift: platform digests match but the top-level digest changed",
            )
        elif classification in {"platform-payload", "top-level-and-platform-payload"}:
            emit_info(
                progress_reporter,
                "Platform payload drift is present; inspect the changed platform digests above first",
            )
            if changed_platforms:
                emit_info(
                    progress_reporter,
                    "OCI hint: compare the rebuilt platform images above before reviewing top-level manifest/index metadata",
                )
            if missing_platforms:
                emit_info(
                    progress_reporter,
                    "OCI hint: at least one expected platform was not rebuilt or published by the local reproduction path",
                )
            if unexpected_platforms:
                emit_info(
                    progress_reporter,
                    "OCI hint: the local rebuild published additional platforms that are absent from the signed manifest",
                )
        elif classification == "top-level-digest-only":
            emit_info(
                progress_reporter,
                "Only the top-level OCI digest evidence was retained; inspect the rebuilt digest first",
            )
            emit_info(
                progress_reporter,
                "OCI hint: compare manifest/config serialization or registry-side index metadata before per-platform payloads",
            )
    if reproducibility.failure_class is not None:
        emit_detail(progress_reporter, "Failure class summary", reproducibility.failure_class)


def _drift_classification(
    *,
    top_level_digest_matches: bool,
    changed_platforms: list[str],
    missing_platforms: list[str],
    unexpected_platforms: list[str],
    platform_details_available: bool,
) -> str | None:
    if not platform_details_available:
        if top_level_digest_matches:
            return None
        return "top-level-digest-only"
    has_platform_drift = bool(changed_platforms or missing_platforms or unexpected_platforms)
    if top_level_digest_matches and not has_platform_drift:
        return None
    if not top_level_digest_matches and not has_platform_drift:
        return "metadata-only"
    if top_level_digest_matches and has_platform_drift:
        return "platform-payload"
    return "top-level-and-platform-payload"


def _platform_digest_map(raw_entries: object) -> dict[str, str] | None:
    if not isinstance(raw_entries, list):
        return None
    entries: dict[str, str] = {}
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, OciPlatformDigest):
            return None
        entries[raw_entry.platform] = raw_entry.digest
    return entries
