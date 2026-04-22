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

"""Shallow top-level archive transcript helpers for inspect-repro."""

from __future__ import annotations

from pathlib import Path

from buildish_release_tooling.release.contracts import ShallowArchiveAnalysisReport
from buildish_release_tooling.release.progress import ProgressReporter
from buildish_release_tooling.release.verification.common import (
    emit_detail,
    emit_failure,
    emit_info,
    emit_success,
    emit_warning,
)
from buildish_release_tooling.release.verification.inspection.archive_shallow_analysis import (
    build_shallow_archive_analysis,
)

_MAX_REPORTED_ENTRY_MISMATCHES = 12


def inspect_shallow_archive_pair(
    progress_reporter: ProgressReporter,
    *,
    staged_path: Path,
    rebuilt_path: Path,
) -> bool:
    """Inspect one retained staged/rebuilt archive pair shallowly.

    Returns ``True`` when at least one side looked like a supported top-level tar/zip archive and
    the caller should consider the emitted archive diagnostics part of the inspection output.
    """

    analysis = build_shallow_archive_analysis(
        staged_path=staged_path,
        rebuilt_path=rebuilt_path,
    )
    return emit_shallow_archive_analysis(
        progress_reporter,
        analysis=analysis,
    )


def emit_shallow_archive_analysis(
    progress_reporter: ProgressReporter,
    *,
    analysis: ShallowArchiveAnalysisReport | None,
) -> bool:
    """Emit one shallow archive analysis already retained in an inspection bundle."""

    if analysis is None:
        return False
    emit_info(progress_reporter, "Shallow archive comparison")
    staged_format = str(analysis.staged_archive_format)
    rebuilt_format = str(analysis.rebuilt_archive_format)
    if analysis.classification == "archive-vs-non-archive":
        emit_failure(
            progress_reporter,
            "One retained artifact is a readable top-level archive and the other is not",
        )
        emit_detail(progress_reporter, "Staged archive format", staged_format)
        emit_detail(progress_reporter, "Rebuilt archive format", rebuilt_format)
        return True
    emit_detail(
        progress_reporter,
        "Archive format",
        str(analysis.archive_format or staged_format),
    )
    emit_detail(
        progress_reporter,
        "Staged entry count",
        str(analysis.staged_entry_count) if analysis.staged_entry_count is not None else "n/a",
    )
    emit_detail(
        progress_reporter,
        "Rebuilt entry count",
        str(analysis.rebuilt_entry_count) if analysis.rebuilt_entry_count is not None else "n/a",
    )
    if analysis.classification == "archive-format-mismatch":
        emit_failure(
            progress_reporter,
            "Retained staged and rebuilt artifacts use different top-level archive formats",
        )
        emit_detail(progress_reporter, "Staged archive format", staged_format)
        emit_detail(progress_reporter, "Rebuilt archive format", rebuilt_format)
        return True
    if analysis.classification == "entries-match":
        emit_success(
            progress_reporter,
            "Top-level archive entries and member payloads match after shallow inspection",
        )
        return True
    if analysis.classification == "outer-container-drift":
        emit_success(
            progress_reporter,
            "Top-level archive entries and member payloads match after shallow inspection",
        )
        emit_warning(
            progress_reporter,
            "Archive drift appears limited to the outer container or compression bytes",
        )
        emit_detail(progress_reporter, "Archive drift classification", "outer-container-drift")
        _emit_archive_hint(progress_reporter, classification="outer-container-drift")
        return True
    emit_failure(progress_reporter, "Top-level archive entries differ after shallow inspection")
    classification = analysis.classification
    emit_detail(progress_reporter, "Archive drift classification", classification)
    _emit_path_list(
        progress_reporter,
        heading="Missing archive entries",
        entries=[str(path) for path in analysis.missing_paths],
    )
    _emit_path_list(
        progress_reporter,
        heading="Unexpected archive entries",
        entries=[str(path) for path in analysis.unexpected_paths],
    )
    _emit_mismatch_list(
        progress_reporter,
        heading="Archive entry-order mismatches",
        mismatches=[str(detail) for detail in analysis.entry_order_mismatches],
    )
    _emit_mismatch_list(
        progress_reporter,
        heading="Archive metadata mismatches",
        mismatches=[str(detail) for detail in analysis.metadata_mismatches],
    )
    _emit_path_list(
        progress_reporter,
        heading="Archive member-content mismatches",
        entries=[str(path) for path in analysis.content_mismatches],
    )
    _emit_archive_hint(progress_reporter, classification=classification)
    return True


def _emit_path_list(
    progress_reporter: ProgressReporter,
    *,
    heading: str,
    entries: list[str],
) -> None:
    if not entries:
        return
    emit_info(progress_reporter, heading)
    for path in entries[:_MAX_REPORTED_ENTRY_MISMATCHES]:
        progress_reporter.emit(f"    {path}")
    if len(entries) > _MAX_REPORTED_ENTRY_MISMATCHES:
        progress_reporter.emit(
            f"    ... {len(entries) - _MAX_REPORTED_ENTRY_MISMATCHES} additional entries omitted"
        )


def _emit_mismatch_list(
    progress_reporter: ProgressReporter,
    *,
    heading: str,
    mismatches: list[str],
) -> None:
    if not mismatches:
        return
    emit_info(progress_reporter, heading)
    for detail in mismatches[:_MAX_REPORTED_ENTRY_MISMATCHES]:
        progress_reporter.emit(f"    {detail}")
    if len(mismatches) > _MAX_REPORTED_ENTRY_MISMATCHES:
        progress_reporter.emit(
            f"    ... {len(mismatches) - _MAX_REPORTED_ENTRY_MISMATCHES} additional mismatches omitted"
        )


def _emit_archive_hint(progress_reporter: ProgressReporter, *, classification: str) -> None:
    hint = _archive_hint(classification)
    if hint is None:
        return
    emit_info(progress_reporter, hint)


def _archive_hint(classification: str) -> str | None:
    if classification == "outer-container-drift":
        return "Likely cause: compression or outer-container bytes changed while extracted members stayed stable"
    if classification == "entry-set-drift":
        return "Likely cause: top-level archive members were added, omitted, or renamed"
    if classification == "entry-order-drift":
        return "Likely cause: the same top-level members were emitted in a different archive order"
    if classification == "entry-metadata-drift":
        return "Likely cause: timestamps, permissions, ownership fields, or symlink metadata changed"
    if classification == "entry-content-drift":
        return "Likely cause: one or more top-level archive member payloads changed"
    if classification == "mixed-entry-drift":
        return "Likely cause: more than one top-level archive drift category is present"
    return None
