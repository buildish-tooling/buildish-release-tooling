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

"""inspect-repro analyzers for Python distribution artifacts."""

from __future__ import annotations

from pathlib import Path

from buildish_release_tooling.release.contracts import (
    ArtifactReproducibilityReport,
    PythonDistributionVerificationReport,
)
from buildish_release_tooling.release.progress import ProgressReporter
from buildish_release_tooling.release.verification.common import emit_detail
from buildish_release_tooling.release.verification.inspection.file_like import (
    inspect_file_like_reproducibility,
)


def inspect_python_distribution_reproducibility(
    progress_reporter: ProgressReporter,
    *,
    verification: PythonDistributionVerificationReport,
    reproducibility: ArtifactReproducibilityReport,
    bundle_root: Path,
) -> None:
    """Inspect retained evidence for one Python distribution reproducibility failure."""

    emit_detail(progress_reporter, "Project", verification.project_name)
    emit_detail(progress_reporter, "Version", verification.version)
    emit_detail(progress_reporter, "Filename", verification.filename)
    emit_detail(progress_reporter, "Distribution type", _distribution_type(verification.filename))
    emit_detail(progress_reporter, "Simple index", verification.index_resolution.project_index_url)
    if verification.index_resolution.sha256_matches_index is not None:
        emit_detail(
            progress_reporter,
            "Simple index hash matched",
            str(verification.index_resolution.sha256_matches_index),
        )
    inspect_file_like_reproducibility(
        progress_reporter,
        verification=verification,
        reproducibility=reproducibility,
        bundle_root=bundle_root,
    )


def _distribution_type(filename: str) -> str:
    normalized = filename.lower()
    if normalized.endswith(".whl"):
        return "wheel"
    if normalized.endswith(".tar.gz") or normalized.endswith(".zip"):
        return "sdist"
    return "unknown"
