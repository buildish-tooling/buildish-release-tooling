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

"""Regression tests for owned contract-model documentation metadata."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import cast
import unittest

from pydantic import BaseModel

import apache_buildish_release_tooling as rootpkg
from apache_buildish_release_tooling.harness.config import ReleaseHarnessConfig
from apache_buildish_release_tooling.release.contracts import VerifyRcReportV1

_SKIPPED_MODEL_MODULE_PREFIXES = (
    "apache_buildish_release_tooling.release.github_api_models",
)


def _iter_documented_models() -> list[type[BaseModel]]:
    """Return the owned model classes that must remain self-documented."""

    models: list[type[BaseModel]] = []
    for module_info in pkgutil.walk_packages(rootpkg.__path__, rootpkg.__name__ + "."):
        module_name = module_info.name
        if any(
            module_name.startswith(prefix)
            for prefix in _SKIPPED_MODEL_MODULE_PREFIXES
        ):
            continue
        module = importlib.import_module(module_name)
        for candidate in vars(module).values():
            if (
                inspect.isclass(candidate)
                and issubclass(candidate, BaseModel)
                and candidate.__module__ == module_name
            ):
                models.append(candidate)
    return sorted(models, key=lambda model: (model.__module__, model.__name__))


class ContractDocumentationTest(unittest.TestCase):
    """Ensure owned typed models remain self-documented for future schema export."""

    def test_owned_models_have_docstrings_and_field_descriptions(self) -> None:
        failures: list[str] = []
        for model in _iter_documented_models():
            if not inspect.getdoc(model):
                failures.append(f"{model.__module__}:{model.__name__}:__doc__")
            for field_name, field in model.model_fields.items():
                if not field.description:
                    failures.append(f"{model.__module__}:{model.__name__}:{field_name}")
        self.assertEqual([], failures)

    def test_report_schema_includes_documented_nested_definitions(self) -> None:
        schema = VerifyRcReportV1.model_json_schema()
        self.assertTrue(schema.get("description"))
        self.assertEqual(
            {"category": "emitted", "ownership": "tooling-derived"},
            schema.get("x-buildish-contract"),
        )

        definitions = schema.get("$defs")
        self.assertIsInstance(definitions, dict)
        definitions = cast(dict[str, object], definitions)
        nested_definition = definitions.get("ArtifactReproducibilityCanonicalBuildRecipeReport")
        self.assertIsInstance(nested_definition, dict)
        nested_definition = cast(dict[str, object], nested_definition)
        self.assertTrue(nested_definition.get("description"))
        nested_properties = nested_definition.get("properties")
        self.assertIsInstance(nested_properties, dict)
        nested_properties = cast(dict[str, object], nested_properties)
        command_property = nested_properties.get("command")
        self.assertIsInstance(command_property, dict)
        command_property = cast(dict[str, object], command_property)
        self.assertTrue(command_property.get("description"))

    def test_harness_config_schema_includes_documented_nested_definitions(self) -> None:
        schema = ReleaseHarnessConfig.model_json_schema()
        self.assertTrue(schema.get("description"))
        self.assertEqual(
            {"category": "authored", "ownership": "consumer-owned"},
            schema.get("x-buildish-contract"),
        )

        definitions = schema.get("$defs")
        self.assertIsInstance(definitions, dict)
        definitions = cast(dict[str, object], definitions)
        nested_definition = definitions.get("SelfRepositoryConfig")
        self.assertIsInstance(nested_definition, dict)
        nested_definition = cast(dict[str, object], nested_definition)
        self.assertTrue(nested_definition.get("description"))
        nested_properties = nested_definition.get("properties")
        self.assertIsInstance(nested_properties, dict)
        nested_properties = cast(dict[str, object], nested_properties)
        local_checkout_mode_property = nested_properties.get("local_checkout_mode")
        self.assertIsInstance(local_checkout_mode_property, dict)
        local_checkout_mode_property = cast(dict[str, object], local_checkout_mode_property)
        self.assertTrue(local_checkout_mode_property.get("description"))
