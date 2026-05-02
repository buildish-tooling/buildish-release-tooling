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

"""Unit tests for shallow archive reproducibility inspection helpers."""

from __future__ import annotations

import io
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
import unittest
import zipfile

from apache_buildish_release_tooling.release.verification.inspection.archive_shallow import (
    build_shallow_archive_analysis,
)


def _write_zip_archive(
    archive_path: Path,
    *,
    members: list[tuple[str, bytes, tuple[int, int, int, int, int, int], int]],
) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for member_name, payload, timestamp, mode in members:
            info = zipfile.ZipInfo(member_name, date_time=timestamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = mode << 16
            archive.writestr(info, payload)


def _write_tgz_archive(
    archive_path: Path,
    *,
    members: list[tuple[str, bytes, int, int]],
) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, mode="w:gz") as archive:
        for member_name, payload, mtime, mode in members:
            info = tarfile.TarInfo(member_name)
            info.size = len(payload)
            info.mtime = mtime
            info.mode = mode
            archive.addfile(info, io.BytesIO(payload))


class ShallowArchiveAnalysisTest(unittest.TestCase):
    """Keep shallow tar/zip archive classification stable."""

    def test_zip_metadata_only_drift_is_classified_separately(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            temp_dir = Path(temporary_directory)
            staged_path = temp_dir / "staged.zip"
            rebuilt_path = temp_dir / "rebuilt.zip"
            payload = b"wheel payload\n"
            _write_zip_archive(
                staged_path,
                members=[("example/__init__.py", payload, (2026, 5, 2, 9, 0, 1), 0o100644)],
            )
            _write_zip_archive(
                rebuilt_path,
                members=[("example/__init__.py", payload, (2026, 5, 2, 9, 0, 9), 0o100755)],
            )

            analysis = build_shallow_archive_analysis(
                staged_path=staged_path,
                rebuilt_path=rebuilt_path,
            )

            self.assertIsNotNone(analysis)
            if analysis is None:
                self.fail("expected archive analysis for zip metadata drift")
            self.assertEqual("entry-metadata-drift", analysis["classification"])
            self.assertEqual([], analysis["missing_paths"])
            self.assertEqual([], analysis["unexpected_paths"])
            self.assertEqual([], analysis["content_mismatches"])
            self.assertEqual(
                ["example/__init__.py: mtime, mode"],
                analysis["metadata_mismatches"],
            )

    def test_tar_entry_set_drift_is_classified_separately(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            temp_dir = Path(temporary_directory)
            staged_path = temp_dir / "staged.tgz"
            rebuilt_path = temp_dir / "rebuilt.tgz"
            _write_tgz_archive(
                staged_path,
                members=[
                    ("package/package.json", b"{}\n", 1714633201, 0o644),
                    ("package/README.md", b"readme\n", 1714633201, 0o644),
                ],
            )
            _write_tgz_archive(
                rebuilt_path,
                members=[("package/package.json", b"{}\n", 1714633201, 0o644)],
            )

            analysis = build_shallow_archive_analysis(
                staged_path=staged_path,
                rebuilt_path=rebuilt_path,
            )

            self.assertIsNotNone(analysis)
            if analysis is None:
                self.fail("expected archive analysis for tar entry-set drift")
            self.assertEqual("entry-set-drift", analysis["classification"])
            self.assertEqual(["package/README.md"], analysis["missing_paths"])
            self.assertEqual([], analysis["unexpected_paths"])
            self.assertEqual([], analysis["metadata_mismatches"])
            self.assertEqual([], analysis["content_mismatches"])
