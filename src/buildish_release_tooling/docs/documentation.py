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

"""Documentation metadata for Buildish-owned contract models.

The category and ownership axes live on the public model types themselves so
future JSON Schema or Markdown reference generation can group contracts without
maintaining a parallel registry keyed by model class.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
import importlib
import inspect
import pkgutil
from typing import Any, ClassVar, Literal, get_args, get_origin

from pydantic import BaseModel

from buildish_release_tooling.contracts.base import BuildishContractModel
from buildish_release_tooling.docs.reference_docs import ReferenceDocumentation

_MODEL_REGISTRY_PACKAGE_NAMES = (
    "buildish_release_tooling.release",
    "buildish_release_tooling.harness",
)

ContractCategory = Literal["authored", "emitted", "runtime"]
ContractOwnership = Literal[
    "consumer-owned",
    "component-owned",
    "tooling-derived",
    "runtime-derived",
]
SchemaAudience = Literal["supported", "internal"]
SchemaStability = Literal["stable", "unstable"]
ReferenceGroup = Literal[
    "supported-authored-file",
    "supported-emitted-file",
    "supported-emitted-root",
    "internal-stable-file",
    "internal-stable-root",
    "internal-unstable-root",
]
ExampleRenderFormat = Literal["json", "yaml"]
ExampleValueBuilder = Callable[[], object]


@dataclass(frozen=True)
class ContractDocumentation:
    """Structured grouping hints for one Buildish-owned contract model."""

    category: ContractCategory
    ownership: ContractOwnership
    summary: str | None = None
    file_path: str | None = None
    reference: ReferenceDocumentation | None = None

    def as_schema_extension(self) -> dict[str, str]:
        """Return a stable vendor extension for eventual JSON Schema exports."""

        extension: dict[str, str] = {
            "category": self.category,
            "ownership": self.ownership,
        }
        if self.summary is not None:
            extension["summary"] = self.summary
        if self.file_path is not None:
            extension["filePath"] = self.file_path
        return extension


@dataclass(frozen=True)
class SchemaExample:
    """One generated example shared by schema files and reference docs."""

    summary: str
    value_builder: ExampleValueBuilder
    render_format: ExampleRenderFormat = "json"


@dataclass(frozen=True)
class SchemaExportSpecification:
    """Export metadata attached to one checked-in Buildish schema root."""

    filename: str
    audience: SchemaAudience = "supported"
    stability: SchemaStability = "stable"
    file_path: str | None = None
    summary: str | None = None
    description: str | None = None
    reference_group: ReferenceGroup | None = None
    examples: tuple[SchemaExample, ...] = ()


class DocumentedContractModel(BuildishContractModel):
    """Base class for Buildish-owned wire models that expose contract metadata."""

    contract_documentation: ClassVar[ContractDocumentation | None] = None
    schema_export: ClassVar[SchemaExportSpecification | None] = None


class ConsumerOwnedAuthoredModel(DocumentedContractModel):
    """Base class for consumer-authored Buildish config and scenario models."""

    contract_documentation: ClassVar[ContractDocumentation] = ContractDocumentation(
        category="authored",
        ownership="consumer-owned",
    )


class ComponentOwnedAuthoredModel(DocumentedContractModel):
    """Base class for component-authored Buildish configuration models."""

    contract_documentation: ClassVar[ContractDocumentation] = ContractDocumentation(
        category="authored",
        ownership="component-owned",
    )


class ToolingDerivedModel(DocumentedContractModel):
    """Base class for Buildish-emitted manifests, reports, and other owned contracts."""

    contract_documentation: ClassVar[ContractDocumentation] = ContractDocumentation(
        category="emitted",
        ownership="tooling-derived",
    )


class RuntimeDerivedModel(DocumentedContractModel):
    """Base class for Buildish runtime-state and machine-readable helper models."""

    contract_documentation: ClassVar[ContractDocumentation] = ContractDocumentation(
        category="runtime",
        ownership="runtime-derived",
    )


def contract_documentation_for(
    model: type[BaseModel],
) -> ContractDocumentation | None:
    """Return documentation metadata for one Buildish-owned contract model if available."""

    documentation = getattr(model, "contract_documentation", None)
    return documentation if isinstance(documentation, ContractDocumentation) else None


def schema_export_spec_for(
    model: type[BaseModel],
) -> SchemaExportSpecification | None:
    """Return export metadata for one Buildish schema root when present."""

    specification = model.__dict__.get("schema_export")
    return specification if isinstance(specification, SchemaExportSpecification) else None


def field_description_for(model: type[BaseModel], field_name: str) -> str | None:
    """Return the explicit field description for one Buildish-owned model field."""

    model_fields = getattr(model, "model_fields", {})
    field = model_fields.get(field_name)
    if field is None:
        return None
    return field.description


def apply_documentation_to_schema(
    model: type[BaseModel],
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Inject Buildish documentation metadata into one generated JSON Schema."""

    _apply_model_documentation(model, schema)
    definitions = schema.get("$defs")
    if isinstance(definitions, dict):
        nested_models = _reachable_models(model)
        global_models = _global_model_registry()
        for definition_name, definition_schema in definitions.items():
            if not isinstance(definition_schema, dict):
                continue
            nested_model = (
                nested_models.get(str(definition_name))
                or nested_models.get(str(definition_schema.get("title")))
                or global_models.get(str(definition_name))
                or global_models.get(str(definition_schema.get("title")))
            )
            if nested_model is not None:
                _apply_model_documentation(nested_model, definition_schema)
    return schema


