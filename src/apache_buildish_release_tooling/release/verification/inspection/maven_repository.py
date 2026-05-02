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

from pathlib import Path

from apache_buildish_release_tooling.release.contracts import (
    ArtifactReproducibilityReport,
    MavenRepositoryPathResultReport,
    MavenRepositoryReproducibilityMetadata,
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
    metadata = MavenRepositoryReproducibilityMetadata.model_validate_json(
        metadata_path.read_text(encoding="utf-8")
    )
    emit_detail(progress_reporter, "Metadata", str(metadata_path))
    if metadata.repository_dir is not None:
        emit_detail(progress_reporter, "Repository dir", metadata.repository_dir)
    if metadata.effective_execution is not None:
        for output_path in metadata.effective_execution.build.output_paths:
            emit_detail(progress_reporter, "Rebuild output", output_path)
    path_results = metadata.path_results
    if not path_results:
        emit_warning(progress_reporter, "No repository path results were retained for this artifact")
        return
    verified_results = [
        path_result
        for path_result in path_results
        if path_result.verdict == "verified"
    ]
    failed_results = [
        path_result
        for path_result in path_results
        if path_result.verdict == "failed"
    ]
    skipped_results = [
        path_result
        for path_result in path_results
        if path_result.verdict == "skipped"
    ]
    emit_detail(progress_reporter, "Compared staged paths", str(len(path_results)))
    emit_detail(progress_reporter, "Verified comparable paths", str(len(verified_results)))
    emit_detail(progress_reporter, "Failed comparable paths", str(len(failed_results)))
    emit_detail(progress_reporter, "Skipped remote-only paths", str(len(skipped_results)))
    if not failed_results:
        emit_success(progress_reporter, "No failed comparable repository paths were retained")
        return
    emit_detail(progress_reporter, "Failed by mode", _failed_mode_summary(failed_results))
    emit_detail(progress_reporter, "Failed by category", _failed_category_summary(failed_results))
    emit_detail(
        progress_reporter,
        "Failed by repository directory",
        _failed_directory_summary(failed_results),
    )
    diagnosis = _failure_diagnosis(failed_results)
    if diagnosis is not None:
        emit_info(progress_reporter, diagnosis)
    emit_failure(
        progress_reporter,
        f"{len(failed_results)} comparable repository path(s) failed local comparison",
    )
    failed_by_category = _group_failed_results_by_category(failed_results)
    for category in ("metadata-text", "archive-payload", "missing-local", "other"):
        category_results = failed_by_category.get(category, [])
        if not category_results:
            continue
        emit_detail(
            progress_reporter,
            _category_summary_label(category),
            str(len(category_results)),
        )
        for path_result in category_results:
            emit_detail(
                progress_reporter,
                _category_path_label(category),
                _path_failure_summary(path_result),
            )


def _failed_mode_summary(failed_results: list[MavenRepositoryPathResultReport]) -> str:
    counts: dict[str, int] = {}
    for path_result in failed_results:
        mode = path_result.mode
        counts[mode] = counts.get(mode, 0) + 1
    return ", ".join(f"{mode}={counts[mode]}" for mode in sorted(counts))


def _failed_category_summary(failed_results: list[MavenRepositoryPathResultReport]) -> str:
    counts: dict[str, int] = {}
    for path_result in failed_results:
        category = _failure_category(path_result)
        counts[category] = counts.get(category, 0) + 1
    return ", ".join(f"{category}={counts[category]}" for category in sorted(counts))


def _failed_directory_summary(failed_results: list[MavenRepositoryPathResultReport]) -> str:
    counts: dict[str, int] = {}
    for path_result in failed_results:
        directory = str(Path(path_result.path).parent)
        counts[directory] = counts.get(directory, 0) + 1
    return ", ".join(f"{directory}={counts[directory]}" for directory in sorted(counts))


def _group_failed_results_by_category(
    failed_results: list[MavenRepositoryPathResultReport],
) -> dict[str, list[MavenRepositoryPathResultReport]]:
    grouped: dict[str, list[MavenRepositoryPathResultReport]] = {}
    for path_result in failed_results:
        category = _failure_category(path_result)
        grouped.setdefault(category, []).append(path_result)
    return grouped


def _failure_category(path_result: MavenRepositoryPathResultReport) -> str:
    path = path_result.path
    detail = path_result.detail
    if detail == "missing rebuilt path":
        return "missing-local"
    if isinstance(detail, str) and "archive member" in detail:
        return "archive-payload"
    lowered = path.lower()
    if lowered.endswith((".jar", ".war", ".zip", ".ear", ".nar")):
        return "archive-payload"
    if lowered.endswith((".pom", ".module", ".xml", ".properties", ".txt")):
        return "metadata-text"
    return "other"


def _category_summary_label(category: str) -> str:
    if category == "metadata-text":
        return "Failed metadata/text paths"
    if category == "archive-payload":
        return "Failed archive paths"
    if category == "missing-local":
        return "Missing local paths"
    return "Failed other paths"


def _category_path_label(category: str) -> str:
    if category == "metadata-text":
        return "Metadata/text path"
    if category == "archive-payload":
        return "Archive path"
    if category == "missing-local":
        return "Missing local path"
    return "Other path"


def _path_failure_summary(path_result: MavenRepositoryPathResultReport) -> str:
    staged_sha512 = path_result.staged_sha512
    rebuilt_sha512 = path_result.rebuilt_sha512
    digest_suffix = ""
    if staged_sha512 is not None and rebuilt_sha512 is not None:
        digest_suffix = f" [{staged_sha512[:12]} -> {rebuilt_sha512[:12]}]"
    return (
        f"{path_result.path} "
        f"[{path_result.mode}] "
        f"{path_result.detail}{digest_suffix}"
    )


def _failure_diagnosis(failed_results: list[MavenRepositoryPathResultReport]) -> str | None:
    metadata_text_suffixes = (".pom", ".module", ".xml", ".properties", ".txt")
    if all(
        path_result.path.endswith(metadata_text_suffixes)
        and path_result.detail == "raw bytes differ"
        and path_result.mode == "exact-bytes"
        for path_result in failed_results
    ):
        return (
            "Likely descriptor/text drift: comparable Maven metadata files changed while "
            "archive payload comparisons were left to stricter or normalized per-path policy"
        )
    if any(path_result.detail == "missing rebuilt path" for path_result in failed_results):
        return "The local rebuild did not reproduce at least one staged comparable repository path"
    if any(
        "archive members differ" in path_result.detail
        for path_result in failed_results
    ):
        return "Archive member drift is present inside one or more rebuilt repository artifacts"
    return None
