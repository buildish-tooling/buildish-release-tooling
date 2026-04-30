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

"""Read-only post-verification reproducibility inspection helpers."""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import cast

from apache_buildish_release_tooling.release.contracts import (
    AnySecondaryArtifactVerification,
    ArtifactReproducibilityReport,
    GenericFileVerificationReport,
    InspectionEvidenceReference,
    MavenRepositoryVerificationReport,
    NpmPackageVerificationReport,
    OciImageVerificationReport,
    PythonDistributionVerificationReport,
    VerifyRcReportV1,
)
from apache_buildish_release_tooling.release.progress import ProgressReporter
from apache_buildish_release_tooling.release.verification.common import (
    emit_detail,
    emit_failure,
    emit_info,
    emit_section,
    emit_success,
    emit_title,
    emit_warning,
)

_MAX_INLINE_TEXT_DIFF_LINES = 12
_MAX_INLINE_TEXT_BYTES = 65536


def inspect_repro_report(report_path: Path, *, progress_reporter: ProgressReporter) -> None:
    """Read one saved verify-rc report and inspect any retained reproducibility evidence."""

    report = VerifyRcReportV1.model_validate_json(report_path.read_text(encoding="utf-8"))
    inspection_bundle = report.inspection_bundle
    if inspection_bundle is None:
        raise ValueError(
            f"verify-rc report does not reference an inspection bundle: {report_path}"
        )
    bundle_root = (report_path.parent / inspection_bundle.relative_path_from_report).resolve()
    if not bundle_root.exists():
        raise ValueError(
            f"inspection bundle referenced by verify-rc report does not exist: {bundle_root}"
        )
    emit_title(progress_reporter, "Inspect Repro")
    emit_detail(progress_reporter, "Report JSON", str(report_path))
    emit_detail(progress_reporter, "Inspection bundle", str(bundle_root))
    emit_section(progress_reporter, "Summary")
    emit_detail(progress_reporter, "Component", report.component_id or "n/a")
    emit_detail(progress_reporter, "RC tag", report.rc_tag or "n/a")
    emit_detail(progress_reporter, "Report verdict", report.verdict)
    emit_detail(
        progress_reporter,
        "Build checks attempted",
        str(report.reproducibility_execution.build_checks_attempted),
    )
    failing_reproducibility_checks: list[
        tuple[AnySecondaryArtifactVerification, ArtifactReproducibilityReport]
    ] = []
    for verification in report.secondary_artifact_verifications:
        reproducibility = getattr(verification, "reproducibility", None)
        if not isinstance(reproducibility, ArtifactReproducibilityReport):
            continue
        if reproducibility.verdict != "failed":
            continue
        failing_reproducibility_checks.append((verification, reproducibility))
    if not failing_reproducibility_checks:
        emit_success(progress_reporter, "No reproducibility failures recorded in the verify-rc report")
        return
    emit_info(
        progress_reporter,
        f"Inspecting {len(failing_reproducibility_checks)} reproducibility failure(s) from the saved bundle",
    )
    for index, (verification, reproducibility) in enumerate(failing_reproducibility_checks, start=1):
        emit_section(
            progress_reporter,
            f"Artifact {index}/{len(failing_reproducibility_checks)}: {verification.artifact_id}",
        )
        emit_detail(progress_reporter, "Kind", verification.kind)
        emit_detail(progress_reporter, "Profile", reproducibility.profile_id)
        emit_detail(
            progress_reporter,
            "Comparison mode",
            reproducibility.comparison_mode,
        )
        if reproducibility.failure_class is not None:
            emit_detail(
                progress_reporter,
                "Failure class",
                reproducibility.failure_class,
            )
        if verification.kind in {"generic-file", "generic-file-with-openpgp"}:
            _inspect_file_like_reproducibility(
                progress_reporter,
                verification=cast(GenericFileVerificationReport, verification),
                reproducibility=reproducibility,
                bundle_root=bundle_root,
            )
            continue
        if verification.kind == "python-distribution":
            _inspect_file_like_reproducibility(
                progress_reporter,
                verification=verification,
                reproducibility=reproducibility,
                bundle_root=bundle_root,
            )
            continue
        if verification.kind == "npm-package":
            _inspect_file_like_reproducibility(
                progress_reporter,
                verification=verification,
                reproducibility=reproducibility,
                bundle_root=bundle_root,
            )
            continue
        if verification.kind == "maven-repository":
            _inspect_maven_repository_reproducibility(
                progress_reporter,
                verification=verification,
                reproducibility=reproducibility,
                bundle_root=bundle_root,
            )
            continue
        if verification.kind == "oci-image":
            _inspect_oci_image_reproducibility(
                progress_reporter,
                verification=verification,
                reproducibility=reproducibility,
                bundle_root=bundle_root,
            )
            continue
        emit_warning(
            progress_reporter,
            f"No inspect-repro analyzer is implemented yet for {verification.kind}",
        )


