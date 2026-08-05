# Copyright 2026 The Buildish Authors
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

import gzip
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import zipfile


class DistributionReproducibilityTests(unittest.TestCase):
    """Ensure release archives are stable across clean working trees."""

    source_date_epoch = 1_785_505_075

    def test_wheel_and_sdist_are_byte_reproducible(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        uv_executable = shutil.which("uv")
        if uv_executable is None:
            self.fail("Expected 'uv' to be available on PATH for package builds.")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            distributions: list[dict[str, bytes]] = []
            for index, timestamp in enumerate((1_704_067_200, 1_706_745_600), start=1):
                source_root = temp_root / f"source-{index}"
                output_root = temp_root / f"dist-{index}"
                shutil.copytree(
                    project_root,
                    source_root,
                    ignore=shutil.ignore_patterns(
                        ".git",
                        ".mypy_cache",
                        ".pytest_cache",
                        ".ruff_cache",
                        ".venv",
                        "__pycache__",
                        "build",
                        "dist",
                    ),
                )
                for path in source_root.rglob("*"):
                    if path.is_file():
                        os.utime(path, (timestamp, timestamp))

                environment = {
                    **os.environ,
                    "SOURCE_DATE_EPOCH": str(self.source_date_epoch),
                }
                completed = subprocess.run(  # noqa: S603
                    [
                        uv_executable,
                        "build",
                        "--no-build-logs",
                        "--no-create-gitignore",
                        "--out-dir",
                        str(output_root),
                    ],
                    cwd=source_root,
                    env=environment,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(
                    0,
                    completed.returncode,
                    msg=(
                        "distribution build failed\n"
                        f"stdout:\n{completed.stdout}\n"
                        f"stderr:\n{completed.stderr}"
                    ),
                )
                distributions.append(
                    {
                        path.name: path.read_bytes()
                        for path in output_root.iterdir()
                        if path.is_file()
                    }
                )

            self.assertEqual(distributions[0], distributions[1])
            self.assertEqual(
                {
                    "buildish_release_tooling-0.1.0-py3-none-any.whl",
                    "buildish_release_tooling-0.1.0.tar.gz",
                },
                set(distributions[0]),
            )

            wheel_path = temp_root / "reproducible.whl"
            wheel_path.write_bytes(
                distributions[0]["buildish_release_tooling-0.1.0-py3-none-any.whl"]
            )
            with zipfile.ZipFile(wheel_path) as wheel:
                self.assertIn(
                    "buildish_release_tooling/release/publications/pypi/attestations.py",
                    wheel.namelist(),
                )
                metadata = wheel.read(
                    "buildish_release_tooling-0.1.0.dist-info/METADATA"
                )
                self.assertIn(b"Provides-Extra: pypi", metadata)
                self.assertIn(
                    b"Requires-Dist: pypi-attestations==0.0.30", metadata
                )

            sdist_path = temp_root / "reproducible.tar.gz"
            sdist_path.write_bytes(
                distributions[0]["buildish_release_tooling-0.1.0.tar.gz"]
            )
            with sdist_path.open("rb") as archive_file:
                archive_file.seek(4)
                self.assertEqual(
                    self.source_date_epoch,
                    int.from_bytes(archive_file.read(4), byteorder="little"),
                )
            with gzip.open(sdist_path, "rb") as gzip_file:
                with tarfile.open(fileobj=gzip_file, mode="r|") as source_tar:
                    for member in source_tar:
                        self.assertEqual(self.source_date_epoch, member.mtime)
                        self.assertEqual(0, member.uid)
                        self.assertEqual(0, member.gid)
                        self.assertEqual("", member.uname)
                        self.assertEqual("", member.gname)


if __name__ == "__main__":
    unittest.main()
