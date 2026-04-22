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

"""Shared bounded archive readers for tar and zip files."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import tarfile
from typing import IO
import zipfile

from buildish_release_tooling.shared.io import hash_stream_bounded

DEFAULT_MAX_ARCHIVE_ENTRIES = 250_000
DEFAULT_MAX_ARCHIVE_MEMBER_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_MAX_ARCHIVE_TOTAL_MEMBER_BYTES = 8 * 1024 * 1024 * 1024


class ArchiveLimitExceededError(ValueError):
    """Raised when an archive exceeds the configured inspection budget."""


@dataclass(frozen=True, slots=True)
class ArchiveLimits:
    """Resource budget for bounded archive inspection."""

    max_entries: int = DEFAULT_MAX_ARCHIVE_ENTRIES
    max_member_bytes: int = DEFAULT_MAX_ARCHIVE_MEMBER_BYTES
    max_total_member_bytes: int = DEFAULT_MAX_ARCHIVE_TOTAL_MEMBER_BYTES

    def __post_init__(self) -> None:
        if self.max_entries < 0:
            raise ValueError("max_entries must be non-negative")
        if self.max_member_bytes < 0:
            raise ValueError("max_member_bytes must be non-negative")
        if self.max_total_member_bytes < 0:
            raise ValueError("max_total_member_bytes must be non-negative")


DEFAULT_ARCHIVE_LIMITS = ArchiveLimits()


@dataclass(frozen=True, slots=True)
class BoundedTarEntry:
    """One tar member after bounded inspection."""

    name: str
    entry_type: str
    size_bytes: int
    mtime: int | None
    mode: int
    owner_uid: int
    owner_gid: int
    owner_user: str | None
    owner_group: str | None
    link_target: str | None
    content_sha512: str | None


@dataclass(frozen=True, slots=True)
class BoundedZipEntry:
    """One zip member after bounded inspection."""

    name: str
    is_dir: bool
    entry_type: str
    size_bytes: int
    date_time: tuple[int, int, int, int, int, int]
    external_attr: int
    content_sha512: str | None


class ArchiveReadBudget:
    """Mutable per-archive budget tracker."""

    def __init__(self, limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS) -> None:
        self.limits = limits
        self.entry_count = 0
        self.total_member_bytes = 0

    def record_member(self, name: str, *, size_bytes: int) -> None:
        """Record one member and fail if the archive budget is exceeded."""

        if size_bytes < 0:
            raise ArchiveLimitExceededError(f"archive member has negative size: {name}")
        self.entry_count += 1
        if self.entry_count > self.limits.max_entries:
            raise ArchiveLimitExceededError(
                f"archive contains more than {self.limits.max_entries} entries"
            )
        if size_bytes > self.limits.max_member_bytes:
            raise ArchiveLimitExceededError(
                f"archive member exceeds {self.limits.max_member_bytes} bytes: {name}"
            )
        self.total_member_bytes += size_bytes
        if self.total_member_bytes > self.limits.max_total_member_bytes:
            raise ArchiveLimitExceededError(
                f"archive members exceed {self.limits.max_total_member_bytes} total bytes"
            )

    def hash_member_stream(self, name: str, stream: IO[bytes], *, declared_size: int) -> str:
        """Hash one member stream while enforcing the declared per-member size."""

        try:
            return hash_stream_bounded(
                stream,
                max_bytes=declared_size,
                algorithm="sha512",
            )
        except ValueError as exc:
            raise ArchiveLimitExceededError(f"archive member exceeded declared size: {name}") from exc


def read_tar_entries(
    path: Path,
    *,
    limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS,
) -> list[BoundedTarEntry]:
    """Read tar member metadata and content hashes under a resource budget."""

    budget = ArchiveReadBudget(limits)
    entries: list[BoundedTarEntry] = []
    with tarfile.open(path, mode="r:*") as archive:
        for member in archive:
            budget.record_member(member.name, size_bytes=member.size if member.isfile() else 0)
            content_sha512: str | None = None
            if member.isfile():
                member_file = archive.extractfile(member)
                content_sha512 = (
                    budget.hash_member_stream(
                        member.name,
                        member_file,
                        declared_size=member.size,
                    )
                    if member_file is not None
                    else _empty_sha512()
                )
            entries.append(
                BoundedTarEntry(
                    name=member.name,
                    entry_type=_tar_entry_type(member),
                    size_bytes=member.size,
                    mtime=int(member.mtime) if member.mtime is not None else None,
                    mode=member.mode,
                    owner_uid=member.uid,
                    owner_gid=member.gid,
                    owner_user=member.uname or None,
                    owner_group=member.gname or None,
                    link_target=member.linkname or None,
                    content_sha512=content_sha512,
                )
            )
    return entries


def read_zip_entries(
    path: Path,
    *,
    limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS,
) -> list[BoundedZipEntry]:
    """Read zip member metadata and content hashes under a resource budget."""

    budget = ArchiveReadBudget(limits)
    entries: list[BoundedZipEntry] = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            budget.record_member(info.filename, size_bytes=0 if info.is_dir() else info.file_size)
            content_sha512: str | None = None
            if not info.is_dir():
                with archive.open(info) as member_file:
                    content_sha512 = budget.hash_member_stream(
                        info.filename,
                        member_file,
                        declared_size=info.file_size,
                    )
            entries.append(
                BoundedZipEntry(
                    name=info.filename,
                    is_dir=info.is_dir(),
                    entry_type=_zip_entry_type(info),
                    size_bytes=info.file_size,
                    date_time=info.date_time,
                    external_attr=info.external_attr,
                    content_sha512=content_sha512,
                )
            )
    return entries


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
    unix_type = (info.external_attr >> 16) & 0o170000
    if info.is_dir():
        return "directory"
    if unix_type == 0o120000:
        return "symlink"
    return "file"


def _empty_sha512() -> str:
    return hashlib.sha512(b"").hexdigest()
