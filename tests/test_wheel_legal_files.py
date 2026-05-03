# Copyright 2026 The Apache Software Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile


class WheelLegalFilesTests(unittest.TestCase):
    def test_built_wheel_includes_dist_info_legal_files_only(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        uv_executable = shutil.which("uv")
        if uv_executable is None:
            self.fail("Expected 'uv' to be available on PATH for the wheel build test.")
        expected_paths = {
            "DISCLAIMER": project_root / "DISCLAIMER",
            "LICENSE": project_root / "dist-release-legal/LICENSE",
            "NOTICE": project_root / "dist-release-legal/NOTICE",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            subprocess.run(  # noqa: S603
                [uv_executable, "build", "--wheel", "--out-dir", str(out_dir)],
                check=True,
                cwd=project_root,
            )

            wheel_path = next(out_dir.glob("*.whl"))
            with zipfile.ZipFile(wheel_path) as wheel_zip:
                names = set(wheel_zip.namelist())
                metadata_path = (
                    "apache_buildish_release_tooling-0.1.0.dist-info/METADATA"
                )
                metadata_text = wheel_zip.read(metadata_path).decode("utf-8")
                self.assertNotIn("LICENSE", names)
                self.assertNotIn("NOTICE", names)
                self.assertNotIn("DISCLAIMER", names)
                self.assertNotIn(
                    "apache_buildish_release_tooling-0.1.0.data/data/LICENSE",
                    names,
                )
                self.assertNotIn(
                    "apache_buildish_release_tooling-0.1.0.data/data/NOTICE",
                    names,
                )
                self.assertNotIn(
                    "apache_buildish_release_tooling-0.1.0.data/data/DISCLAIMER",
                    names,
                )
                self.assertNotIn(
                    "apache_buildish_release_tooling-0.1.0.dist-info/licenses/dist-release-legal/LICENSE",
                    names,
                )
                self.assertNotIn(
                    "apache_buildish_release_tooling-0.1.0.dist-info/licenses/dist-release-legal/NOTICE",
                    names,
                )
                for relative_source_path, source_path in expected_paths.items():
                    wheel_member_path = (
                        "apache_buildish_release_tooling-0.1.0.dist-info/licenses/"
                        f"{relative_source_path}"
                    )
                    self.assertIn(wheel_member_path, names)
                    self.assertEqual(wheel_zip.read(wheel_member_path), source_path.read_bytes())
                self.assertIn("License-File: DISCLAIMER", metadata_text)
                self.assertIn("License-File: LICENSE", metadata_text)
                self.assertIn("License-File: NOTICE", metadata_text)
                self.assertNotIn(
                    "License-File: dist-release-legal/LICENSE",
                    metadata_text,
                )
                self.assertNotIn(
                    "License-File: dist-release-legal/NOTICE",
                    metadata_text,
                )


if __name__ == "__main__":
    unittest.main()
