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

"""Release-legal distribution discovery tests."""

from __future__ import annotations

from pathlib import Path
import tempfile

from buildish_release_tooling.legal.release_legal import (
    LockedPackage,
    collect_distribution_legal_files,
    installed_distributions_by_name,
    locked_runtime_packages_from_pylock_text,
)


from tests.release_legal_support import ReleaseLegalTestBase


class ReleaseLegalDistributionTests(ReleaseLegalTestBase):
    """Release-legal distribution discovery tests."""

    def test_distribution_legal_file_collection_rejects_oversized_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_distribution(
                root=root,
                name="demo-runtime",
                version="2.3.4",
                metadata_lines=(
                    "Metadata-Version: 2.4",
                    "Name: demo-runtime",
                    "Version: 2.3.4",
                    "License-File: LICENSE",
                ),
                record_entries=(
                    "demo_runtime/__init__.py,,",
                    "demo_runtime-2.3.4.dist-info/METADATA,,",
                    "demo_runtime-2.3.4.dist-info/RECORD,,",
                    "demo_runtime-2.3.4.dist-info/licenses/LICENSE,,",
                ),
                file_contents={
                    "demo_runtime/__init__.py": "",
                    "demo_runtime-2.3.4.dist-info/licenses/LICENSE": "",
                },
            )
            license_path = root / "demo_runtime-2.3.4.dist-info" / "licenses" / "LICENSE"
            with license_path.open("wb") as handle:
                handle.truncate((25 * 1024 * 1024) + 1)
            distributions = installed_distributions_by_name((root,))

            with self.assertRaisesRegex(RuntimeError, "too large"):
                collect_distribution_legal_files(distributions["demo-runtime"])

    def test_locked_runtime_packages_from_pylock_text_reads_index_and_directory_entries(
        self,
    ) -> None:
        packages = locked_runtime_packages_from_pylock_text(
            """
lock-version = "1.0"

[[packages]]
name = "demo-runtime"
version = "2.3.4"
index = "https://pypi.org/simple"

[[packages]]
name = "buildish-release-tooling"
directory = { path = ".", editable = true }
"""
        )

        self.assertEqual(
            packages,
            (
                LockedPackage(
                    name="demo-runtime",
                    version="2.3.4",
                    source_kind="index",
                    source_reference="https://pypi.org/simple",
                ),
                LockedPackage(
                    name="buildish-release-tooling",
                    version=None,
                    source_kind="directory",
                    source_reference=".",
                ),
            ),
        )

    def test_installed_distributions_by_name_prefers_dist_info_over_duplicate_egg_info(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_distribution(
                root=root,
                name="demo-runtime",
                version="2.3.4",
                metadata_lines=(
                    "Metadata-Version: 2.4",
                    "Name: demo-runtime",
                    "Version: 2.3.4",
                ),
                record_entries=(
                    "demo_runtime/__init__.py,,",
                    "demo_runtime-2.3.4.dist-info/METADATA,,",
                    "demo_runtime-2.3.4.dist-info/RECORD,,",
                ),
                file_contents={"demo_runtime/__init__.py": ""},
            )
            self._write_egg_info_distribution(
                root=root,
                name="demo-runtime",
                version="2.3.4",
                metadata_lines=(
                    "Metadata-Version: 2.1",
                    "Name: demo-runtime",
                    "Version: 2.3.4",
                ),
            )

            distributions = installed_distributions_by_name((root,))
            chosen_has_record = (
                distributions["demo-runtime"].read_text("RECORD") is not None
            )
            chosen_version = distributions["demo-runtime"].version

        self.assertTrue(chosen_has_record)
        self.assertEqual(chosen_version, "2.3.4")
