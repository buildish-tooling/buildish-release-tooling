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

"""Pure shallow top-level archive analysis helpers for inspect-repro."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tarfile
from typing import Literal
import zipfile

from apache_buildish_release_tooling.release.contracts import ShallowArchiveAnalysisReport
from apache_buildish_release_tooling.shared.archive import read_tar_entries, read_zip_entries

_ArchiveFormat = Literal["tar", "zip"]
_HASH_CHUNK_BYTES = 1024 * 1024


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
    entry_order: list[str]


@dataclass(frozen=True)
class ShallowArchiveComparison:
    classification: str
    missing_paths: list[str]
    unexpected_paths: list[str]
    entry_order_mismatches: list[str]
    metadata_mismatches: list[str]
    content_mismatches: list[str]


def build_shallow_archive_analysis(
    *,
    staged_path: Path,
    rebuilt_path: Path,
) -> ShallowArchiveAnalysisReport | None:
    """Return one durable shallow archive-analysis payload for a retained artifact pair."""

    staged_description = _describe_archive_path(staged_path)
    rebuilt_description = _describe_archive_path(rebuilt_path)
    if staged_description is None and rebuilt_description is None:
        return None
    staged_format = staged_description.archive_format if staged_description is not None else "non-archive"
    rebuilt_format = rebuilt_description.archive_format if rebuilt_description is not None else "non-archive"
    raw_bytes_equal = _file_bytes_equal(staged_path, rebuilt_path)
    staged_entry_count = len(staged_description.entries) if staged_description is not None else None
    rebuilt_entry_count = len(rebuilt_description.entries) if rebuilt_description is not None else None
    if staged_description is None or rebuilt_description is None:
        return ShallowArchiveAnalysisReport(
            classification="archive-vs-non-archive",
            raw_bytes_equal=raw_bytes_equal,
            staged_archive_format=staged_format,
            rebuilt_archive_format=rebuilt_format,
            staged_entry_count=staged_entry_count,
            rebuilt_entry_count=rebuilt_entry_count,
        )
    if staged_description.archive_format != rebuilt_description.archive_format:
        return ShallowArchiveAnalysisReport(
            classification="archive-format-mismatch",
            raw_bytes_equal=raw_bytes_equal,
            staged_archive_format=staged_format,
            rebuilt_archive_format=rebuilt_format,
            staged_entry_count=staged_entry_count,
            rebuilt_entry_count=rebuilt_entry_count,
        )
    comparison = _compare_archives(staged_description, rebuilt_description)
    if comparison is None:
        return ShallowArchiveAnalysisReport(
            classification=("entries-match" if raw_bytes_equal else "outer-container-drift"),
            archive_format=staged_description.archive_format,
            raw_bytes_equal=raw_bytes_equal,
            staged_archive_format=staged_format,
            rebuilt_archive_format=rebuilt_format,
            staged_entry_count=staged_entry_count,
            rebuilt_entry_count=rebuilt_entry_count,
        )
    return ShallowArchiveAnalysisReport(
        classification=comparison.classification,
        archive_format=staged_description.archive_format,
        raw_bytes_equal=raw_bytes_equal,
        staged_archive_format=staged_format,
        rebuilt_archive_format=rebuilt_format,
        staged_entry_count=staged_entry_count,
        rebuilt_entry_count=rebuilt_entry_count,
        missing_paths=comparison.missing_paths,
        unexpected_paths=comparison.unexpected_paths,
        entry_order_mismatches=comparison.entry_order_mismatches,
        metadata_mismatches=comparison.metadata_mismatches,
        content_mismatches=comparison.content_mismatches,
    )


def _compare_archives(
    staged: ShallowArchiveDescription,
    rebuilt: ShallowArchiveDescription,
) -> ShallowArchiveComparison | None:
    staged_paths = set(staged.entries)
    rebuilt_paths = set(rebuilt.entries)
    missing_paths = sorted(staged_paths - rebuilt_paths)
    unexpected_paths = sorted(rebuilt_paths - staged_paths)
    entry_order_mismatches: list[str] = []
    metadata_mismatches: list[str] = []
    content_mismatches: list[str] = []
    if not missing_paths and not unexpected_paths and staged.entry_order != rebuilt.entry_order:
        entry_order_mismatches.append(
            _entry_order_mismatch_detail(staged.entry_order, rebuilt.entry_order)
        )
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
    if (
        not missing_paths
        and not unexpected_paths
        and not entry_order_mismatches
        and not metadata_mismatches
        and not content_mismatches
    ):
        return None
    classification = _classify_archive_drift(
        missing_paths=missing_paths,
        unexpected_paths=unexpected_paths,
        entry_order_mismatches=entry_order_mismatches,
        metadata_mismatches=metadata_mismatches,
        content_mismatches=content_mismatches,
    )
    return ShallowArchiveComparison(
        classification=classification,
        missing_paths=missing_paths,
        unexpected_paths=unexpected_paths,
        entry_order_mismatches=entry_order_mismatches,
        metadata_mismatches=metadata_mismatches,
        content_mismatches=content_mismatches,
    )


def _classify_archive_drift(
    *,
    missing_paths: list[str],
    unexpected_paths: list[str],
    entry_order_mismatches: list[str],
    metadata_mismatches: list[str],
    content_mismatches: list[str],
) -> str:
    categories = sum(
        1
        for present in (
            bool(missing_paths or unexpected_paths),
            bool(entry_order_mismatches),
            bool(metadata_mismatches),
            bool(content_mismatches),
        )
        if present
    )
    if categories > 1:
        return "mixed-entry-drift"
    if missing_paths or unexpected_paths:
        return "entry-set-drift"
    if entry_order_mismatches:
        return "entry-order-drift"
    if metadata_mismatches:
        return "entry-metadata-drift"
    return "entry-content-drift"


def _describe_archive_path(path: Path) -> ShallowArchiveDescription | None:
    tar_description = _describe_tar_archive(path)
    if tar_description is not None:
        return tar_description
    return _describe_zip_archive(path)


def _describe_tar_archive(path: Path) -> ShallowArchiveDescription | None:
    try:
        bounded_entries = read_tar_entries(path)
    except tarfile.TarError:
        return None
    entries: dict[str, ArchiveEntry] = {}
    entry_order: list[str] = []
    for entry in bounded_entries:
        if entry.name in entries:
            raise ValueError(f"archive member is duplicated: {entry.name}")
        entry_order.append(entry.name)
        entries[entry.name] = ArchiveEntry(
            path=entry.name,
            entry_type=entry.entry_type,
            size_bytes=entry.size_bytes,
            mtime=str(entry.mtime) if entry.mtime is not None else None,
            mode=f"{entry.mode:o}",
            owner_uid=entry.owner_uid,
            owner_gid=entry.owner_gid,
            owner_user=entry.owner_user,
            owner_group=entry.owner_group,
            symlink_target=entry.link_target,
            content_sha512=entry.content_sha512,
        )
    return ShallowArchiveDescription(archive_format="tar", entries=entries, entry_order=entry_order)


def _describe_zip_archive(path: Path) -> ShallowArchiveDescription | None:
    try:
        bounded_entries = read_zip_entries(path)
    except zipfile.BadZipFile:
        return None
    entries: dict[str, ArchiveEntry] = {}
    entry_order: list[str] = []
    for entry in bounded_entries:
        if entry.name in entries:
            raise ValueError(f"archive member is duplicated: {entry.name}")
        entry_order.append(entry.name)
        unix_mode = (entry.external_attr >> 16) & 0o7777
        entries[entry.name] = ArchiveEntry(
            path=entry.name,
            entry_type=entry.entry_type,
            size_bytes=entry.size_bytes,
            mtime=_zip_mtime(entry.date_time),
            mode=(f"{unix_mode:o}" if unix_mode else None),
            owner_uid=None,
            owner_gid=None,
            owner_user=None,
            owner_group=None,
            symlink_target=None,
            content_sha512=entry.content_sha512,
        )
    return ShallowArchiveDescription(archive_format="zip", entries=entries, entry_order=entry_order)


def _file_bytes_equal(left: Path, right: Path) -> bool:
    if left.stat().st_size != right.stat().st_size:
        return False
    with left.open("rb") as left_file, right.open("rb") as right_file:
        while True:
            left_chunk = left_file.read(_HASH_CHUNK_BYTES)
            right_chunk = right_file.read(_HASH_CHUNK_BYTES)
            if left_chunk != right_chunk:
                return False
            if not left_chunk:
                return True


def _entry_order_mismatch_detail(staged_order: list[str], rebuilt_order: list[str]) -> str:
    for index, (staged_path, rebuilt_path) in enumerate(
        zip(staged_order, rebuilt_order, strict=True),
        start=1,
    ):
        if staged_path != rebuilt_path:
            return f"position {index}: staged={staged_path} rebuilt={rebuilt_path}"
    return "entry ordering differs"


def _zip_mtime(date_time: tuple[int, int, int, int, int, int]) -> str | None:
    year, month, day, hour, minute, second = date_time
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}"
