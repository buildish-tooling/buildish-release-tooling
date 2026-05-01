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

"""inspect-repro analyzers for Maven repository artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from apache_buildish_release_tooling.release.contracts import (
    ArtifactReproducibilityReport,
    MavenRepositoryVerificationReport,
)
from apache_buildish_release_tooling.release.progress import ProgressReporter
from apache_buildish_release_tooling.release.verification.common import (
    emit_detail,
    emit_failure,
    emit_info,
    emit_success,
    emit_warning,
)
from apache_buildish_release_tooling.release.verification.inspection.shared import evidence_path


def inspect_maven_repository_reproducibility(
    progress_reporter: ProgressReporter,
    *,
    verification: MavenRepositoryVerificationReport,
    reproducibility: ArtifactReproducibilityReport,
    bundle_root: Path,
) -> None:
    """Inspect retained evidence for one Maven repository reproducibility failure."""

    metadata_path = evidence_path(
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
    verified_results = [
        path_result
        for path_result in path_results
        if isinstance(path_result, dict) and path_result.get("verdict") == "verified"
    ]
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
    emit_detail(progress_reporter, "Compared staged paths", str(len(path_results)))
    emit_detail(progress_reporter, "Verified comparable paths", str(len(verified_results)))
    emit_detail(progress_reporter, "Failed comparable paths", str(len(failed_results)))
    emit_detail(progress_reporter, "Skipped remote-only paths", str(len(skipped_results)))
    if not failed_results:
        emit_success(progress_reporter, "No failed comparable repository paths were retained")
        return
    emit_detail(progress_reporter, "Failed by mode", _failed_mode_summary(failed_results))
    diagnosis = _failure_diagnosis(failed_results)
    if diagnosis is not None:
        emit_info(progress_reporter, diagnosis)
    emit_failure(
        progress_reporter,
        f"{len(failed_results)} comparable repository path(s) failed local comparison",
    )
    for path_result in failed_results[:12]:
        staged_sha512 = path_result.get("staged_sha512")
        rebuilt_sha512 = path_result.get("rebuilt_sha512")
        digest_suffix = ""
        if isinstance(staged_sha512, str) and isinstance(rebuilt_sha512, str):
            digest_suffix = f" [{staged_sha512[:12]} -> {rebuilt_sha512[:12]}]"
        emit_detail(
            progress_reporter,
            "Path failure",
            (
                f"{path_result.get('path', 'n/a')} "
                f"[{path_result.get('mode', 'n/a')}] "
                f"{path_result.get('detail', 'n/a')}{digest_suffix}"
            ),
        )
    if len(failed_results) > 12:
        emit_info(
            progress_reporter,
            f"... plus {len(failed_results) - 12} additional failed path(s)",
        )


def _failed_mode_summary(failed_results: list[dict[str, object]]) -> str:
    counts: dict[str, int] = {}
    for path_result in failed_results:
        mode = path_result.get("mode")
        if not isinstance(mode, str):
            mode = "unknown"
        counts[mode] = counts.get(mode, 0) + 1
    return ", ".join(f"{mode}={counts[mode]}" for mode in sorted(counts))


def _failure_diagnosis(failed_results: list[dict[str, object]]) -> str | None:
    metadata_text_suffixes = (".pom", ".module", ".xml", ".properties", ".txt")
    if all(
        isinstance(path_result.get("path"), str)
        and str(path_result.get("path")).endswith(metadata_text_suffixes)
        and path_result.get("detail") == "raw bytes differ"
        and path_result.get("mode") == "exact-bytes"
        for path_result in failed_results
    ):
        return (
            "Likely descriptor/text drift: comparable Maven metadata files changed while "
            "archive payload comparisons were left to stricter or normalized per-path policy"
        )
    if any(path_result.get("detail") == "missing rebuilt path" for path_result in failed_results):
        return "The local rebuild did not reproduce at least one staged comparable repository path"
    if any(
        isinstance(path_result.get("detail"), str)
        and "archive members differ" in str(path_result.get("detail"))
        for path_result in failed_results
    ):
        return "Archive member drift is present inside one or more rebuilt repository artifacts"
    return None
