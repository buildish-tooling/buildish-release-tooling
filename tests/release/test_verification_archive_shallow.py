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

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from io import StringIO

from apache_buildish_release_tooling.release.verification.inspection.archive_shallow import (
    build_shallow_archive_analysis,
    emit_shallow_archive_analysis,
)
from apache_buildish_release_tooling.release.progress import ProgressReporter
from tests.release.archive_support import (
    write_gzip_wrapped_tar,
    write_tgz_archive,
    write_zip_archive,
)


class ShallowArchiveAnalysisTest(unittest.TestCase):
    """Keep shallow tar/zip archive classification stable."""

    def test_emit_shallow_archive_analysis_renders_saved_analysis_without_file_access(
        self,
    ) -> None:
        stream = StringIO()
        reporter = ProgressReporter(
            enabled=True,
            color_enabled=False,
            stream=stream,
            prefix="",
        )

        rendered = emit_shallow_archive_analysis(
            reporter,
            analysis=build_shallow_archive_analysis(
                staged_path=self._archive_fixture_path(
                    members=[("pkg/a.txt", b"a\n", 1714633201, 0o644)],
                ),
                rebuilt_path=self._archive_fixture_path(
                    members=[("pkg/b.txt", b"a\n", 1714633201, 0o644)],
                ),
            ),
        )

        self.assertTrue(rendered)
        transcript = stream.getvalue()
        self.assertIn("Shallow archive comparison", transcript)
        self.assertIn("Archive drift classification: entry-set-drift", transcript)
        self.assertIn("Missing archive entries", transcript)
        self.assertIn("Unexpected archive entries", transcript)

    def _archive_fixture_path(
        self,
        *,
        members: list[tuple[str, bytes, int, int]],
    ) -> Path:
        temporary_directory = TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        temp_dir = Path(temporary_directory.name)
        archive_path = temp_dir / "fixture.tgz"
        write_tgz_archive(archive_path, members=members)
        return archive_path

    def test_zip_metadata_only_drift_is_classified_separately(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            temp_dir = Path(temporary_directory)
            staged_path = temp_dir / "staged.zip"
            rebuilt_path = temp_dir / "rebuilt.zip"
            payload = b"wheel payload\n"
            write_zip_archive(
                staged_path,
                members=[
                    ("example/__init__.py", payload, (2026, 5, 2, 9, 0, 1), 0o100644)
                ],
            )
            write_zip_archive(
                rebuilt_path,
                members=[
                    ("example/__init__.py", payload, (2026, 5, 2, 9, 0, 9), 0o100755)
                ],
            )

            analysis = build_shallow_archive_analysis(
                staged_path=staged_path,
                rebuilt_path=rebuilt_path,
            )

            self.assertIsNotNone(analysis)
            if analysis is None:
                self.fail("expected archive analysis for zip metadata drift")
            self.assertEqual("entry-metadata-drift", analysis.classification)
            self.assertEqual([], analysis.missing_paths)
            self.assertEqual([], analysis.unexpected_paths)
            self.assertEqual([], analysis.content_mismatches)
            self.assertEqual(
                ["example/__init__.py: mtime, mode"],
                analysis.metadata_mismatches,
            )

    def test_tar_entry_set_drift_is_classified_separately(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            temp_dir = Path(temporary_directory)
            staged_path = temp_dir / "staged.tgz"
            rebuilt_path = temp_dir / "rebuilt.tgz"
            write_tgz_archive(
                staged_path,
                members=[
                    ("package/package.json", b"{}\n", 1714633201, 0o644),
                    ("package/README.md", b"readme\n", 1714633201, 0o644),
                ],
            )
            write_tgz_archive(
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
            self.assertEqual("entry-set-drift", analysis.classification)
            self.assertEqual(["package/README.md"], analysis.missing_paths)
            self.assertEqual([], analysis.unexpected_paths)
            self.assertEqual([], analysis.metadata_mismatches)
            self.assertEqual([], analysis.content_mismatches)

    def test_gzip_outer_container_drift_is_classified_separately(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            temp_dir = Path(temporary_directory)
            staged_path = temp_dir / "staged.tar.gz"
            rebuilt_path = temp_dir / "rebuilt.tar.gz"
            members = [
                (
                    "apache-buildish-example-1.2.3/README.txt",
                    b"hello\n",
                    1714633201,
                    0o644,
                )
            ]
            write_gzip_wrapped_tar(
                staged_path,
                members=members,
                gzip_mtime=1714633201,
            )
            write_gzip_wrapped_tar(
                rebuilt_path,
                members=members,
                gzip_mtime=1714633299,
            )

            analysis = build_shallow_archive_analysis(
                staged_path=staged_path,
                rebuilt_path=rebuilt_path,
            )

            self.assertIsNotNone(analysis)
            if analysis is None:
                self.fail("expected archive analysis for gzip outer drift")
            self.assertEqual("outer-container-drift", analysis.classification)
            self.assertFalse(analysis.raw_bytes_equal)
            self.assertEqual("tar", analysis.archive_format)
            self.assertEqual([], analysis.missing_paths)
            self.assertEqual([], analysis.unexpected_paths)
            self.assertEqual([], analysis.metadata_mismatches)
            self.assertEqual([], analysis.content_mismatches)

    def test_zip_entry_order_drift_is_reported_separately(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            temp_dir = Path(temporary_directory)
            staged_path = temp_dir / "staged.zip"
            rebuilt_path = temp_dir / "rebuilt.zip"
            first = ("example/a.txt", b"a\n", (2026, 5, 2, 9, 0, 1), 0o100644)
            second = ("example/b.txt", b"b\n", (2026, 5, 2, 9, 0, 1), 0o100644)
            write_zip_archive(staged_path, members=[first, second])
            write_zip_archive(rebuilt_path, members=[second, first])

            analysis = build_shallow_archive_analysis(
                staged_path=staged_path,
                rebuilt_path=rebuilt_path,
            )

            self.assertIsNotNone(analysis)
            if analysis is None:
                self.fail("expected archive analysis for zip entry-order drift")
            self.assertEqual("entry-order-drift", analysis.classification)
            self.assertEqual(
                ["position 1: staged=example/a.txt rebuilt=example/b.txt"],
                analysis.entry_order_mismatches,
            )
            self.assertEqual([], analysis.missing_paths)
            self.assertEqual([], analysis.unexpected_paths)
            self.assertEqual([], analysis.metadata_mismatches)
            self.assertEqual([], analysis.content_mismatches)
