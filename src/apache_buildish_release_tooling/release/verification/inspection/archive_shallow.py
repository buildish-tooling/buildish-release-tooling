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

"""Shallow top-level archive inspection helpers for inspect-repro."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO
from pathlib import Path
import stat
import tarfile
from typing import Any, Literal
import zipfile

from apache_buildish_release_tooling.release.progress import ProgressReporter
from apache_buildish_release_tooling.release.verification.common import (
    emit_detail,
    emit_failure,
    emit_info,
    emit_success,
    emit_warning,
)

_MAX_REPORTED_ENTRY_MISMATCHES = 12
_ArchiveFormat = Literal["tar", "zip"]


@dataclass(frozen=True)
class ArchiveEntry:
    path: str
    entry_type: str
    size_bytes: int
    mtime: str | None
    mode: str | None
    owner_uid: int | None
    owner_gid: int | None
    owner_user: str | None
    owner_group: str | None
    symlink_target: str | None
    content_sha512: str | None


@dataclass(frozen=True)
class ShallowArchiveDescription:
    archive_format: _ArchiveFormat
    entries: dict[str, ArchiveEntry]


@dataclass(frozen=True)
class ShallowArchiveComparison:
    classification: str
    missing_paths: list[str]
    unexpected_paths: list[str]
    metadata_mismatches: list[str]
    content_mismatches: list[str]


def build_shallow_archive_analysis(
    *,
    staged_path: Path,
    rebuilt_path: Path,
) -> dict[str, Any] | None:
    """Return one durable shallow archive-analysis payload for a retained artifact pair."""

    staged_bytes = staged_path.read_bytes()
    rebuilt_bytes = rebuilt_path.read_bytes()
    staged_description = _describe_archive_payload(staged_bytes)
    rebuilt_description = _describe_archive_payload(rebuilt_bytes)
    if staged_description is None and rebuilt_description is None:
        return None
    staged_format = staged_description.archive_format if staged_description is not None else "non-archive"
    rebuilt_format = rebuilt_description.archive_format if rebuilt_description is not None else "non-archive"
    payload: dict[str, Any] = {
        "raw_bytes_equal": staged_bytes == rebuilt_bytes,
        "staged_archive_format": staged_format,
        "rebuilt_archive_format": rebuilt_format,
        "staged_entry_count": (len(staged_description.entries) if staged_description is not None else None),
        "rebuilt_entry_count": (len(rebuilt_description.entries) if rebuilt_description is not None else None),
        "missing_paths": [],
        "unexpected_paths": [],
        "metadata_mismatches": [],
        "content_mismatches": [],
    }
    if staged_description is None or rebuilt_description is None:
        payload["classification"] = "archive-vs-non-archive"
        return payload
    if staged_description.archive_format != rebuilt_description.archive_format:
        payload["classification"] = "archive-format-mismatch"
        return payload
    comparison = _compare_archives(staged_description, rebuilt_description)
    payload["archive_format"] = staged_description.archive_format
    if comparison is None:
        payload["classification"] = (
            "entries-match"
            if staged_bytes == rebuilt_bytes
            else "outer-container-drift"
        )
        return payload
    payload["classification"] = comparison.classification
    payload["missing_paths"] = comparison.missing_paths
    payload["unexpected_paths"] = comparison.unexpected_paths
    payload["metadata_mismatches"] = comparison.metadata_mismatches
    payload["content_mismatches"] = comparison.content_mismatches
    return payload


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
    if analysis is None:
        return False
    emit_info(progress_reporter, "Shallow archive comparison")
    staged_format = str(analysis["staged_archive_format"])
    rebuilt_format = str(analysis["rebuilt_archive_format"])
    if analysis["classification"] == "archive-vs-non-archive":
        emit_failure(
            progress_reporter,
            "One retained artifact is a readable top-level archive and the other is not",
        )
        emit_detail(progress_reporter, "Staged archive format", staged_format)
        emit_detail(progress_reporter, "Rebuilt archive format", rebuilt_format)
        return True
    emit_detail(progress_reporter, "Archive format", str(analysis.get("archive_format", staged_format)))
    emit_detail(progress_reporter, "Staged entry count", str(analysis.get("staged_entry_count", "n/a")))
    emit_detail(progress_reporter, "Rebuilt entry count", str(analysis.get("rebuilt_entry_count", "n/a")))
    if analysis["classification"] == "archive-format-mismatch":
        emit_failure(
            progress_reporter,
            "Retained staged and rebuilt artifacts use different top-level archive formats",
        )
        emit_detail(progress_reporter, "Staged archive format", staged_format)
        emit_detail(progress_reporter, "Rebuilt archive format", rebuilt_format)
        return True
    if analysis["classification"] == "entries-match":
        emit_success(
            progress_reporter,
            "Top-level archive entries and member payloads match after shallow inspection",
        )
        return True
    if analysis["classification"] == "outer-container-drift":
        emit_success(
            progress_reporter,
            "Top-level archive entries and member payloads match after shallow inspection",
        )
        emit_warning(
            progress_reporter,
            "Archive drift appears limited to the outer container or compression bytes",
        )
        emit_detail(progress_reporter, "Archive drift classification", "outer-container-drift")
        return True
    emit_failure(progress_reporter, "Top-level archive entries differ after shallow inspection")
    emit_detail(progress_reporter, "Archive drift classification", str(analysis["classification"]))
    _emit_path_list(
        progress_reporter,
        heading="Missing archive entries",
        entries=[str(path) for path in analysis["missing_paths"]],
    )
    _emit_path_list(
        progress_reporter,
        heading="Unexpected archive entries",
        entries=[str(path) for path in analysis["unexpected_paths"]],
    )
    _emit_mismatch_list(
        progress_reporter,
        heading="Archive metadata mismatches",
        mismatches=[str(detail) for detail in analysis["metadata_mismatches"]],
    )
    _emit_path_list(
        progress_reporter,
        heading="Archive member-content mismatches",
        entries=[str(path) for path in analysis["content_mismatches"]],
    )
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


def _compare_archives(
    staged: ShallowArchiveDescription,
    rebuilt: ShallowArchiveDescription,
) -> ShallowArchiveComparison | None:
    staged_paths = set(staged.entries)
    rebuilt_paths = set(rebuilt.entries)
    missing_paths = sorted(staged_paths - rebuilt_paths)
    unexpected_paths = sorted(rebuilt_paths - staged_paths)
    metadata_mismatches: list[str] = []
    content_mismatches: list[str] = []
    for path in sorted(staged_paths & rebuilt_paths):
        staged_entry = staged.entries[path]
        rebuilt_entry = rebuilt.entries[path]
        mismatched_fields = [
            field_name
            for field_name, staged_value, rebuilt_value in (
                ("type", staged_entry.entry_type, rebuilt_entry.entry_type),
                ("size", staged_entry.size_bytes, rebuilt_entry.size_bytes),
                ("mtime", staged_entry.mtime, rebuilt_entry.mtime),
                ("mode", staged_entry.mode, rebuilt_entry.mode),
                ("owner_uid", staged_entry.owner_uid, rebuilt_entry.owner_uid),
                ("owner_gid", staged_entry.owner_gid, rebuilt_entry.owner_gid),
                ("owner_user", staged_entry.owner_user, rebuilt_entry.owner_user),
                ("owner_group", staged_entry.owner_group, rebuilt_entry.owner_group),
                ("symlink_target", staged_entry.symlink_target, rebuilt_entry.symlink_target),
            )
            if staged_value != rebuilt_value
        ]
        if mismatched_fields:
            metadata_mismatches.append(f"{path}: {', '.join(mismatched_fields)}")
        if staged_entry.content_sha512 != rebuilt_entry.content_sha512:
            content_mismatches.append(path)
    if not missing_paths and not unexpected_paths and not metadata_mismatches and not content_mismatches:
        return None
    classification = _classify_archive_drift(
        missing_paths=missing_paths,
        unexpected_paths=unexpected_paths,
        metadata_mismatches=metadata_mismatches,
        content_mismatches=content_mismatches,
    )
    return ShallowArchiveComparison(
        classification=classification,
        missing_paths=missing_paths,
        unexpected_paths=unexpected_paths,
        metadata_mismatches=metadata_mismatches,
        content_mismatches=content_mismatches,
    )


def _classify_archive_drift(
    *,
    missing_paths: list[str],
    unexpected_paths: list[str],
    metadata_mismatches: list[str],
    content_mismatches: list[str],
) -> str:
    categories = sum(
        1
        for present in (
            bool(missing_paths or unexpected_paths),
            bool(metadata_mismatches),
            bool(content_mismatches),
        )
        if present
    )
    if categories > 1:
        return "mixed-entry-drift"
    if missing_paths or unexpected_paths:
        return "entry-set-drift"
    if metadata_mismatches:
        return "entry-metadata-drift"
    return "entry-content-drift"


def _describe_archive(path: Path) -> ShallowArchiveDescription | None:
    return _describe_archive_payload(path.read_bytes())


def _describe_archive_payload(payload: bytes) -> ShallowArchiveDescription | None:
    tar_description = _describe_tar_archive(payload)
    if tar_description is not None:
        return tar_description
    return _describe_zip_archive(payload)


def _describe_tar_archive(payload: bytes) -> ShallowArchiveDescription | None:
    try:
        with tarfile.open(fileobj=BytesIO(payload), mode="r:*") as archive:
            entries: dict[str, ArchiveEntry] = {}
            for member in archive.getmembers():
                if member.name in entries:
                    raise ValueError(f"archive member is duplicated: {member.name}")
                content_sha512: str | None = None
                if member.isfile():
                    member_file = archive.extractfile(member)
                    content_sha512 = (
                        hashlib.sha512(member_file.read()).hexdigest()
                        if member_file is not None
                        else hashlib.sha512(b"").hexdigest()
                    )
                entries[member.name] = ArchiveEntry(
                    path=member.name,
                    entry_type=_tar_entry_type(member),
                    size_bytes=member.size,
                    mtime=str(int(member.mtime)) if member.mtime is not None else None,
                    mode=f"{member.mode:o}",
                    owner_uid=member.uid,
                    owner_gid=member.gid,
                    owner_user=member.uname or None,
                    owner_group=member.gname or None,
                    symlink_target=member.linkname or None,
                    content_sha512=content_sha512,
                )
    except tarfile.TarError:
        return None
    return ShallowArchiveDescription(archive_format="tar", entries=entries)


def _describe_zip_archive(payload: bytes) -> ShallowArchiveDescription | None:
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            entries: dict[str, ArchiveEntry] = {}
            for info in archive.infolist():
                if info.filename in entries:
                    raise ValueError(f"archive member is duplicated: {info.filename}")
                content_sha512: str | None = None
                if not info.is_dir():
                    content_sha512 = hashlib.sha512(archive.read(info)).hexdigest()
                unix_mode = (info.external_attr >> 16) & 0o7777
                entry_type = _zip_entry_type(info)
                entries[info.filename] = ArchiveEntry(
                    path=info.filename,
                    entry_type=entry_type,
                    size_bytes=info.file_size,
                    mtime=_zip_mtime(info),
                    mode=(f"{unix_mode:o}" if unix_mode else None),
                    owner_uid=None,
                    owner_gid=None,
                    owner_user=None,
                    owner_group=None,
                    symlink_target=None,
                    content_sha512=content_sha512,
                )
    except zipfile.BadZipFile:
        return None
    return ShallowArchiveDescription(archive_format="zip", entries=entries)


def _tar_entry_type(member: tarfile.TarInfo) -> str:
    if member.isdir():
        return "directory"
    if member.issym():
        return "symlink"
    if member.islnk():
        return "hardlink"
    if member.isfile():
        return "file"
    return "other"


def _zip_entry_type(info: zipfile.ZipInfo) -> str:
    if info.is_dir():
        return "directory"
    unix_mode = (info.external_attr >> 16) & 0o170000
    if unix_mode == stat.S_IFLNK:
        return "symlink"
    return "file"


def _zip_mtime(info: zipfile.ZipInfo) -> str | None:
    year, month, day, hour, minute, second = info.date_time
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}"
