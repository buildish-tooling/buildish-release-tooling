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

"""Tests for shared bounded structured-file parsing helpers."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pydantic import BaseModel

from buildish_release_tooling.shared.io import ByteLimitExceededError
from buildish_release_tooling.shared.parsing import (
    read_json_object_file_bounded,
    read_pydantic_json_file_bounded,
    read_toml_file_bounded,
    read_yaml_mapping_file_bounded,
)


class _PayloadModel(BaseModel):
    name: str


class SharedParsingTest(unittest.TestCase):
    """Verify structured parsers enforce byte limits before parsing."""

    def test_read_json_object_file_bounded_parses_mapping(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "payload.json"
            path.write_text('{"name": "buildish"}\n', encoding="utf-8")

            self.assertEqual(
                {"name": "buildish"},
                read_json_object_file_bounded(path, max_bytes=100),
            )

    def test_read_json_object_file_bounded_rejects_non_mapping(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "payload.json"
            path.write_text('["buildish"]\n', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "JSON object"):
                read_json_object_file_bounded(path, max_bytes=100)

    def test_read_pydantic_json_file_bounded_validates_model(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "payload.json"
            path.write_text('{"name": "buildish"}\n', encoding="utf-8")

            self.assertEqual(
                "buildish",
                read_pydantic_json_file_bounded(_PayloadModel, path, max_bytes=100).name,
            )

    def test_read_yaml_mapping_file_bounded_parses_mapping(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "payload.yaml"
            path.write_text("name: buildish\n", encoding="utf-8")

            self.assertEqual(
                {"name": "buildish"},
                read_yaml_mapping_file_bounded(path, max_bytes=100),
            )

    def test_read_toml_file_bounded_parses_mapping(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "payload.toml"
            path.write_text('name = "buildish"\n', encoding="utf-8")

            self.assertEqual(
                {"name": "buildish"},
                read_toml_file_bounded(path, max_bytes=100),
            )

    def test_parsers_reject_oversized_files_before_parsing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "payload.json"
            path.write_text('{"name": "buildish"}\n', encoding="utf-8")

            with self.assertRaises(ByteLimitExceededError):
                read_json_object_file_bounded(path, max_bytes=3)


if __name__ == "__main__":
    unittest.main()
