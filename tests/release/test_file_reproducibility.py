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

"""Unit tests for file reproducibility helpers."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from buildish_release_tooling.release.verification.secondary.file_reproducibility import (
    _file_bytes_equal,
)


class FileReproducibilityTest(unittest.TestCase):
    """Keep file comparison memory-bounded."""

    def test_file_bytes_equal_streams_files_without_read_bytes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            left = Path(temp_dir) / "left.bin"
            right = Path(temp_dir) / "right.bin"
            left.write_bytes(b"alpha\n")
            right.write_bytes(b"alpha\n")

            with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("unexpected read_bytes")):
                self.assertTrue(_file_bytes_equal(left, right))

    def test_file_bytes_equal_rejects_size_mismatch_without_reading_content(self) -> None:
        with TemporaryDirectory() as temp_dir:
            left = Path(temp_dir) / "left.bin"
            right = Path(temp_dir) / "right.bin"
            left.write_bytes(b"alpha\n")
            right.write_bytes(b"alpha\nbeta\n")

            with mock.patch.object(Path, "open", side_effect=AssertionError("unexpected open")):
                self.assertFalse(_file_bytes_equal(left, right))
