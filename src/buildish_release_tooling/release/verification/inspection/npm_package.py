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

"""inspect-repro analyzers for npm package artifacts."""

from __future__ import annotations

from pathlib import Path

from buildish_release_tooling.release.contracts import (
    ArtifactReproducibilityReport,
    NpmPackageVerificationReport,
)
from buildish_release_tooling.release.progress import ProgressReporter
from buildish_release_tooling.release.verification.common import emit_detail
from buildish_release_tooling.release.verification.inspection.file_like import (
    inspect_file_like_reproducibility,
)


def inspect_npm_package_reproducibility(
    progress_reporter: ProgressReporter,
    *,
    verification: NpmPackageVerificationReport,
    reproducibility: ArtifactReproducibilityReport,
    bundle_root: Path,
) -> None:
    """Inspect retained evidence for one npm package reproducibility failure."""

    emit_detail(progress_reporter, "Package", verification.package_name)
    emit_detail(progress_reporter, "Version", verification.version)
    emit_detail(progress_reporter, "Filename", verification.filename)
    emit_detail(progress_reporter, "Registry URL", verification.registry_url)
    emit_detail(progress_reporter, "Tarball URL", verification.uri)
    emit_detail(
        progress_reporter,
        "Declared integrity",
        verification.integrity.value or "n/a",
    )
    if verification.registry_resolution.metadata_url is not None:
        emit_detail(
            progress_reporter,
            "Registry metadata",
            verification.registry_resolution.metadata_url,
        )
    if verification.registry_resolution.integrity_matches_manifest is not None:
        emit_detail(
            progress_reporter,
            "Registry integrity matched",
            str(verification.registry_resolution.integrity_matches_manifest),
        )
    inspect_file_like_reproducibility(
        progress_reporter,
        verification=verification,
        reproducibility=reproducibility,
        bundle_root=bundle_root,
    )