def _apply_model_documentation(model: type[BaseModel], schema: dict[str, Any]) -> None:
    """Inject model and field descriptions for one specific schema node."""

    if not schema.get("description"):
        docstring = inspect.getdoc(model)
        if docstring:
            schema["description"] = docstring
    documentation = contract_documentation_for(model)
    if documentation is not None:
        schema.setdefault("x-buildish-contract", documentation.as_schema_extension())
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for field_name, property_schema in properties.items():
            if not isinstance(property_schema, dict) or property_schema.get("description"):
                continue
            description = field_description_for(model, str(field_name))
            if description is not None:
                property_schema["description"] = description


def _reachable_models(root_model: type[BaseModel]) -> dict[str, type[BaseModel]]:
    """Return nested Buildish models reachable from one root model annotation graph."""

    discovered: dict[str, type[BaseModel]] = {}
    visited: set[type[BaseModel]] = set()

    def visit_model(model: type[BaseModel]) -> None:
        if model in visited:
            return
        visited.add(model)
        discovered.setdefault(model.__name__, model)
        discovered.setdefault(str(getattr(model, "__name__", "")), model)
        for field_info in model.model_fields.values():
            visit_annotation(field_info.annotation)

    def visit_annotation(annotation: Any) -> None:
        origin = get_origin(annotation)
        if origin is None:
            if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
                visit_model(annotation)
            return
        for argument in get_args(annotation):
            if argument is None or argument is type(None):
                continue
            visit_annotation(argument)

    visit_model(root_model)
    return discovered


@lru_cache(maxsize=1)
def _global_model_registry() -> dict[str, type[BaseModel]]:
    """Return a deterministic model-name registry for schema doc enrichment."""

    registry: dict[str, type[BaseModel]] = {}
    for package_name in _MODEL_REGISTRY_PACKAGE_NAMES:
        package = importlib.import_module(package_name)
        for module_name in (package.__name__, *_walk_module_names(package)):
            module = importlib.import_module(module_name)
            for candidate in vars(module).values():
                if (
                    inspect.isclass(candidate)
                    and issubclass(candidate, BaseModel)
                    and candidate.__module__ == module.__name__
                ):
                    registry.setdefault(candidate.__name__, candidate)
                    registry.setdefault(str(getattr(candidate, "__name__", "")), candidate)
    return registry


def _walk_module_names(package: Any) -> tuple[str, ...]:
    package_path = getattr(package, "__path__", None)
    if package_path is None:
        return ()
    return tuple(
        module_info.name
        for module_info in pkgutil.walk_packages(package_path, package.__name__ + ".")
    )
