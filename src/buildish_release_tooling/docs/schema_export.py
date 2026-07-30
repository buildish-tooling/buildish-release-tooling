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

"""Generate checked-in JSON Schema files and reference docs for release-tooling contracts."""

from __future__ import annotations

import argparse
import importlib
import json
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass
from inspect import cleandoc
from pathlib import Path
import re
import sys
from typing import Any

from buildish_release_tooling.docs.documentation import (
    ContractDocumentation,
    DocumentedContractModel,
    ReferenceGroup,
    SchemaAudience,
    SchemaExample,
    SchemaExportSpecification,
    SchemaStability,
    contract_documentation_for,
    schema_export_spec_for,
)

_JSON_SCHEMA_DRAFT_202012 = "https://json-schema.org/draft/2020-12/schema"
_PUBLISHED_SCHEMA_BASE_URL = (
    "https://buildish.org/components/release-tooling/schemas"
)
_GENERATED_COMMENT = (
    "Generated from the Buildish Release Tooling Pydantic models. "
    "Do not edit by hand; regenerate with `make schemas`."
)
_EXPORT_PACKAGE_NAMES = (
    "buildish_release_tooling.release",
    "buildish_release_tooling.harness",
)

SchemaBuilder = Callable[[], dict[str, Any]]


@dataclass(frozen=True)
class SchemaExport:
    """One checked-in JSON Schema export for a Buildish-owned contract root."""

    filename: str
    title: str
    schema_builder: SchemaBuilder
    description: str | None = None
    documentation: ContractDocumentation | None = None
    reference_roots: tuple[type[DocumentedContractModel], ...] = ()
    examples: tuple[SchemaExample, ...] = ()
    audience: SchemaAudience = "supported"
    stability: SchemaStability = "stable"
    reference_group: ReferenceGroup = "supported-emitted-root"


def _model_schema(model: type[DocumentedContractModel]) -> SchemaBuilder:
    def build() -> dict[str, Any]:
        return model.model_json_schema(by_alias=True)

    return build


def _first_sentence(value: str) -> str:
    sentence_match = re.match(r"^(.+?[.!?])(?:\s|$)", value)
    return sentence_match.group(1) if sentence_match is not None else value


def _docstring_for_model(model: type[DocumentedContractModel]) -> str:
    docstring = cleandoc(model.__doc__ or "")
    if not docstring:
        raise ValueError(
            f"Exported schema root is missing a docstring: {model.__module__}.{model.__name__}"
        )
    return docstring


def _documentation_for_export(
    model: type[DocumentedContractModel],
    specification: SchemaExportSpecification,
) -> ContractDocumentation:
    base = contract_documentation_for(model)
    if base is None:
        raise ValueError(
            f"Exported schema root is missing contract documentation: {model.__module__}.{model.__name__}"
        )
    return ContractDocumentation(
        category=base.category,
        ownership=base.ownership,
        summary=specification.summary or base.summary or _first_sentence(_docstring_for_model(model)),
        file_path=specification.file_path if specification.file_path is not None else base.file_path,
        reference=base.reference,
    )


def _default_reference_group(
    *,
    audience: SchemaAudience,
    stability: SchemaStability,
    documentation: ContractDocumentation,
) -> ReferenceGroup:
    if stability == "unstable":
        return "internal-unstable-root"
    if audience == "supported":
        if documentation.file_path is not None and documentation.category == "authored":
            return "supported-authored-file"
        if documentation.file_path is not None:
            return "supported-emitted-file"
        return "supported-emitted-root"
    if documentation.file_path is not None:
        return "internal-stable-file"
    return "internal-stable-root"


def _schema_export_from_model(model: type[DocumentedContractModel]) -> SchemaExport:
    specification = _required_schema_export_spec(model)
    documentation = _documentation_for_export(model, specification)
    return SchemaExport(
        filename=specification.filename,
        title=f"Buildish Release Tooling {model.__name__}",
        schema_builder=_model_schema(model),
        description=specification.description or _docstring_for_model(model),
        documentation=documentation,
        reference_roots=(model,),
        examples=specification.examples,
        audience=specification.audience,
        stability=specification.stability,
        reference_group=specification.reference_group
        or _default_reference_group(
            audience=specification.audience,
            stability=specification.stability,
            documentation=documentation,
        ),
    )


def _required_schema_export_spec(
    model: type[DocumentedContractModel],
) -> SchemaExportSpecification:
    specification = schema_export_spec_for(model)
    if specification is None:
        raise ValueError(
            f"Missing schema export specification for {model.__module__}.{model.__name__}"
        )
    return specification