def _inspect_file_like_reproducibility(
    progress_reporter: ProgressReporter,
    *,
    verification: GenericFileVerificationReport | PythonDistributionVerificationReport | NpmPackageVerificationReport,
    reproducibility: ArtifactReproducibilityReport,
    bundle_root: Path,
) -> None:
    metadata_path = _evidence_path(
        reproducibility.evidence,
        label="comparison-metadata",
        bundle_root=bundle_root,
    )
    if metadata_path is None:
        emit_warning(progress_reporter, "No comparison metadata was retained for this artifact")
        return
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    emit_detail(progress_reporter, "Metadata", str(metadata_path))
    staged_metadata = metadata.get("staged_artifact", {})
    if isinstance(staged_metadata, dict):
        emit_detail(
            progress_reporter,
            "Staged SHA512",
            str(staged_metadata.get("sha512", "n/a")),
        )
        emit_detail(
            progress_reporter,
            "Staged size",
            str(staged_metadata.get("size_bytes", "n/a")),
        )
    rebuilt_outputs = metadata.get("rebuilt_outputs", [])
    if isinstance(rebuilt_outputs, list):
        for output in rebuilt_outputs:
            if not isinstance(output, dict):
                continue
            emit_detail(
                progress_reporter,
                "Rebuilt output",
                f"{output.get('path', 'n/a')} ({output.get('sha512', 'n/a')})",
            )
    staged_path = _evidence_path(
        reproducibility.evidence,
        label="staged-artifact",
        bundle_root=bundle_root,
    )
    rebuilt_path = _first_matching_evidence_path(
        reproducibility.evidence,
        label_prefix="rebuilt-artifact",
        bundle_root=bundle_root,
    )
    if staged_path is None or rebuilt_path is None:
        emit_warning(
            progress_reporter,
            "The inspection bundle does not retain both staged and rebuilt artifact copies for this failure",
        )
        return
    emit_detail(progress_reporter, "Staged artifact", str(staged_path))
    emit_detail(progress_reporter, "Rebuilt artifact", str(rebuilt_path))
    staged_bytes = staged_path.read_bytes()
    rebuilt_bytes = rebuilt_path.read_bytes()
    if staged_bytes == rebuilt_bytes:
        emit_success(progress_reporter, "Retained staged and rebuilt artifact copies are identical")
        return
    emit_failure(progress_reporter, "Retained staged and rebuilt artifact copies differ")
    emit_detail(
        progress_reporter,
        "First differing byte",
        str(_first_differing_byte(staged_bytes, rebuilt_bytes)),
    )
    inline_diff = _text_diff(staged_bytes, rebuilt_bytes)
    if inline_diff:
        emit_info(progress_reporter, "Unified text diff")
        for line in inline_diff:
            progress_reporter.emit(f"    {line}")


