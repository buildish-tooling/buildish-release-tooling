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

"""Release-legal report construction and policy tests."""

from __future__ import annotations

from pathlib import Path
import tempfile

from apache_buildish_release_tooling.legal.release_legal import (
    LockedPackage,
    build_release_legal_report,
)


from tests.release_legal_support import ReleaseLegalTestBase


class ReleaseLegalReportTests(ReleaseLegalTestBase):
    """Release-legal report construction and policy tests."""

    def test_build_release_legal_report_collects_license_and_notice_files(self) -> None:
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
                    "Summary: Demo runtime",
                    "License-Expression: MIT",
                    "Project-URL: Homepage, https://example.invalid/demo-runtime",
                    "License-File: licenses/LICENSE",
                ),
                record_entries=(
                    "demo_runtime/__init__.py,,",
                    "demo_runtime-2.3.4.dist-info/METADATA,,",
                    "demo_runtime-2.3.4.dist-info/RECORD,,",
                    "demo_runtime-2.3.4.dist-info/licenses/LICENSE,,",
                    "demo_runtime-2.3.4.dist-info/NOTICE,,",
                ),
                file_contents={
                    "demo_runtime/__init__.py": "",
                    "demo_runtime-2.3.4.dist-info/licenses/LICENSE": "Demo license text\n",
                    "demo_runtime-2.3.4.dist-info/NOTICE": "Demo notice text\n",
                },
            )
            report = build_release_legal_report(
                project_dir=root,
                locked_packages=(
                    LockedPackage(
                        name="demo-runtime",
                        version="2.3.4",
                        source_kind="index",
                        source_reference="https://pypi.org/simple",
                    ),
                ),
                distribution_search_paths=(root,),
            )

        self.assertEqual(len(report.entries), 1)
        entry = report.entries[0]
        self.assertEqual(entry.name, "demo-runtime")
        self.assertEqual(entry.declared_license_summary, "SPDX: MIT")
        self.assertEqual(
            [file.output_relative_path for file in entry.license_files],
            ["licenses/demo-runtime/LICENSE"],
        )
        self.assertEqual(
            [file.output_relative_path for file in entry.notice_files],
            ["notices/demo-runtime/NOTICE"],
        )
        self.assertIn("bundled-notice-files-require-review", entry.review_flags)

    def test_build_release_legal_report_rejects_category_x_spdx_license_expression(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_distribution(
                root=root,
                name="forbidden-runtime",
                version="9.9.9",
                metadata_lines=(
                    "Metadata-Version: 2.4",
                    "Name: forbidden-runtime",
                    "Version: 9.9.9",
                    "License-Expression: GPL-3.0-only",
                ),
                record_entries=(
                    "forbidden_runtime/__init__.py,,",
                    "forbidden_runtime-9.9.9.dist-info/METADATA,,",
                    "forbidden_runtime-9.9.9.dist-info/RECORD,,",
                ),
                file_contents={"forbidden_runtime/__init__.py": ""},
            )

            with self.assertRaisesRegex(RuntimeError, "Category X"):
                build_release_legal_report(
                    project_dir=root,
                    locked_packages=(
                        LockedPackage(
                            name="forbidden-runtime",
                            version="9.9.9",
                            source_kind="index",
                            source_reference="https://pypi.org/simple",
                        ),
                    ),
                    distribution_search_paths=(root,),
                )

    def test_build_release_legal_report_accepts_or_expression_with_allowed_choice(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_distribution(
                root=root,
                name="choice-runtime",
                version="1.0.0",
                metadata_lines=(
                    "Metadata-Version: 2.4",
                    "Name: choice-runtime",
                    "Version: 1.0.0",
                    "License-Expression: MIT OR GPL-3.0-only",
                ),
                record_entries=(
                    "choice_runtime/__init__.py,,",
                    "choice_runtime-1.0.0.dist-info/METADATA,,",
                    "choice_runtime-1.0.0.dist-info/RECORD,,",
                    "choice_runtime-1.0.0.dist-info/LICENSE,,",
                ),
                file_contents={
                    "choice_runtime/__init__.py": "",
                    "choice_runtime-1.0.0.dist-info/LICENSE": "Choice runtime license\n",
                },
            )

            report = build_release_legal_report(
                project_dir=root,
                locked_packages=(
                    LockedPackage(
                        name="choice-runtime",
                        version="1.0.0",
                        source_kind="index",
                        source_reference="https://pypi.org/simple",
                    ),
                ),
                distribution_search_paths=(root,),
            )

        self.assertEqual(report.entries[0].license_expression, "MIT OR GPL-3.0-only")

    def test_build_release_legal_report_orders_entries_deterministically_by_name(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_distribution(
                root=root,
                name="zeta-runtime",
                version="1.0.0",
                metadata_lines=(
                    "Metadata-Version: 2.4",
                    "Name: zeta-runtime",
                    "Version: 1.0.0",
                    "License-Expression: MIT",
                ),
                record_entries=(
                    "zeta_runtime/__init__.py,,",
                    "zeta_runtime-1.0.0.dist-info/METADATA,,",
                    "zeta_runtime-1.0.0.dist-info/RECORD,,",
                ),
                file_contents={"zeta_runtime/__init__.py": ""},
            )
            self._write_distribution(
                root=root,
                name="alpha-runtime",
                version="1.0.0",
                metadata_lines=(
                    "Metadata-Version: 2.4",
                    "Name: alpha-runtime",
                    "Version: 1.0.0",
                    "License-Expression: MIT",
                ),
                record_entries=(
                    "alpha_runtime/__init__.py,,",
                    "alpha_runtime-1.0.0.dist-info/METADATA,,",
                    "alpha_runtime-1.0.0.dist-info/RECORD,,",
                ),
                file_contents={"alpha_runtime/__init__.py": ""},
            )

            report = build_release_legal_report(
                project_dir=root,
                locked_packages=(
                    LockedPackage(
                        name="zeta-runtime",
                        version="1.0.0",
                        source_kind="index",
                        source_reference="https://pypi.org/simple",
                    ),
                    LockedPackage(
                        name="alpha-runtime",
                        version="1.0.0",
                        source_kind="index",
                        source_reference="https://pypi.org/simple",
                    ),
                ),
                distribution_search_paths=(root,),
            )

        self.assertEqual(
            [entry.name for entry in report.entries], ["alpha-runtime", "zeta-runtime"]
        )
