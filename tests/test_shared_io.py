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

"""Tests for shared stream and file I/O helpers."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from apache_buildish_release_tooling.shared.io import (
    ByteLimitExceededError,
    copy_stream_to_path,
    files_equal,
    first_differing_byte,
    hash_file,
    read_bytes_bounded,
)


class SharedIoTest(unittest.TestCase):
    """Verify shared I/O primitives remain bounded and stream-oriented."""

    def test_copy_stream_to_path_hashes_and_replaces_destination_atomically(self) -> None:
        with TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "artifact.bin"
            destination.write_bytes(b"old")

            copied = copy_stream_to_path(
                io.BytesIO(b"payload\n"),
                destination,
                algorithms=("sha256", "sha512"),
            )

            self.assertEqual(destination, copied.path)
            self.assertEqual(8, copied.size_bytes)
            self.assertEqual(b"payload\n", destination.read_bytes())
            self.assertEqual(hashlib.sha256(b"payload\n").hexdigest(), copied.hashes["sha256"])
            self.assertEqual(hashlib.sha512(b"payload\n").hexdigest(), copied.hashes["sha512"])

    def test_copy_stream_to_path_removes_partial_file_after_limit_failure(self) -> None:
        with TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "artifact.bin"
            destination.write_bytes(b"old")

            with self.assertRaises(ByteLimitExceededError):
                copy_stream_to_path(io.BytesIO(b"too large"), destination, max_bytes=3)

            self.assertEqual(b"old", destination.read_bytes())
            self.assertEqual(["artifact.bin"], sorted(path.name for path in Path(temp_dir).iterdir()))

    def test_read_bytes_bounded_rejects_oversized_streams(self) -> None:
        with self.assertRaises(ByteLimitExceededError):
            read_bytes_bounded(io.BytesIO(b"payload"), max_bytes=3)

    def test_file_comparison_helpers_stream_local_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            left = Path(temp_dir) / "left.bin"
            right = Path(temp_dir) / "right.bin"
            other = Path(temp_dir) / "other.bin"
            left.write_bytes(b"abcdef")
            right.write_bytes(b"abcdef")
            other.write_bytes(b"abcxef")

            self.assertTrue(files_equal(left, right, chunk_size=2))
            self.assertFalse(files_equal(left, other, chunk_size=2))
            self.assertIsNone(first_differing_byte(left, right, chunk_size=2))
            self.assertEqual(3, first_differing_byte(left, other, chunk_size=2))
            self.assertEqual(hashlib.sha512(b"abcdef").hexdigest(), hash_file(left))

    def test_first_differing_byte_reports_offset_when_lengths_differ(self) -> None:
        with TemporaryDirectory() as temp_dir:
            left = Path(temp_dir) / "left.bin"
            right = Path(temp_dir) / "right.bin"
            left.write_bytes(b"abc")
            right.write_bytes(b"abcdef")

            self.assertEqual(3, first_differing_byte(left, right, chunk_size=2))
            self.assertEqual(3, first_differing_byte(right, left, chunk_size=2))
