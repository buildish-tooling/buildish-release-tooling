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

"""Tests for shared release path validators."""

from __future__ import annotations

from pathlib import Path
import unittest

from buildish_release_tooling.release.path_validation import (
    validate_project_relative_path,
    validate_simple_filename,
)


class PathValidationTest(unittest.TestCase):
    """Keep release metadata path validation behavior explicit."""

    def test_validate_simple_filename_rejects_path_components(self) -> None:
        absolute_filename = str(Path.cwd().anchor + "artifact.zip")
        for filename in ("../artifact.zip", "nested/artifact.zip", absolute_filename):
            with self.subTest(filename=filename):
                with self.assertRaisesRegex(ValueError, "simple file name"):
                    validate_simple_filename(filename, field_name="artifact filename")

    def test_validate_simple_filename_accepts_plain_names(self) -> None:
        self.assertEqual(
            "artifact.zip",
            validate_simple_filename(" artifact.zip ", field_name="artifact filename"),
        )

    def test_validate_project_relative_path_rejects_escapes(self) -> None:
        absolute_path = str(Path.cwd().anchor + "m2repo")
        for path in ("../m2repo", "target/../m2repo", absolute_path):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "project root|relative"):
                    validate_project_relative_path(path, field_name="repository_dir")


if __name__ == "__main__":
    unittest.main()
