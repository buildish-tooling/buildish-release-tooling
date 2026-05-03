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

"""Tests for the preliminary release-legal generator."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from apache_buildish_release_tooling.legal.release_legal import (
    LockedPackage,
    build_release_legal_report,
    generate_release_legal_artifacts,
    installed_distributions_by_name,
    locked_runtime_packages_from_pylock_text,
)


class ReleaseLegalTests(unittest.TestCase):
    """Verify the runtime legal inventory helper and generated review files."""

    def test_locked_runtime_packages_from_pylock_text_reads_index_and_directory_entries(self) -> None:
        packages = locked_runtime_packages_from_pylock_text(
            """
lock-version = "1.0"

[[packages]]
name = "demo-runtime"
version = "2.3.4"
index = "https://pypi.org/simple"

[[packages]]
name = "apache-buildish-release-tooling"
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
                    name="apache-buildish-release-tooling",
                    version=None,
                    source_kind="directory",
                    source_reference=".",
                ),
            ),
        )

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
        self.assertEqual([file.output_relative_path for file in entry.license_files], ["licenses/demo-runtime/LICENSE"])
        self.assertEqual([file.output_relative_path for file in entry.notice_files], ["notices/demo-runtime/NOTICE"])
        self.assertIn("bundled-notice-files-require-review", entry.review_flags)

    def test_installed_distributions_by_name_prefers_dist_info_over_duplicate_egg_info(self) -> None:
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
            chosen_has_record = distributions["demo-runtime"].read_text("RECORD") is not None
            chosen_version = distributions["demo-runtime"].version

        self.assertTrue(chosen_has_record)
        self.assertEqual(chosen_version, "2.3.4")

    def test_generate_release_legal_artifacts_writes_preliminary_files_and_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "out"
            details_output_dir = root / "dist" / "release-legal-preliminary"
            self._write_distribution(
                root=root,
                name="apache-buildish-release-tooling",
                version="0.1.0",
                metadata_lines=(
                    "Metadata-Version: 2.4",
                    "Name: apache-buildish-release-tooling",
                    "Version: 0.1.0",
                    "Requires-Dist: demo-runtime>=2",
                    "License-File: LICENSE",
                    "License-File: NOTICE",
                ),
                record_entries=(
                    "apache_buildish_release_tooling/__init__.py,,",
                    "apache_buildish_release_tooling-0.1.0.dist-info/METADATA,,",
                    "apache_buildish_release_tooling-0.1.0.dist-info/RECORD,,",
                    "apache_buildish_release_tooling-0.1.0.dist-info/licenses/LICENSE,,",
                    "apache_buildish_release_tooling-0.1.0.dist-info/licenses/NOTICE,,",
                ),
                file_contents={
                    "apache_buildish_release_tooling/__init__.py": "",
                    "apache_buildish_release_tooling-0.1.0.dist-info/licenses/LICENSE": "Project bundled license\n",
                    "apache_buildish_release_tooling-0.1.0.dist-info/licenses/NOTICE": "Project bundled notice\n",
                },
            )
            self._write_distribution(
                root=root,
                name="demo-runtime",
                version="2.3.4",
                metadata_lines=(
                    "Metadata-Version: 2.4",
                    "Name: demo-runtime",
                    "Version: 2.3.4",
                    "License-Expression: MIT",
                    "Project-URL: Repository, https://github.invalid/demo-runtime",
                ),
                record_entries=(
                    "demo_runtime/__init__.py,,",
                    "demo_runtime-2.3.4.dist-info/METADATA,,",
                    "demo_runtime-2.3.4.dist-info/RECORD,,",
                    "demo_runtime-2.3.4.dist-info/LICENSE,,",
                ),
                file_contents={
                    "demo_runtime/__init__.py": "",
                    "demo_runtime-2.3.4.dist-info/LICENSE": "Demo runtime license\n",
                },
            )

            written_paths = generate_release_legal_artifacts(
                project_dir=root,
                output_dir=output_dir,
                details_output_dir=details_output_dir,
                distribution_search_paths=(root,),
                locked_packages=(
                    LockedPackage(
                        name="apache-buildish-release-tooling",
                        version=None,
                        source_kind="directory",
                        source_reference=".",
                    ),
                    LockedPackage(
                        name="demo-runtime",
                        version="2.3.4",
                        source_kind="index",
                        source_reference="https://pypi.org/simple",
                    ),
                ),
                project_license_text="Apache License text\n",
                project_notice_text="Apache project notice\n",
            )

            inventory = json.loads(
                (details_output_dir / "inventory.json").read_text(encoding="utf-8")
            )
            license_text = (output_dir / "LICENSE").read_text(encoding="utf-8")
            notice_text = (output_dir / "NOTICE").read_text(encoding="utf-8")
            inventory_markdown = (details_output_dir / "inventory.md").read_text(encoding="utf-8")
            demo_license_exists = (
                details_output_dir / "licenses" / "demo-runtime" / "LICENSE"
            ).is_file()
            output_dir_entries = sorted(path.name for path in output_dir.iterdir())
            tracked_inventory_exists = (output_dir / "inventory.json").exists()
            tracked_inventory_markdown_exists = (output_dir / "inventory.md").exists()
            tracked_licenses_exists = (output_dir / "licenses").exists()
            tracked_notices_exists = (output_dir / "notices").exists()

        self.assertEqual(
            [path.name for path in written_paths],
            ["LICENSE", "NOTICE", "inventory.json", "inventory.md", "licenses", "notices"],
        )
        self.assertEqual(
            [path.parent for path in written_paths[:2]],
            [output_dir, output_dir],
        )
        self.assertEqual(
            [path.parent for path in written_paths[2:]],
            [details_output_dir, details_output_dir, details_output_dir, details_output_dir],
        )
        self.assertEqual(
            output_dir_entries,
            ["LICENSE", "NOTICE"],
        )
        self.assertFalse(tracked_inventory_exists)
        self.assertFalse(tracked_inventory_markdown_exists)
        self.assertFalse(tracked_licenses_exists)
        self.assertFalse(tracked_notices_exists)
        self.assertEqual(inventory["summary"]["runtimePackageCount"], 2)
        self.assertNotIn("generatedAt", inventory)
        self.assertNotIn("projectDir", inventory)
        self.assertNotIn("pythonExecutable", inventory)
        self.assertNotIn("version", inventory["entries"][0])
        self.assertNotIn("installedPath", inventory["entries"][0]["licenseFiles"][0])
        self.assertNotIn("originalRelativePath", inventory["entries"][0]["licenseFiles"][0])
        self.assertIn("Apache License text", license_text)
        self.assertIn("This product bundles demo-runtime.", license_text)
        self.assertIn("Project URL: https://github.invalid/demo-runtime", license_text)
        self.assertIn("License: MIT", license_text)
        self.assertNotIn("Generated at:", license_text)
        self.assertNotIn("Version: 2.3.4", license_text)
        self.assertNotIn("SPDX license expression:", license_text)
        self.assertNotIn("Copied license files:", license_text)
        self.assertNotIn("Source: index", license_text)
        self.assertNotIn("This product bundles apache-buildish-release-tooling.", license_text)
        self.assertIn("Apache project notice", notice_text)
        self.assertNotIn("Generated at:", notice_text)
        self.assertNotIn(
            "This product bundles apache-buildish-release-tooling with the following in its NOTICE file:",
            notice_text,
        )
        self.assertIn("| `demo-runtime` | `index` |", inventory_markdown)
        self.assertNotIn("generated at:", inventory_markdown)
        self.assertNotIn("### demo-runtime 2.3.4", inventory_markdown)
        self.assertTrue(demo_license_exists)

    def test_build_release_legal_report_rejects_category_x_spdx_license_expression(self) -> None:
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

    def test_build_release_legal_report_accepts_or_expression_with_allowed_choice(self) -> None:
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

    def test_generate_release_legal_artifacts_does_not_include_curated_container_base_image_licenses_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "out"
            self._write_distribution(
                root=root,
                name="demo-runtime",
                version="2.3.4",
                metadata_lines=(
                    "Metadata-Version: 2.4",
                    "Name: demo-runtime",
                    "Version: 2.3.4",
                    "License-Expression: MIT",
                ),
                record_entries=(
                    "demo_runtime/__init__.py,,",
                    "demo_runtime-2.3.4.dist-info/METADATA,,",
                    "demo_runtime-2.3.4.dist-info/RECORD,,",
                    "demo_runtime-2.3.4.dist-info/LICENSE,,",
                ),
                file_contents={
                    "demo_runtime/__init__.py": "",
                    "demo_runtime-2.3.4.dist-info/LICENSE": "Demo runtime license\n",
                },
            )
            self._write_site_pipeline_container_legal_inputs(root)

            generate_release_legal_artifacts(
                project_dir=root,
                output_dir=output_dir,
                distribution_search_paths=(root,),
                locked_packages=(
                    LockedPackage(
                        name="demo-runtime",
                        version="2.3.4",
                        source_kind="index",
                        source_reference="https://pypi.org/simple",
                    ),
                ),
                project_license_text="Apache License text\n",
                project_notice_text="Apache project notice\n",
            )

            inventory = json.loads((output_dir / "inventory.json").read_text(encoding="utf-8"))
            license_text = (output_dir / "LICENSE").read_text(encoding="utf-8")
            python_license_exists = (
                output_dir
                / "licenses"
                / "container-base-images"
                / "python-3.13-bookworm"
                / "LICENSE"
            ).is_file()
            uv_license_exists = (
                output_dir
                / "licenses"
                / "container-base-images"
                / "uv-0.9.7"
                / "LICENSE-MIT"
            ).is_file()

        self.assertEqual(inventory["summary"]["runtimePackageCount"], 1)
        self.assertEqual(inventory["summary"]["supplementalComponentCount"], 0)
        self.assertNotIn("This product bundles python.", license_text)
        self.assertNotIn("Project URL: https://www.python.org/", license_text)
        self.assertNotIn("License: Python-2.0", license_text)
        self.assertNotIn("This product bundles uv.", license_text)
        self.assertNotIn("Project URL: https://docs.astral.sh/uv/", license_text)
        self.assertNotIn("License: Apache-2.0 OR MIT", license_text)
        self.assertFalse(python_license_exists)
        self.assertFalse(uv_license_exists)

    def test_generate_release_legal_artifacts_omits_classifier_only_review_note_in_license(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "out"
            self._write_distribution(
                root=root,
                name="classifier-runtime",
                version="1.0.0",
                metadata_lines=(
                    "Metadata-Version: 2.4",
                    "Name: classifier-runtime",
                    "Version: 1.0.0",
                    "Classifier: License :: OSI Approved :: MIT License",
                    "Project-URL: Repository, https://github.invalid/classifier-runtime",
                ),
                record_entries=(
                    "classifier_runtime/__init__.py,,",
                    "classifier_runtime-1.0.0.dist-info/METADATA,,",
                    "classifier_runtime-1.0.0.dist-info/RECORD,,",
                    "classifier_runtime-1.0.0.dist-info/LICENSE,,",
                ),
                file_contents={
                    "classifier_runtime/__init__.py": "",
                    "classifier_runtime-1.0.0.dist-info/LICENSE": "Classifier runtime license\n",
                },
            )

            generate_release_legal_artifacts(
                project_dir=root,
                output_dir=output_dir,
                distribution_search_paths=(root,),
                locked_packages=(
                    LockedPackage(
                        name="classifier-runtime",
                        version="1.0.0",
                        source_kind="index",
                        source_reference="https://pypi.org/simple",
                    ),
                ),
                project_license_text="Apache License text\n",
                project_notice_text="Apache project notice\n",
            )

            license_text = (output_dir / "LICENSE").read_text(encoding="utf-8")

        self.assertIn("Project URL: https://github.invalid/classifier-runtime", license_text)
        self.assertNotIn("Review notes:", license_text)
        self.assertNotIn(
            "The package does not declare a dedicated SPDX `License-Expression` or plain `License` field.",
            license_text,
        )
        self.assertNotIn("Review flags: classifier-only-license-metadata", license_text)

    def test_build_release_legal_report_orders_entries_deterministically_by_name(self) -> None:
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

        self.assertEqual([entry.name for entry in report.entries], ["alpha-runtime", "zeta-runtime"])

    @staticmethod
    def _write_distribution(
        *,
        root: Path,
        name: str,
        version: str,
        metadata_lines: tuple[str, ...],
        record_entries: tuple[str, ...],
        file_contents: dict[str, str],
    ) -> None:
        dist_info = root / f"{name.replace('-', '_')}-{version}.dist-info"
        dist_info.mkdir(parents=True, exist_ok=True)
        (dist_info / "METADATA").write_text(
            "\n".join(metadata_lines) + "\n",
            encoding="utf-8",
        )
        (dist_info / "RECORD").write_text(
            "\n".join(record_entries) + "\n",
            encoding="utf-8",
        )
        for relative_path, text in file_contents.items():
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    @staticmethod
    def _write_egg_info_distribution(
        *,
        root: Path,
        name: str,
        version: str,
        metadata_lines: tuple[str, ...],
    ) -> None:
        egg_info = root / f"{name.replace('-', '_')}.egg-info"
        egg_info.mkdir(parents=True, exist_ok=True)
        (egg_info / "PKG-INFO").write_text(
            "\n".join(metadata_lines) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _write_site_pipeline_container_legal_inputs(root: Path) -> None:
        containerfile = root / "tools" / "release-tooling-image" / "Containerfile"
        containerfile.parent.mkdir(parents=True, exist_ok=True)
        containerfile.write_text(
            "\n".join(
                (
                    "FROM ghcr.io/astral-sh/uv:0.9.7@sha256:ba4857bf2a068e9bc0e64eed8563b065908a4cd6bfb66b531a9c424c8e25e142 AS uvbin",
                    "FROM docker.io/library/python:3.13-bookworm@sha256:345d669f21b1ab934cb67f2015a713ec041bb2ebb8e3f069484839361f64cc53",
                    "COPY --from=uvbin /uv /bin/uv",
                    "COPY --from=uvbin /uvx /bin/uvx",
                    "",
                )
            ),
            encoding="utf-8",
        )
        manifest_path = root / "tools" / "release-tooling-image" / "legal" / "base-image-bundles.toml"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            "\n".join(
                (
                    "[[bundles]]",
                    'image-ref = "docker.io/library/python:3.13-bookworm@sha256:345d669f21b1ab934cb67f2015a713ec041bb2ebb8e3f069484839361f64cc53"',
                    'name = "python"',
                    'version = "3.13-bookworm"',
                    'output-key = "python-3.13-bookworm"',
                    'home-page = "https://www.python.org/"',
                    'license-expression = "Python-2.0"',
                    'license-files = ["tools/release-tooling-image/legal/base-images/python-3.13-bookworm/LICENSE"]',
                    "",
                    "[[bundles]]",
                    'image-ref = "ghcr.io/astral-sh/uv:0.9.7@sha256:ba4857bf2a068e9bc0e64eed8563b065908a4cd6bfb66b531a9c424c8e25e142"',
                    'name = "uv"',
                    'version = "0.9.7"',
                    'output-key = "uv-0.9.7"',
                    'home-page = "https://docs.astral.sh/uv/"',
                    'license-expression = "Apache-2.0 OR MIT"',
                    'license-files = ["tools/release-tooling-image/legal/base-images/uv-0.9.7/LICENSE-APACHE", "tools/release-tooling-image/legal/base-images/uv-0.9.7/LICENSE-MIT"]',
                    "",
                )
            ),
            encoding="utf-8",
        )
        (root / "tools" / "release-tooling-image" / "legal" / "base-images" / "python-3.13-bookworm").mkdir(
            parents=True,
            exist_ok=True,
        )
        (root / "tools" / "release-tooling-image" / "legal" / "base-images" / "uv-0.9.7").mkdir(
            parents=True,
            exist_ok=True,
        )
        (
            root
            / "tools"
            / "release-tooling-image"
            / "legal"
            / "base-images"
            / "python-3.13-bookworm"
            / "LICENSE"
        ).write_text("Python license text\n", encoding="utf-8")
        (
            root
            / "tools"
            / "release-tooling-image"
            / "legal"
            / "base-images"
            / "uv-0.9.7"
            / "LICENSE-APACHE"
        ).write_text("Apache license text\n", encoding="utf-8")
        (
            root
            / "tools"
            / "release-tooling-image"
            / "legal"
            / "base-images"
            / "uv-0.9.7"
            / "LICENSE-MIT"
        ).write_text("MIT license text\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