def _iter_export_models() -> tuple[type[DocumentedContractModel], ...]:
    discovered: dict[str, type[DocumentedContractModel]] = {}
    for package_name in _EXPORT_PACKAGE_NAMES:
        package = importlib.import_module(package_name)
        for module_name in (package.__name__, *_walk_module_names(package)):
            module = importlib.import_module(module_name)
            for candidate in vars(module).values():
                if (
                    isinstance(candidate, type)
                    and issubclass(candidate, DocumentedContractModel)
                    and candidate.__module__ == module.__name__
                    and schema_export_spec_for(candidate) is not None
                ):
                    discovered[f"{candidate.__module__}:{candidate.__name__}"] = candidate
    return tuple(
        sorted(
            discovered.values(),
            key=lambda model: (
                _required_schema_export_spec(model).filename,
                model.__module__,
                model.__name__,
            ),
        )
    )


def _walk_module_names(package: Any) -> tuple[str, ...]:
    package_path = getattr(package, "__path__", None)
    if package_path is None:
        return ()
    return tuple(
        module_info.name
        for module_info in pkgutil.walk_packages(package_path, package.__name__ + ".")
    )


_SCHEMA_EXPORTS = tuple(
    _schema_export_from_model(model)
    for model in _iter_export_models()
)


def schema_exports() -> tuple[SchemaExport, ...]:
    """Return the checked-in schema exports for release-tooling contract roots."""

    return _SCHEMA_EXPORTS


def authored_schema_exports() -> tuple[SchemaExport, ...]:
    """Return authored schema exports kept for local YAML authoring and validation."""

    return tuple(
        export
        for export in _SCHEMA_EXPORTS
        if export.reference_group in {"supported-authored-file", "internal-stable-file"}
        and export.documentation is not None
        and export.documentation.category == "authored"
    )


def build_schema_document(export: SchemaExport) -> dict[str, Any]:
    """Build one finalized JSON Schema document for a release-tooling contract root."""

    schema = export.schema_builder()
    schema["$schema"] = _JSON_SCHEMA_DRAFT_202012
    schema["$id"] = f"{_PUBLISHED_SCHEMA_BASE_URL}/{export.filename}"
    schema["$comment"] = _GENERATED_COMMENT
    schema["title"] = export.title
    if export.description is not None:
        schema["description"] = export.description
    if export.documentation is not None:
        schema["x-buildish-contract"] = export.documentation.as_schema_extension()
    if export.examples:
        schema["examples"] = [
            _serialize_example_value(example.value_builder()) for example in export.examples
        ]
    return schema


def write_schema_files(output_dir: Path) -> tuple[Path, ...]:
    """Write the checked-in JSON Schema files to ``output_dir``."""

    output_dir.mkdir(parents=True, exist_ok=True)
    written_paths: list[Path] = []
    for export in schema_exports():
        output_path = output_dir / export.filename
        output_path.write_text(
            json.dumps(build_schema_document(export), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written_paths.append(output_path)
    return tuple(written_paths)


def write_authored_schema_files(output_dir: Path) -> tuple[Path, ...]:
    """Backward-compatible alias for the full release-tooling schema export set."""

    return write_schema_files(output_dir)


def write_reference_files(output_dir: Path) -> tuple[Path, ...]:
    """Write the generated Markdown schema reference page set."""

    from buildish_release_tooling.docs.reference_export import (
        write_reference_markdown_files,
    )

    return write_reference_markdown_files(output_dir, schema_exports())


def write_reference_file(output_path: Path) -> tuple[Path, ...]:
    """Backward-compatible alias that writes the full Markdown reference page set."""

    if output_path.name != "release-model-schema-reference.md":
        raise ValueError(
            "reference output path must be docs/reference/release-model-schema-reference.md or an equivalent filename"
        )
    return write_reference_files(output_path.parent)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m buildish_release_tooling.docs.schema_export"
    )
    parser.add_argument(
        "--output-dir",
        default="site/pages/schemas",
        help="Directory that should receive the generated JSON Schema files.",
    )
    parser.add_argument(
        "--reference-dir",
        default="docs/reference",
        help="Directory that should receive the generated Markdown schema reference pages.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Generate the checked-in JSON Schema files and Markdown reference docs."""

    args = _build_parser().parse_args(argv)
    for output_path in write_schema_files(Path(args.output_dir)):
        sys.stdout.write(output_path.as_posix())  # noqa: TID251
        sys.stdout.write("\n")  # noqa: TID251
    for reference_path in write_reference_files(Path(args.reference_dir)):
        sys.stdout.write(reference_path.as_posix())  # noqa: TID251
        sys.stdout.write("\n")  # noqa: TID251
    return 0


def _serialize_example_value(value: object) -> object:
    """Convert typed example payloads into JSON-serializable data."""

    if isinstance(value, DocumentedContractModel):
        return value.model_dump(by_alias=True, exclude_none=True, mode="json")
    if isinstance(value, tuple):
        return [_serialize_example_value(item) for item in value]
    if isinstance(value, list):
        return [_serialize_example_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_example_value(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"Unsupported schema example payload type: {type(value)!r}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
