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

"""Tests for inspection-bundle evidence handling."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from apache_buildish_release_tooling.release.verification.inspection_bundle import (
    retain_evidence_file,
)


class InspectionBundleTest(unittest.TestCase):
    """Verify retained evidence files cannot silently overwrite each other."""

    def test_retain_evidence_file_rejects_existing_target_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "one" / "artifact.txt"
            second = root / "two" / "artifact.txt"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_text("one\n", encoding="utf-8")
            second.write_text("two\n", encoding="utf-8")

            retain_evidence_file(
                root / "bundle",
                artifact_id="artifact",
                label_directory="rebuilt",
                source_path=first,
            )

            with self.assertRaisesRegex(ValueError, "already exists"):
                retain_evidence_file(
                    root / "bundle",
                    artifact_id="artifact",
                    label_directory="rebuilt",
                    source_path=second,
                )


if __name__ == "__main__":
    unittest.main()
