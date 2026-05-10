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

"""Release-legal artifact generation tests."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
from unittest import mock

from apache_buildish_release_tooling.legal.release_legal import (
    LockedPackage,
    collect_curated_legal_files,
    curated_container_image_bundles_by_ref,
    export_locked_runtime_packages,
    generate_release_legal_artifacts,
)


from tests.release_legal_support import ReleaseLegalTestBase


class ReleaseLegalGenerationTests(ReleaseLegalTestBase):
    """Release-legal artifact generation tests."""

    def test_export_locked_runtime_packages_uses_bounded_logged_command_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            def fake_run_logged_command(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                output_path = Path(command[-1])
                output_path.write_text(
                    "\n".join(
                        [
                            "[[packages]]",
                            'name = "demo-runtime"',
                            'version = "1.2.3"',
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(command, 0, "", "advisory warning\n")

            with mock.patch(
                "apache_buildish_release_tooling.legal.release_legal.run_logged_command",
                side_effect=fake_run_logged_command,
            ) as run_logged_command:
                packages = export_locked_runtime_packages(root)

        self.assertEqual(("demo-runtime",), tuple(package.name for package in packages))
        run_logged_command.assert_called_once()
        _command, kwargs = run_logged_command.call_args
        self.assertEqual(root, kwargs["cwd"])
        self.assertTrue(kwargs["check"])
        self.assertTrue(kwargs["capture_output"])
        self.assertFalse(kwargs["log_command"])
        self.assertEqual(15 * 60, kwargs["timeout_seconds"])

    def test_curated_legal_file_collection_rejects_oversized_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            license_path = root / "LICENSE"
            with license_path.open("wb") as handle:
                handle.truncate((25 * 1024 * 1024) + 1)

            with self.assertRaisesRegex(RuntimeError, "too large"):
                collect_curated_legal_files(
                    component_key="demo-image",
                    component_kind="container-base-image",
                    license_paths=(license_path,),
                    notice_paths=(),
                )

    def test_curated_container_bundle_manifest_rejects_path_escapes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = root / "base-image-bundles.toml"
            manifest_path.write_text(
                "\n".join(
                    [
                        "[[bundles]]",
                        'image-ref = "example.invalid/image@sha256:abc"',
                        'name = "image"',
                        'version = "1"',
                        'output-key = "image"',
                        'license-files = ["../LICENSE"]',
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "project root"):
                curated_container_image_bundles_by_ref(project_dir=root, manifest_path=manifest_path)

    def test_curated_container_bundle_manifest_rejects_output_key_escapes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = root / "base-image-bundles.toml"
            manifest_path.write_text(
                "\n".join(
                    [
                        "[[bundles]]",
                        'image-ref = "example.invalid/image@sha256:abc"',
                        'name = "image"',
                        'version = "1"',
                        'output-key = "../image"',
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "output-key"):
                curated_container_image_bundles_by_ref(project_dir=root, manifest_path=manifest_path)

    def test_generate_release_legal_artifacts_writes_preliminary_files_and_inventory(
        self,
    ) -> None:
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
            inventory_markdown = (details_output_dir / "inventory.md").read_text(
                encoding="utf-8"
            )
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
            [
                "LICENSE",
                "NOTICE",
                "inventory.json",
                "inventory.md",
                "licenses",
                "notices",
            ],
        )
        self.assertEqual(
            [path.parent for path in written_paths[:2]],
            [output_dir, output_dir],
        )
        self.assertEqual(
            [path.parent for path in written_paths[2:]],
            [
                details_output_dir,
                details_output_dir,
                details_output_dir,
                details_output_dir,
            ],
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
        self.assertNotIn(
            "originalRelativePath", inventory["entries"][0]["licenseFiles"][0]
        )
        self.assertIn("Apache License text", license_text)
        self.assertIn("This product bundles demo-runtime.", license_text)
        self.assertIn("Project URL: https://github.invalid/demo-runtime", license_text)
        self.assertIn("License: MIT", license_text)
        self.assertNotIn("Generated at:", license_text)
        self.assertNotIn("Version: 2.3.4", license_text)
        self.assertNotIn("SPDX license expression:", license_text)
        self.assertNotIn("Copied license files:", license_text)
        self.assertNotIn("Source: index", license_text)
        self.assertNotIn(
            "This product bundles apache-buildish-release-tooling.", license_text
        )
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

    def test_generate_release_legal_artifacts_does_not_include_curated_container_base_image_licenses_when_disabled(
        self,
    ) -> None:
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

            inventory = json.loads(
                (output_dir / "inventory.json").read_text(encoding="utf-8")
            )
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

    def test_generate_release_legal_artifacts_omits_classifier_only_review_note_in_license(
        self,
    ) -> None:
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

        self.assertIn(
            "Project URL: https://github.invalid/classifier-runtime", license_text
        )
        self.assertNotIn("Review notes:", license_text)
        self.assertNotIn(
            "The package does not declare a dedicated SPDX `License-Expression` or plain `License` field.",
            license_text,
        )
        self.assertNotIn("Review flags: classifier-only-license-metadata", license_text)
