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

"""inspect-repro analyzer for source-artifact reproducibility drift."""

from __future__ import annotations

from pathlib import Path

from buildish_release_tooling.release.contracts import (
    ArtifactReproducibilityReport,
    SourceArtifactVerificationSection,
)
from buildish_release_tooling.release.progress import ProgressReporter
from buildish_release_tooling.release.verification.schemas import SourceArtifactReproducibilityMetadata
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
    load_inspection_metadata_model,
    text_diff_paths,
)
from buildish_release_tooling.shared.io import files_equal, first_differing_byte


def inspect_source_artifact_reproducibility(
    progress_reporter: ProgressReporter,
    *,
    verification: SourceArtifactVerificationSection,
    reproducibility: ArtifactReproducibilityReport,
    bundle_root: Path,
) -> None:
    """Inspect retained source-artifact evidence for one reproducibility failure."""

    metadata_path = evidence_path(
        reproducibility.evidence,
        label="comparison-metadata",
        bundle_root=bundle_root,
    )
    if metadata_path is None:
        emit_warning(progress_reporter, "No comparison metadata was retained for the source artifact")
        return
    metadata = load_inspection_metadata_model(
        SourceArtifactReproducibilityMetadata,
        metadata_path,
        payload_label="source-artifact reproducibility metadata",
    )
    emit_detail(progress_reporter, "Metadata", str(metadata_path))
    emit_detail(progress_reporter, "Staged SHA512", metadata.staged_artifact.sha512)
    emit_detail(progress_reporter, "Staged size", str(metadata.staged_artifact.size_bytes))
    rebuilt_metadata = metadata.rebuilt_artifact
    if rebuilt_metadata is not None:
        emit_detail(
            progress_reporter,
            "Rebuilt artifact",
            f"{rebuilt_metadata.filename} ({rebuilt_metadata.sha512})",
        )
    staged_path = evidence_path(
        reproducibility.evidence,
        label="staged-artifact",
        bundle_root=bundle_root,
    )
    rebuilt_path = evidence_path(
        reproducibility.evidence,
        label="rebuilt-artifact",
        bundle_root=bundle_root,
    )
    if staged_path is None or rebuilt_path is None:
        emit_warning(
            progress_reporter,
            "The inspection bundle does not retain both staged and rebuilt source-artifact copies for this failure",
        )
        return
    emit_detail(progress_reporter, "Source artifact", verification.filename or "n/a")
    emit_detail(progress_reporter, "Staged artifact", str(staged_path))
    emit_detail(progress_reporter, "Rebuilt artifact", str(rebuilt_path))
    if files_equal(staged_path, rebuilt_path):
        emit_success(progress_reporter, "Retained staged and rebuilt source-artifact copies are identical")
        return
    emit_failure(progress_reporter, "Retained staged and rebuilt source-artifact copies differ")
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
    if archive_analysis is not None and archive_analysis.classification == "outer-container-drift":
        emit_info(
            progress_reporter,
            "Source artifact hint: this often points to gzip or outer tarball container settings rather than source-tree content drift",
        )
    elif archive_analysis is not None and archive_analysis.classification == "entry-metadata-drift":
        emit_info(
            progress_reporter,
            "Source artifact hint: compare tar member mtimes, modes, ownership fields, and archive file selection",
        )
    elif archive_analysis is not None and archive_analysis.classification == "entry-order-drift":
        emit_info(
            progress_reporter,
            "Source artifact hint: compare tar member ordering and source tree enumeration before packing",
        )
    elif archive_analysis is not None and archive_analysis.classification == "entry-content-drift":
        emit_info(
            progress_reporter,
            "Source artifact hint: compare the materialized source tree and any generated files before packaging",
        )
    elif archive_analysis is not None and archive_analysis.classification == "mixed-entry-drift":
        emit_info(
            progress_reporter,
            "Source artifact hint: more than one source archive dimension changed; start with member metadata before payload drift",
        )
    inline_diff = text_diff_paths(staged_path, rebuilt_path)
    if inline_diff:
        emit_info(progress_reporter, "Unified text diff")
        for line in inline_diff:
            progress_reporter.emit(f"    {line}")
