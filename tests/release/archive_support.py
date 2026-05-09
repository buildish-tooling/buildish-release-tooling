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
"""Shared archive fixture writers for verification tests."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
import gzip
import io
import tarfile
import zipfile

ZipArchiveMember = tuple[str, bytes, tuple[int, int, int, int, int, int], int]
TarArchiveMember = tuple[str, bytes, int, int]


def write_zip_archive(
    archive_path: Path,
    *,
    members: Sequence[ZipArchiveMember],
) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        archive_path, mode="w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for member_name, payload, timestamp, mode in members:
            info = zipfile.ZipInfo(member_name, date_time=timestamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = mode << 16
            archive.writestr(info, payload)


def write_tgz_archive(
    archive_path: Path,
    *,
    members: Sequence[TarArchiveMember],
) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, mode="w:gz") as archive:
        for member_name, payload, mtime, mode in members:
            info = tarfile.TarInfo(member_name)
            info.size = len(payload)
            info.mtime = mtime
            info.mode = mode
            archive.addfile(info, io.BytesIO(payload))


def write_gzip_wrapped_tar(
    archive_path: Path,
    *,
    members: Sequence[TarArchiveMember],
    gzip_mtime: int,
) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as archive:
        for member_name, payload, mtime, mode in members:
            info = tarfile.TarInfo(member_name)
            info.size = len(payload)
            info.mtime = mtime
            info.mode = mode
            archive.addfile(info, io.BytesIO(payload))
    archive_path.write_bytes(
        gzip.compress(
            tar_buffer.getvalue(),
            compresslevel=9,
            mtime=gzip_mtime,
        )
    )
