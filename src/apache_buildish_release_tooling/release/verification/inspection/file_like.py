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

"""inspect-repro analyzers for file-like artifacts."""

from __future__ import annotations

from pathlib import Path

from apache_buildish_release_tooling.release.contracts import (
    ArtifactReproducibilityReport,
    FileLikeReproducibilityMetadata,
    GenericFileVerificationReport,
    NpmPackageVerificationReport,
    PythonDistributionVerificationReport,
    ShallowArchiveAnalysisReport,
)
from apache_buildish_release_tooling.release.progress import ProgressReporter
from apache_buildish_release_tooling.release.verification.common import (
    emit_detail,
    emit_failure,
    emit_info,
    emit_success,
    emit_warning,
)
from apache_buildish_release_tooling.release.verification.inspection.archive_shallow import (
    inspect_shallow_archive_pair,
)
from apache_buildish_release_tooling.release.verification.inspection.shared import (
    evidence_path,
    first_differing_byte,
    first_matching_evidence_path,
    text_diff,
)


def inspect_file_like_reproducibility(
    progress_reporter: ProgressReporter,
    *,
    verification: GenericFileVerificationReport
    | PythonDistributionVerificationReport
    | NpmPackageVerificationReport,
    reproducibility: ArtifactReproducibilityReport,
    bundle_root: Path,
) -> None:
    """Inspect retained evidence for one file-like artifact reproducibility failure."""

    metadata_path = evidence_path(
        reproducibility.evidence,
        label="comparison-metadata",
        bundle_root=bundle_root,
    )
    if metadata_path is None:
        emit_warning(progress_reporter, "No comparison metadata was retained for this artifact")
        return
    metadata = FileLikeReproducibilityMetadata.model_validate_json(
        metadata_path.read_text(encoding="utf-8")
    )
    emit_detail(progress_reporter, "Metadata", str(metadata_path))
    emit_detail(progress_reporter, "Staged SHA512", metadata.staged_artifact.sha512)
    emit_detail(progress_reporter, "Staged size", str(metadata.staged_artifact.size_bytes))
    for output in metadata.rebuilt_outputs:
        emit_detail(
            progress_reporter,
            "Rebuilt output",
            f"{output.path} ({output.sha512})",
        )
    staged_path = evidence_path(
        reproducibility.evidence,
        label="staged-artifact",
        bundle_root=bundle_root,
    )
    rebuilt_path = first_matching_evidence_path(
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
    inline_diff = text_diff(staged_bytes, rebuilt_bytes)
    drift_classification = _classify_file_like_drift(
        staged_bytes,
        rebuilt_bytes,
        inline_diff=inline_diff,
    )
    emit_failure(progress_reporter, "Retained staged and rebuilt artifact copies differ")
    emit_detail(progress_reporter, "Drift classification", drift_classification)
    emit_detail(progress_reporter, "Staged byte count", str(len(staged_bytes)))
    emit_detail(progress_reporter, "Rebuilt byte count", str(len(rebuilt_bytes)))
    emit_detail(progress_reporter, "Size delta bytes", str(len(rebuilt_bytes) - len(staged_bytes)))
    emit_detail(
        progress_reporter,
        "First differing byte",
        str(first_differing_byte(staged_bytes, rebuilt_bytes)),
    )
    inspect_shallow_archive_pair(
        progress_reporter,
        staged_path=staged_path,
        rebuilt_path=rebuilt_path,
    )
    _emit_file_like_archive_hint(
        progress_reporter,
        verification=verification,
        archive_analysis=metadata.archive_analysis,
    )
    if inline_diff:
        emit_info(progress_reporter, "Unified text diff")
        for line in inline_diff:
            progress_reporter.emit(f"    {line}")


def _classify_file_like_drift(
    staged_bytes: bytes,
    rebuilt_bytes: bytes,
    *,
    inline_diff: list[str],
) -> str:
    same_size = len(staged_bytes) == len(rebuilt_bytes)
    if inline_diff:
        return "text-content-drift" if same_size else "size-and-text-drift"
    return "binary-content-drift" if same_size else "size-and-binary-drift"


def _emit_file_like_archive_hint(
    progress_reporter: ProgressReporter,
    *,
    verification: GenericFileVerificationReport
    | PythonDistributionVerificationReport
    | NpmPackageVerificationReport,
    archive_analysis: ShallowArchiveAnalysisReport | None,
) -> None:
    if archive_analysis is None:
        return
    if isinstance(verification, PythonDistributionVerificationReport):
        distribution_type = _distribution_type(verification.filename)
        if distribution_type == "wheel":
            emit_info(
                progress_reporter,
                "Wheel hint: this often points to ZIP member metadata, entry order, or wheel payload generation drift",
            )
            return
        if distribution_type == "sdist":
            emit_info(
                progress_reporter,
                "Sdist hint: this often points to tar member metadata, file selection, or source packaging drift",
            )
            return
    if isinstance(verification, NpmPackageVerificationReport):
        emit_info(
            progress_reporter,
            "npm hint: this often points to npm pack file selection, tar header metadata, or generated package contents",
        )


def _distribution_type(filename: str) -> str:
    normalized = filename.lower()
    if normalized.endswith(".whl"):
        return "wheel"
    if normalized.endswith(".tar.gz") or normalized.endswith(".zip"):
        return "sdist"
    return "unknown"
