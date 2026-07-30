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

"""inspect-repro analyzers for file-like artifacts."""

from __future__ import annotations

from pathlib import Path

from buildish_release_tooling.release.contracts import (
    ArtifactReproducibilityReport,
    GenericFileVerificationReport,
    NpmPackageVerificationReport,
    PythonDistributionVerificationReport,
    ShallowArchiveAnalysisReport,
)
from buildish_release_tooling.release.progress import ProgressReporter
from buildish_release_tooling.release.verification.schemas import FileLikeReproducibilityMetadata
from buildish_release_tooling.release.verification.common import (
    emit_detail,
    emit_failure,
    emit_info,
    emit_success,
    emit_warning,
)
from buildish_release_tooling.release.verification.inspection.archive_shallow import (
    emit_shallow_archive_analysis,
    inspect_shallow_archive_pair,
)
from buildish_release_tooling.release.verification.inspection.shared import (
    evidence_path,
    first_matching_evidence_path,
    load_inspection_metadata_model,
    text_diff_paths,
)
from buildish_release_tooling.shared.io import files_equal, first_differing_byte


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
    metadata = load_inspection_metadata_model(
        FileLikeReproducibilityMetadata,
        metadata_path,
        payload_label="file-like reproducibility metadata",
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
    staged_size = staged_path.stat().st_size
    rebuilt_size = rebuilt_path.stat().st_size
    if files_equal(staged_path, rebuilt_path):
        emit_success(progress_reporter, "Retained staged and rebuilt artifact copies are identical")
        return
    inline_diff = text_diff_paths(staged_path, rebuilt_path)
    drift_classification = _classify_file_like_drift(
        staged_size,
        rebuilt_size,
        inline_diff=inline_diff,
    )
    emit_failure(progress_reporter, "Retained staged and rebuilt artifact copies differ")
    emit_detail(progress_reporter, "Drift classification", drift_classification)
    emit_detail(progress_reporter, "Staged byte count", str(staged_size))
    emit_detail(progress_reporter, "Rebuilt byte count", str(rebuilt_size))
    emit_detail(progress_reporter, "Size delta bytes", str(rebuilt_size - staged_size))
    emit_detail(
        progress_reporter,
        "First differing byte",
        str(first_differing_byte(staged_path, rebuilt_path)),
    )
    archive_analysis = metadata.archive_analysis
    if not emit_shallow_archive_analysis(
        progress_reporter,
        analysis=archive_analysis,
    ):
        inspect_shallow_archive_pair(
            progress_reporter,
            staged_path=staged_path,
            rebuilt_path=rebuilt_path,
        )
    _emit_file_like_archive_hint(
        progress_reporter,
        verification=verification,
        archive_analysis=archive_analysis,
    )
    if inline_diff:
        emit_info(progress_reporter, "Unified text diff")
        for line in inline_diff:
            progress_reporter.emit(f"    {line}")


def _classify_file_like_drift(
    staged_size: int,
    rebuilt_size: int,
    *,
    inline_diff: list[str],
) -> str:
    same_size = staged_size == rebuilt_size
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
            emit_info(progress_reporter, _wheel_hint(archive_analysis.classification))
            return
        if distribution_type == "sdist":
            emit_info(
                progress_reporter,
                _sdist_hint(archive_analysis.classification),
            )
            return
    if isinstance(verification, NpmPackageVerificationReport):
        emit_info(progress_reporter, _npm_hint(archive_analysis.classification))


def _wheel_hint(classification: str) -> str:
    if classification == "entry-metadata-drift":
        return (
            "Wheel hint: compare ZIP member mtimes, permissions, and wheel metadata files such as "
            "*.dist-info/RECORD"
        )
    if classification == "entry-order-drift":
        return "Wheel hint: compare wheel member ordering and file enumeration in the build backend"
    if classification == "outer-container-drift":
        return (
            "Wheel hint: ZIP container bytes changed while member payloads stayed stable; compare "
            "archive-level metadata first"
        )
    if classification == "entry-content-drift":
        return "Wheel hint: compare generated wheel payload files and *.dist-info contents"
    return "Wheel hint: this often points to ZIP member metadata, entry order, or wheel payload generation drift"


def _sdist_hint(classification: str) -> str:
    if classification == "entry-metadata-drift":
        return "Sdist hint: compare tar member mtimes, modes, ownership fields, and file selection"
    if classification == "entry-order-drift":
        return "Sdist hint: compare tar member ordering and source tree enumeration before packing"
    if classification == "outer-container-drift":
        return "Sdist hint: compare outer compression or tarball container settings before source-tree contents"
    if classification == "entry-content-drift":
        return "Sdist hint: compare source packaging inputs and generated files included in the archive"
    return "Sdist hint: this often points to tar member metadata, file selection, or source packaging drift"


def _npm_hint(classification: str) -> str:
    if classification == "entry-metadata-drift":
        return "npm hint: compare tar header mtime, mode, owner, and package file selection from npm pack"
    if classification == "entry-order-drift":
        return "npm hint: compare npm pack file ordering and the final package file list"
    if classification == "outer-container-drift":
        return "npm hint: compare outer gzip or tarball container bytes before generated package contents"
    if classification == "entry-content-drift":
        return "npm hint: compare generated package contents and files selected by npm pack"
    return "npm hint: this often points to npm pack file selection, tar header metadata, or generated package contents"


def _distribution_type(filename: str) -> str:
    normalized = filename.lower()
    if normalized.endswith(".whl"):
        return "wheel"
    if normalized.endswith(".tar.gz") or normalized.endswith(".zip"):
        return "sdist"
    return "unknown"
