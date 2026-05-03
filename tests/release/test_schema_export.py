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

"""Tests for generated JSON Schema and Markdown reference exports."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from apache_buildish_release_tooling.docs.documentation import DocumentedContractModel
from apache_buildish_release_tooling.docs.reference_export import _build_anchor_index, _collect_reachable_models
from apache_buildish_release_tooling.docs.schema_export import (
    _build_parser,
    authored_schema_exports,
    build_schema_document,
    main,
    schema_exports,
    write_reference_file,
    write_schema_files,
)
from apache_buildish_release_tooling.harness import config as harness_config_models
from apache_buildish_release_tooling.harness import models as harness_models
from apache_buildish_release_tooling.harness import shim_builtins as harness_shim_models
from apache_buildish_release_tooling.release import command_manifests as release_command_manifests
from apache_buildish_release_tooling.release import contracts as release_contracts
from apache_buildish_release_tooling.release import models as release_models


def _reference_model_roots() -> tuple[type[DocumentedContractModel], ...]:
    modules = (
        release_models,
        release_contracts,
        release_command_manifests,
        harness_config_models,
        harness_models,
        harness_shim_models,
    )
    models: list[type[DocumentedContractModel]] = []
    for module in modules:
        for candidate in vars(module).values():
            if (
                isinstance(candidate, type)
                and issubclass(candidate, DocumentedContractModel)
                and candidate.__module__ == module.__name__
            ):
                models.append(candidate)
    return tuple(sorted(models, key=lambda model: (model.__module__, model.__name__)))


class SchemaExportTests(unittest.TestCase):
    """Verify the checked-in schema export workflow."""

    def test_generated_schema_uses_model_metadata_and_contract_classification(self) -> None:
        component_export = next(
            export
            for export in schema_exports()
            if export.filename == "buildish-release-tooling-component-config.schema.json"
        )
        component_schema = build_schema_document(component_export)

        self.assertEqual(component_schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(
            component_schema["$id"],
            "https://buildish.apache.org/components/buildish-release-tooling/schemas/buildish-release-tooling-component-config.schema.json",
        )
        self.assertIn("Do not edit by hand", component_schema["$comment"])
        self.assertEqual(
            component_schema["x-buildish-contract"],
            {
                "category": "authored",
                "ownership": "component-owned",
                "summary": "Component-authored `release-config.yaml` contract for release policy and target integration settings.",
                "filePath": "release-config.yaml",
            },
        )
        self.assertEqual(
            component_schema["properties"]["component_id"]["description"],
            "Stable component identifier used across Buildish manifests, reports, and release-state records.",
        )

        command_export = next(
            export
            for export in schema_exports()
            if export.filename == "buildish-release-tooling-prepare-rc-manifest.schema.json"
        )
        command_schema = build_schema_document(command_export)
        self.assertEqual(
            command_schema["x-buildish-contract"]["ownership"],
            "tooling-derived",
        )
        self.assertIn("not a supported external API", command_schema["description"])

    def test_generated_reference_doc_matches_checked_in_output(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            generated_reference_path = Path(tempdir) / "release-model-schema-reference.md"
            write_reference_file(generated_reference_path)
            checked_in_reference_path = (
                Path(__file__).resolve().parents[2] / "docs/reference/release-model-schema-reference.md"
            )
            generated_reference_text = generated_reference_path.read_text(encoding="utf-8")

            self.assertEqual(
                checked_in_reference_path.read_text(encoding="utf-8"),
                generated_reference_text,
            )
            self.assertIn(
                "This reference describes the typed Buildish Release Tooling contracts that are checked into this repository.",
                generated_reference_text,
            )
            self.assertIn("### Internal unstable command action manifests", generated_reference_text)
            self.assertIn(
                "[`buildish-release-tooling-verify-rc-report-v1.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-verify-rc-report-v1.schema.json)",
                generated_reference_text,
            )
            self.assertIn(
                "| <a id=\"componentconfig-component-id\"></a>`component_id` | str | yes |",
                generated_reference_text,
            )
            self.assertIn("- audience: `internal`", generated_reference_text)
            self.assertIn("- stability: `unstable`", generated_reference_text)
            self.assertNotIn("**UX warning:**", generated_reference_text)

    def test_export_inventory_covers_supported_and_internal_contracts(self) -> None:
        export_names = {export.filename for export in schema_exports()}

        self.assertIn("buildish-release-tooling-component-config.schema.json", export_names)
        self.assertIn("buildish-release-tooling-rc-vote-manifest-v1.schema.json", export_names)
        self.assertIn("buildish-release-tooling-verify-rc-report-v1.schema.json", export_names)
        self.assertIn("buildish-release-tooling-inspection-bundle-manifest-v1.schema.json", export_names)
        self.assertIn("buildish-release-tooling-harness-scenario.schema.json", export_names)
        self.assertIn("buildish-release-tooling-command-action-manifest.schema.json", export_names)
        self.assertIn("buildish-release-tooling-prepare-rc-manifest.schema.json", export_names)
        self.assertGreaterEqual(len(export_names), 20)

        authored_names = {export.filename for export in authored_schema_exports()}
        self.assertIn("buildish-release-tooling-component-config.schema.json", authored_names)
        self.assertIn("buildish-release-tooling-release-harness-config.schema.json", authored_names)
        self.assertIn("buildish-release-tooling-harness-scenario.schema.json", authored_names)

    def test_reference_roots_cover_all_documented_models(self) -> None:
        reachable_models = set(_collect_reachable_models(schema_exports()))
        documented_models = set(_reference_model_roots())

        self.assertEqual(documented_models, reachable_models)

    def test_checked_in_schema_files_match_generated_output(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            generated_dir = Path(tempdir)
            write_schema_files(generated_dir)
            checked_in_dir = Path(__file__).resolve().parents[2] / "site/pages/schemas"

            self.assertEqual(
                sorted(path.name for path in checked_in_dir.glob("*.json")),
                sorted(export.filename for export in schema_exports()),
            )

            for name in [export.filename for export in schema_exports()]:
                self.assertEqual(
                    json.loads((checked_in_dir / name).read_text(encoding="utf-8")),
                    json.loads((generated_dir / name).read_text(encoding="utf-8")),
                )

    def test_anchor_index_covers_release_tooling_models(self) -> None:
        reachable_models = _collect_reachable_models(schema_exports())
        anchors = _build_anchor_index(models=reachable_models, enums=(), scalar_entries=())

        self.assertIn("ComponentConfig", anchors.type_anchors)
        self.assertIn(("ComponentConfig", "component_id"), anchors.field_anchors)
        self.assertIn(("PrepareRcManifest", "source_date_epoch"), anchors.field_anchors)

    def test_main_uses_parser_defaults_and_prints_written_paths(self) -> None:
        parser = _build_parser()
        namespace = parser.parse_args([])

        self.assertEqual(namespace.output_dir, "site/pages/schemas")
        self.assertEqual(
            namespace.reference_output,
            "docs/reference/release-model-schema-reference.md",
        )

        with tempfile.TemporaryDirectory() as tempdir:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--output-dir",
                        tempdir,
                        "--reference-output",
                        str(Path(tempdir) / "release-model-schema-reference.md"),
                    ]
                )

            written_lines = [line for line in stdout.getvalue().splitlines() if line.strip()]

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(written_lines), len(schema_exports()) + 1)
        self.assertTrue(
            written_lines[0].endswith("buildish-release-tooling-component-config.schema.json")
        )
        self.assertTrue(written_lines[-1].endswith("release-model-schema-reference.md"))


if __name__ == "__main__":
    unittest.main()
