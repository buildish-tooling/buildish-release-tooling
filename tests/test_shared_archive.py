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

"""Tests for shared bounded archive readers."""

from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock
import zipfile

from buildish_release_tooling.shared.archive import (
    ArchiveLimitExceededError,
    ArchiveLimits,
    ArchiveReadBudget,
    read_tar_entries,
    read_zip_entries,
)
from tests.release.archive_support import write_tgz_archive, write_zip_archive


class SharedArchiveTest(unittest.TestCase):
    """Verify shared archive readers enforce budgets while streaming payloads."""

    def test_read_zip_entries_hashes_members_without_zip_read(self) -> None:
        with TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "fixture.zip"
            write_zip_archive(
                archive_path,
                members=[
                    ("pkg/a.txt", b"payload\n", (2026, 5, 2, 9, 0, 1), 0o100644),
                ],
            )

            with mock.patch.object(zipfile.ZipFile, "read", side_effect=AssertionError("unexpected read")):
                entries = read_zip_entries(archive_path)

        self.assertEqual(["pkg/a.txt"], [entry.name for entry in entries])
        self.assertEqual(hashlib.sha512(b"payload\n").hexdigest(), entries[0].content_sha512)

    def test_read_zip_entries_rejects_entry_count_limit(self) -> None:
        with TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "fixture.zip"
            write_zip_archive(
                archive_path,
                members=[
                    ("pkg/a.txt", b"a\n", (2026, 5, 2, 9, 0, 1), 0o100644),
                    ("pkg/b.txt", b"b\n", (2026, 5, 2, 9, 0, 1), 0o100644),
                ],
            )

            with self.assertRaises(ArchiveLimitExceededError):
                read_zip_entries(archive_path, limits=ArchiveLimits(max_entries=1))

    def test_read_tar_entries_rejects_total_member_size_limit(self) -> None:
        with TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "fixture.tgz"
            write_tgz_archive(
                archive_path,
                members=[
                    ("pkg/a.txt", b"abcd", 1714633201, 0o644),
                    ("pkg/b.txt", b"efgh", 1714633201, 0o644),
                ],
            )

            with self.assertRaises(ArchiveLimitExceededError):
                read_tar_entries(
                    archive_path,
                    limits=ArchiveLimits(max_member_bytes=10, max_total_member_bytes=7),
                )

    def test_archive_budget_rejects_huge_declared_members_without_huge_fixture(self) -> None:
        budget = ArchiveReadBudget(ArchiveLimits(max_member_bytes=25, max_total_member_bytes=100))

        with self.assertRaises(ArchiveLimitExceededError):
            budget.record_member("huge.bin", size_bytes=26)

