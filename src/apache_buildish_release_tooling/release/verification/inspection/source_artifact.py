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

"""inspect-repro analyzer for source-artifact reproducibility drift."""

from __future__ import annotations

import json
from pathlib import Path

from apache_buildish_release_tooling.release.contracts import (
    ArtifactReproducibilityReport,
    SourceArtifactVerificationSection,
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
    text_diff,
)


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
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    emit_detail(progress_reporter, "Metadata", str(metadata_path))
    staged_metadata = metadata.get("staged_artifact", {})
    if isinstance(staged_metadata, dict):
        emit_detail(progress_reporter, "Staged SHA512", str(staged_metadata.get("sha512", "n/a")))
        emit_detail(progress_reporter, "Staged size", str(staged_metadata.get("size_bytes", "n/a")))
    rebuilt_metadata = metadata.get("rebuilt_artifact", {})
    if isinstance(rebuilt_metadata, dict):
        emit_detail(
            progress_reporter,
            "Rebuilt artifact",
            f"{rebuilt_metadata.get('filename', 'n/a')} ({rebuilt_metadata.get('sha512', 'n/a')})",
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
    staged_bytes = staged_path.read_bytes()
    rebuilt_bytes = rebuilt_path.read_bytes()
    if staged_bytes == rebuilt_bytes:
        emit_success(progress_reporter, "Retained staged and rebuilt source-artifact copies are identical")
        return
    emit_failure(progress_reporter, "Retained staged and rebuilt source-artifact copies differ")
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
    archive_analysis = metadata.get("archive_analysis")
    if isinstance(archive_analysis, dict) and archive_analysis.get("classification") == "outer-container-drift":
        emit_info(
            progress_reporter,
            "Source artifact hint: this often points to gzip or outer tarball container settings rather than source-tree content drift",
        )
    inline_diff = text_diff(staged_bytes, rebuilt_bytes)
    if inline_diff:
        emit_info(progress_reporter, "Unified text diff")
        for line in inline_diff:
            progress_reporter.emit(f"    {line}")