def _inspect_maven_repository_reproducibility(
    progress_reporter: ProgressReporter,
    *,
    verification: MavenRepositoryVerificationReport,
    reproducibility: ArtifactReproducibilityReport,
    bundle_root: Path,
) -> None:
    metadata_path = _evidence_path(
        reproducibility.evidence,
        label="comparison-metadata",
        bundle_root=bundle_root,
    )
    if metadata_path is None:
        emit_warning(progress_reporter, "No comparison metadata was retained for this artifact")
        return
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    emit_detail(progress_reporter, "Metadata", str(metadata_path))
    repository_dir = metadata.get("repository_dir")
    if isinstance(repository_dir, str):
        emit_detail(progress_reporter, "Repository dir", repository_dir)
    output_paths = metadata.get("output_paths")
    if isinstance(output_paths, list):
        for output_path in output_paths:
            if isinstance(output_path, str):
                emit_detail(progress_reporter, "Rebuild output", output_path)
    path_results = metadata.get("path_results")
    if not isinstance(path_results, list):
        emit_warning(progress_reporter, "No repository path results were retained for this artifact")
        return
    failed_results = [
        path_result
        for path_result in path_results
        if isinstance(path_result, dict) and path_result.get("verdict") == "failed"
    ]
    skipped_results = [
        path_result
        for path_result in path_results
        if isinstance(path_result, dict) and path_result.get("verdict") == "skipped"
    ]
    emit_detail(progress_reporter, "Failed comparable paths", str(len(failed_results)))
    emit_detail(progress_reporter, "Skipped remote-only paths", str(len(skipped_results)))
    if not failed_results:
        emit_success(progress_reporter, "No failed comparable repository paths were retained")
        return
    emit_failure(
        progress_reporter,
        f"{len(failed_results)} comparable repository path(s) failed local comparison",
    )
    for path_result in failed_results[:12]:
        emit_detail(
            progress_reporter,
            "Path failure",
            f"{path_result.get('path', 'n/a')} [{path_result.get('mode', 'n/a')}] {path_result.get('detail', 'n/a')}",
        )
    if len(failed_results) > 12:
        emit_info(
            progress_reporter,
            f"... plus {len(failed_results) - 12} additional failed path(s)",
        )


def _inspect_oci_image_reproducibility(
    progress_reporter: ProgressReporter,
    *,
    verification: OciImageVerificationReport,
    reproducibility: ArtifactReproducibilityReport,
    bundle_root: Path,
) -> None:
    metadata_path = _evidence_path(
        reproducibility.evidence,
        label="comparison-metadata",
        bundle_root=bundle_root,
    )
    if metadata_path is None:
        emit_warning(progress_reporter, "No comparison metadata was retained for this artifact")
        return
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    emit_detail(progress_reporter, "Metadata", str(metadata_path))
    image_ref = metadata.get("image_ref")
    if isinstance(image_ref, str):
        emit_detail(progress_reporter, "Rebuilt image ref", image_ref)
    rebuilt_digest = metadata.get("rebuilt_digest")
    if isinstance(rebuilt_digest, str):
        emit_detail(progress_reporter, "Rebuilt digest", rebuilt_digest)
    declared_digest = metadata.get("declared_digest")
    if isinstance(declared_digest, str):
        emit_detail(progress_reporter, "Expected digest", declared_digest)
    rebuilt_platform_digests = metadata.get("rebuilt_platform_digests")
    if isinstance(rebuilt_platform_digests, list):
        emit_detail(progress_reporter, "Rebuilt platform digests", json.dumps(rebuilt_platform_digests))
    expected_platform_digests = metadata.get("expected_platform_digests")
    if isinstance(expected_platform_digests, list):
        emit_detail(progress_reporter, "Expected platform digests", json.dumps(expected_platform_digests))
    if reproducibility.failure_class is not None:
        emit_failure(
            progress_reporter,
            f"OCI reproducibility failed with class {reproducibility.failure_class}",
        )


def _evidence_path(
    evidence: list[InspectionEvidenceReference],
    *,
    label: str,
    bundle_root: Path,
) -> Path | None:
    for reference in evidence:
        if reference.label == label:
            candidate_path = bundle_root / reference.path
            if candidate_path.exists():
                return candidate_path
    return None


def _first_matching_evidence_path(
    evidence: list[InspectionEvidenceReference],
    *,
    label_prefix: str,
    bundle_root: Path,
) -> Path | None:
    for reference in evidence:
        if not reference.label.startswith(label_prefix):
            continue
        candidate_path = bundle_root / reference.path
        if candidate_path.exists():
            return candidate_path
    return None


def _first_differing_byte(left: bytes, right: bytes) -> int:
    shared_length = min(len(left), len(right))
    for index in range(shared_length):
        if left[index] != right[index]:
            return index
    return shared_length


def _text_diff(left: bytes, right: bytes) -> list[str]:
    if len(left) > _MAX_INLINE_TEXT_BYTES or len(right) > _MAX_INLINE_TEXT_BYTES:
        return []
    try:
        left_text = left.decode("utf-8")
        right_text = right.decode("utf-8")
    except UnicodeDecodeError:
        return []
    if "\x00" in left_text or "\x00" in right_text:
        return []
    diff_lines = list(
        difflib.unified_diff(
            left_text.splitlines(),
            right_text.splitlines(),
            fromfile="staged",
            tofile="rebuilt",
            lineterm="",
        )
    )
    return diff_lines[:_MAX_INLINE_TEXT_DIFF_LINES]
