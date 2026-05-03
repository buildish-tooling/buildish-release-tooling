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

"""Generate the checked-in Markdown reference for release-tooling models."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from inspect import cleandoc
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any, get_args, get_origin

import yaml

from apache_buildish_release_tooling.docs.documentation import (
    DocumentedContractModel,
    contract_documentation_for,
)
from apache_buildish_release_tooling.docs.reference_docs import (
    ReferenceDocError,
    TypeReferenceTarget,
    parse_reference_document,
    render_reference_markdown,
    render_reference_schema_text,
)
from apache_buildish_release_tooling.docs.reference_docs.registry import (
    MODEL_SECTION_DEFINITIONS,
    SCALAR_REFERENCE_ENTRIES,
    ModelSectionDefinition,
    ScalarReferenceEntry,
)

if TYPE_CHECKING:
    from apache_buildish_release_tooling.docs.schema_export import SchemaExample, SchemaExport

_GENERATED_REFERENCE_COMMENT = (
    "This reference is generated from the Buildish Release Tooling Pydantic models and checked-in "
    "reference metadata. Do not edit it by hand; regenerate it with `make schemas`."
)
_PUBLISHED_SCHEMA_PATH_PREFIX = "/components/buildish-release-tooling/schemas"
_TOKEN_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_INNER_TYPE_PLACEHOLDER = "(inner type)"
_NOT_DOCUMENTED_PLACEHOLDER = "(not documented)"
_TYPE_SUMMARY_WARNING = (
    "**UX warning:** type summary missing; this violates the project's UX requirements."
)
_FIELD_DESCRIPTION_WARNING = (
    "**UX warning:** field description missing; this violates the project's UX requirements. "
    f"{_NOT_DOCUMENTED_PLACEHOLDER}"
)


@dataclass(frozen=True, slots=True)
class AnchorIndex:
    """Stable generated anchors for types, scalars, enums, and fields."""

    type_anchors: dict[str, str]
    field_anchors: dict[tuple[str, str], str]

    def resolve_type_target(self, target: TypeReferenceTarget) -> str:
        type_anchor = self.type_anchors.get(target.type_name)
        if type_anchor is None:
            raise ReferenceDocError(
                f"Unknown generated reference type target: {target.type_name!r}"
            )
        if target.field_name is None:
            return f"#{type_anchor}"
        field_anchor = self.field_anchors.get((target.type_name, target.field_name))
        if field_anchor is None:
            raise ReferenceDocError(
                f"Unknown generated reference field target: {target.type_name}#{target.field_name}",
            )
        return f"#{field_anchor}"

    def link_type_expression(self, expression: str) -> str:
        return _TOKEN_PATTERN.sub(self._replace_type_token, expression)

    def _replace_type_token(self, match: re.Match[str]) -> str:
        token = match.group(0)
        anchor = self.type_anchors.get(token)
        return token if anchor is None else f"[{token}](#{anchor})"


@dataclass(frozen=True, slots=True)
class FileContractIndexGroup:
    """One rendered grouping for the file-contract index."""

    title: str
    description: str
    export_group: str
    has_contract_file: bool


def build_reference_markdown(exports: Iterable[SchemaExport]) -> str:
    """Build the generated Markdown schema reference from release-tooling model metadata."""

    export_list = tuple(exports)
    reachable_models = _collect_reachable_models(export_list)
    reachable_enums = _collect_reachable_enums(reachable_models)
    anchors = _build_anchor_index(reachable_models, reachable_enums, SCALAR_REFERENCE_ENTRIES)
    examples_by_root = _examples_by_root_model(export_list)
    exports_by_root = _exports_by_root_model(export_list)

    lines = [
        "---",
        'title: "Release model schema reference"',
        f'description: "{_GENERATED_REFERENCE_COMMENT}"',
        "weight: 30",
        "---",
        "",
        "<!--",
        "Copyright 2026 The Apache Software Foundation",
        "",
        'Licensed under the Apache License, Version 2.0 (the "License");',
        "you may not use this file except in compliance with the License.",
        "You may obtain a copy of the License at",
        "",
        "http://www.apache.org/licenses/LICENSE-2.0",
        "",
        "Unless required by applicable law or agreed to in writing, software",
        'distributed under the License is distributed on an "AS IS" BASIS,',
        "WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.",
        "See the License for the specific language governing permissions and",
        "limitations under the License.",
        "-->",
        "",
        "This reference describes the typed Buildish Release Tooling contracts that are checked into this repository.",
        "It covers supported external configuration and verification/report contracts, plus internal runtime contracts and internal unstable command action manifests.",
        "Use the contract-file tables to find the governing file or schema root, then follow the linked type sections below for exact field-level structure.",
        "",
        "## How to read this reference",
        "",
        "- contract-file tables identify stable checked-in file contracts where one exists",
        "- `audience` distinguishes supported external contracts from Buildish-owned internal contracts",
        "- `stability` distinguishes stable supported/internal contracts from intentionally unstable internal machine I/O",
        "- field names are shown in their wire-format aliases",
        "- type, enum, and alias names link to their definitions below",
        "- schema files link to the published JSON Schema contract for the matching root type",
        "",
    ]
    lines.extend(_render_file_contract_index(export_list, anchors))
    lines.extend(_render_scalar_section())
    lines.extend(_render_enum_section(reachable_enums, anchors))
    lines.extend(_render_model_index(reachable_models, anchors))
    lines.extend(_render_model_sections(reachable_models, anchors, examples_by_root, exports_by_root))
    return "\n".join(lines) + "\n"


def write_reference_markdown_file(output_path: Path, exports: Iterable[SchemaExport]) -> Path:
    """Write the generated Markdown model reference to ``output_path``."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_reference_markdown(exports), encoding="utf-8")
    return output_path


def _collect_reachable_models(
    exports: tuple[SchemaExport, ...],
) -> tuple[type[DocumentedContractModel], ...]:
    seen: set[type[DocumentedContractModel]] = set()

    def collect(model: type[DocumentedContractModel]) -> None:
        if model in seen:
            return
        seen.add(model)
        for field in model.model_fields.values():
            _walk_annotation(field.annotation, collect_model=collect, collect_enum=lambda _: None)

    for export in exports:
        for root in export.reference_roots:
            collect(root)
    return tuple(sorted(seen, key=lambda model: (model.__module__, model.__name__)))


def _collect_reachable_enums(
    models: tuple[type[DocumentedContractModel], ...],
) -> tuple[type[Enum], ...]:
    seen: set[type[Enum]] = set()
    for model in models:
        for field in model.model_fields.values():
            _walk_annotation(field.annotation, collect_model=lambda _: None, collect_enum=seen.add)
    return tuple(sorted(seen, key=lambda enum_type: enum_type.__name__))


def _walk_annotation(
    annotation: Any,
    *,
    collect_model: Callable[[type[DocumentedContractModel]], None],
    collect_enum: Callable[[type[Enum]], None],
) -> None:
    origin = get_origin(annotation)
    if origin is None:
        if isinstance(annotation, type):
            if issubclass(annotation, DocumentedContractModel):
                collect_model(annotation)
            elif issubclass(annotation, Enum):
                collect_enum(annotation)
        return
    for argument in get_args(annotation):
        if argument is type(None):
            continue
        _walk_annotation(argument, collect_model=collect_model, collect_enum=collect_enum)


def _build_anchor_index(
    models: tuple[type[DocumentedContractModel], ...],
    enums: tuple[type[Enum], ...],
    scalar_entries: tuple[ScalarReferenceEntry, ...],
) -> AnchorIndex:
    type_anchors: dict[str, str] = {}
    field_anchors: dict[tuple[str, str], str] = {}
    for scalar in scalar_entries:
        type_anchors[scalar.name] = _slugify_anchor(scalar.name)
    for enum_type in enums:
        type_anchors[enum_type.__name__] = _slugify_anchor(enum_type.__name__)
    for model in models:
        type_anchors[model.__name__] = _slugify_anchor(model.__name__)
        for field_name, field in model.model_fields.items():
            alias = field.alias or field_name
            anchor = f"{type_anchors[model.__name__]}-{_slugify_anchor(alias)}"
            field_anchors[(model.__name__, alias)] = anchor
            field_anchors[(model.__name__, field_name)] = anchor
    return AnchorIndex(type_anchors=type_anchors, field_anchors=field_anchors)


def _slugify_anchor(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _render_file_contract_index(
    exports: tuple[SchemaExport, ...],
    anchors: AnchorIndex,
) -> list[str]:
    lines = ["## File contract index", ""]
    for group in _file_contract_index_groups():
        grouped_exports = tuple(
            sorted(
                (export for export in exports if export.reference_group == group.export_group),
                key=_file_contract_sort_key,
            )
        )
        if not grouped_exports:
            continue
        lines.append(f"### {group.title}")
        lines.append("")
        lines.append(group.description)
        lines.append("")
        if group.has_contract_file:
            lines.extend(
                [
                    "| Contract file | Root type(s) | Schema file | Audience | Stability | Summary |",
                    "| --- | --- | --- | --- | --- | --- |",
                ]
            )
            for export in grouped_exports:
                lines.append(
                    f"| `{_contract_file_path(export)}` | {_render_root_types(export, anchors)} | {_render_schema_file_link(export)} | `{export.audience}` | `{export.stability}` | {_escape_table_cell(_export_summary(export))} |"
                )
        else:
            lines.extend(
                [
                    "| Root type(s) | Schema file | Audience | Stability | Summary |",
                    "| --- | --- | --- | --- | --- |",
                ]
            )
            for export in grouped_exports:
                lines.append(
                    f"| {_render_root_types(export, anchors)} | {_render_schema_file_link(export)} | `{export.audience}` | `{export.stability}` | {_escape_table_cell(_export_summary(export))} |"
                )
        lines.append("")
    return lines


def _render_scalar_section() -> list[str]:
    lines = [
        "## Shared aliases and literal sets",
        "",
        "| Type | Base type | Description |",
        "| --- | --- | --- |",
    ]
    for entry in SCALAR_REFERENCE_ENTRIES:
        anchor = _slugify_anchor(entry.name)
        lines.append(
            f"| <a id=\"{anchor}\"></a>`{entry.name}` | `{entry.base_type}` | {_escape_table_cell(entry.description)} |"
        )
    lines.extend(["", ""])
    return lines


def _render_enum_section(
    enums: tuple[type[Enum], ...],
    anchors: AnchorIndex,
) -> list[str]:
    if not enums:
        return []
    lines = [
        "## Shared enums",
        "",
        "| Type | Values | Description |",
        "| --- | --- | --- |",
    ]
    for enum_type in enums:
        anchor = anchors.type_anchors[enum_type.__name__]
        values = ", ".join(f"`{member.value}`" for member in enum_type)
        description = cleandoc(enum_type.__doc__ or _NOT_DOCUMENTED_PLACEHOLDER)
        lines.append(
            f"| <a id=\"{anchor}\"></a>`{enum_type.__name__}` | {values} | {_escape_table_cell(description)} |"
        )
    lines.extend(["", ""])
    return lines


def _render_model_index(
    models: tuple[type[DocumentedContractModel], ...],
    anchors: AnchorIndex,
) -> list[str]:
    lines = ["## Type index", ""]
    grouped = _group_models(models)
    for definition, grouped_models in grouped:
        lines.append(f"### {definition.title}")
        lines.append("")
        lines.append(definition.description)
        lines.append("")
        for model in grouped_models:
            lines.append(
                f"- [{model.__name__}](#{anchors.type_anchors[model.__name__]}) — {_model_index_summary(model)}"
            )
        lines.append("")
    return lines


def _render_model_sections(
    models: tuple[type[DocumentedContractModel], ...],
    anchors: AnchorIndex,
    examples_by_root: dict[type[DocumentedContractModel], tuple[SchemaExample, ...]],
    exports_by_root: dict[type[DocumentedContractModel], tuple[SchemaExport, ...]],
) -> list[str]:
    lines: list[str] = []
    for definition, grouped_models in _group_models(models):
        lines.append(f"## {definition.title}")
        lines.append("")
        lines.append(definition.description)
        lines.append("")
        for model in grouped_models:
            lines.extend(
                _render_model_section(
                    model,
                    anchors,
                    examples_by_root.get(model, ()),
                    exports_by_root.get(model, ()),
                )
            )
    return lines


def _render_model_section(
    model: type[DocumentedContractModel],
    anchors: AnchorIndex,
    examples: tuple[SchemaExample, ...],
    root_exports: tuple[SchemaExport, ...],
) -> list[str]:
    documentation = contract_documentation_for(model)
    lines = [
        f"<a id=\"{anchors.type_anchors[model.__name__]}\"></a>",
        f"### {model.__name__}",
        "",
    ]
    summary_source = _model_summary_source(model)
    if summary_source is None:
        lines.extend([_TYPE_SUMMARY_WARNING, "", _NOT_DOCUMENTED_PLACEHOLDER, ""])
    else:
        lines.extend([_render_markdown_fragment(summary_source, anchors), ""])
    if documentation is not None:
        lines.extend(
            [
                f"- category: `{documentation.category}`",
                f"- ownership: `{documentation.ownership}`",
            ]
        )
    if root_exports:
        for export in root_exports:
            lines.extend(
                [
                    f"- schema file: {_render_schema_file_link(export)}",
                    f"- audience: `{export.audience}`",
                    f"- stability: `{export.stability}`",
                    f"- file contract: `{export.documentation.file_path}`"
                    if export.documentation is not None and export.documentation.file_path is not None
                    else f"- file contract: {_INNER_TYPE_PLACEHOLDER}",
                ]
            )
    elif documentation is not None:
        lines.append(f"- file contract: {_INNER_TYPE_PLACEHOLDER}")
    if documentation is not None or root_exports:
        lines.append("")
    lines.extend(
        [
            "| Field | Type | Required | Description |",
            "| --- | --- | --- | --- |",
        ]
    )
    for field_name, field in model.model_fields.items():
        alias = field.alias or field_name
        field_anchor = anchors.field_anchors[(model.__name__, alias)]
        rendered_type = _render_field_type_expression(model, field_name, field.is_required(), anchors)
        description = _render_field_description(field.description, anchors)
        lines.append(
            f"| <a id=\"{field_anchor}\"></a>`{alias}` | {_escape_table_cell(rendered_type)} | {'yes' if field.is_required() else 'no'} | {_escape_table_cell(description)} |"
        )
    lines.append("")
    field_example_lines = _render_field_examples_section(model)
    if field_example_lines:
        lines.extend(field_example_lines)
    if documentation is not None and documentation.reference is not None:
        for section in documentation.reference.sections:
            lines.append(f"#### {section.title}")
            lines.append("")
            lines.append(_render_markdown_fragment(section.body.source, anchors))
            lines.append("")
    for example in examples:
        lines.append(f"#### Example: {example.summary}")
        lines.append("")
        lines.append(_render_example_block(example))
        lines.append("")
    return lines


def _render_markdown_fragment(source: str, anchors: AnchorIndex) -> str:
    try:
        return render_reference_markdown(
            parse_reference_document(cleandoc(source)),
            resolve_type_target=anchors.resolve_type_target,
        )
    except ReferenceDocError as error:
        raise ReferenceDocError(
            f"Failed to render generated reference fragment {source!r}: {error}"
        ) from error


def _render_example_block(example: SchemaExample) -> str:
    data = _serialize_example_value(example.value_builder())
    if example.render_format == "yaml":
        rendered = yaml.safe_dump(data, sort_keys=False).rstrip()
    else:
        import json

        rendered = json.dumps(data, indent=2, sort_keys=False)
    return f"```{example.render_format}\n{rendered}\n```"


def _render_field_examples_section(model: type[DocumentedContractModel]) -> list[str]:
    entries: list[str] = []
    for field_name, field in model.model_fields.items():
        if not field.examples:
            continue
        alias = field.alias or field_name
        rendered_examples = ", ".join(_render_inline_example_value(value) for value in field.examples)
        label = "Example" if len(field.examples) == 1 else "Examples"
        entries.append(f"- `{alias}`: {label}: {rendered_examples}")
    if not entries:
        return []
    return ["#### Selected field examples", "", *entries, ""]


def _render_inline_example_value(value: Any) -> str:
    import json

    serialized = json.dumps(_serialize_example_value(value), separators=(",", ": "), sort_keys=False)
    return f"`{serialized}`"


def _examples_by_root_model(
    exports: tuple[SchemaExport, ...],
) -> dict[type[DocumentedContractModel], tuple[SchemaExample, ...]]:
    examples: dict[type[DocumentedContractModel], tuple[SchemaExample, ...]] = {}
    for export in exports:
        if not export.examples or len(export.reference_roots) != 1:
            continue
        examples[export.reference_roots[0]] = export.examples
    return examples


def _exports_by_root_model(
    exports: tuple[SchemaExport, ...],
) -> dict[type[DocumentedContractModel], tuple[SchemaExport, ...]]:
    grouped: dict[type[DocumentedContractModel], list[SchemaExport]] = {}
    for export in exports:
        for root in export.reference_roots:
            grouped.setdefault(root, []).append(export)
    return {
        root: tuple(sorted(root_exports, key=lambda export: export.filename))
        for root, root_exports in grouped.items()
    }


def _group_models(
    models: tuple[type[DocumentedContractModel], ...],
) -> tuple[tuple[ModelSectionDefinition, tuple[type[DocumentedContractModel], ...]], ...]:
    grouped: list[tuple[ModelSectionDefinition, tuple[type[DocumentedContractModel], ...]]] = []
    matched_models: set[type[DocumentedContractModel]] = set()
    for definition in MODEL_SECTION_DEFINITIONS:
        members = tuple(
            sorted(
                (model for model in models if definition.matches(model.__module__)),
                key=lambda model: model.__name__,
            )
        )
        if members:
            grouped.append((definition, members))
            matched_models.update(members)
    unmatched = sorted(model.__name__ for model in models if model not in matched_models)
    if unmatched:
        raise ReferenceDocError(
            f"Unmatched release-tooling reference model modules: {', '.join(unmatched)}"
        )
    return tuple(grouped)


def _escape_table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def _file_contract_index_groups() -> tuple[FileContractIndexGroup, ...]:
    return (
        FileContractIndexGroup(
            title="Supported authored file contracts",
            description=(
                "Consumer-authored or component-authored file contracts that are part of the supported external release-tooling surface."
            ),
            export_group="supported-authored-file",
            has_contract_file=True,
        ),
        FileContractIndexGroup(
            title="Supported emitted file contracts",
            description=(
                "Stable emitted Buildish file contracts that workflows or humans may intentionally consume."
            ),
            export_group="supported-emitted-file",
            has_contract_file=True,
        ),
        FileContractIndexGroup(
            title="Supported emitted non-file root contracts",
            description=(
                "Supported emitted JSON contract roots that do not correspond to one fixed checked-in path."
            ),
            export_group="supported-emitted-root",
            has_contract_file=False,
        ),
        FileContractIndexGroup(
            title="Internal stable file contracts",
            description=(
                "Buildish-owned internal file contracts that are documented here for maintainability but are not part of the supported external API."
            ),
            export_group="internal-stable-file",
            has_contract_file=True,
        ),
        FileContractIndexGroup(
            title="Internal stable non-file root contracts",
            description=(
                "Buildish-owned internal root contracts and runtime payloads with stable current semantics but no external support promise."
            ),
            export_group="internal-stable-root",
            has_contract_file=False,
        ),
        FileContractIndexGroup(
            title="Internal unstable command action manifests",
            description=(
                "Internal workflow-coordination manifests written by commands. These are documented to aid maintenance and debugging, but they are intentionally unstable."
            ),
            export_group="internal-unstable-root",
            has_contract_file=False,
        ),
    )


def _file_contract_sort_key(export: SchemaExport) -> tuple[int, str, str]:
    documentation = export.documentation
    contract_file = (
        documentation.file_path if documentation is not None and documentation.file_path is not None else ""
    )
    return (0 if contract_file else 1, export.audience, export.title)


def _contract_file_path(export: SchemaExport) -> str:
    documentation = export.documentation
    if documentation is None or documentation.file_path is None:
        return _INNER_TYPE_PLACEHOLDER
    return documentation.file_path


def _render_root_types(export: SchemaExport, anchors: AnchorIndex) -> str:
    return ", ".join(
        f"[{root.__name__}](#{anchors.type_anchors[root.__name__]})"
        for root in export.reference_roots
    ) or "—"


def _export_summary(export: SchemaExport) -> str:
    documentation = export.documentation
    if documentation is not None and documentation.summary is not None:
        return documentation.summary
    return export.description or _NOT_DOCUMENTED_PLACEHOLDER


def _render_schema_file_link(export: SchemaExport) -> str:
    schema_path = f"{_PUBLISHED_SCHEMA_PATH_PREFIX}/{export.filename}"
    return f"[`{export.filename}`]({schema_path})"


def _model_index_summary(model: type[DocumentedContractModel]) -> str:
    summary_text = _model_summary_text(model)
    return _first_sentence(summary_text) if summary_text is not None else _NOT_DOCUMENTED_PLACEHOLDER


def _model_summary_source(model: type[DocumentedContractModel]) -> str | None:
    documentation = contract_documentation_for(model)
    if (
        documentation is not None
        and documentation.reference is not None
        and documentation.reference.summary is not None
    ):
        return documentation.reference.summary.source
    model_doc = cleandoc(model.__doc__) if model.__doc__ else None
    return model_doc if model_doc else None


def _model_summary_text(model: type[DocumentedContractModel]) -> str | None:
    summary_source = _model_summary_source(model)
    if summary_source is None:
        return None
    documentation = contract_documentation_for(model)
    if (
        documentation is not None
        and documentation.reference is not None
        and documentation.reference.summary is not None
    ):
        return _normalize_summary_text(
            render_reference_schema_text(parse_reference_document(cleandoc(summary_source)))
        )
    return _normalize_summary_text(summary_source)


def _render_field_type_expression(
    model: type[DocumentedContractModel],
    field_name: str,
    required: bool,
    anchors: AnchorIndex,
) -> str:
    raw_type = model.__annotations__.get(field_name)
    type_expression = str(raw_type) if raw_type is not None else "object"
    if not required:
        type_expression = _strip_top_level_optional_none(type_expression)
    return anchors.link_type_expression(type_expression)


def _render_field_description(description: str | None, anchors: AnchorIndex) -> str:
    if description is None or not description.strip():
        return _FIELD_DESCRIPTION_WARNING
    return _render_markdown_fragment(description, anchors)


def _strip_top_level_optional_none(type_expression: str) -> str:
    stripped = type_expression.strip()
    for prefix in ("Optional[", "typing.Optional["):
        if stripped.startswith(prefix) and stripped.endswith("]"):
            return stripped[len(prefix) : -1]
    union_prefixes = ("Union[", "typing.Union[")
    for prefix in union_prefixes:
        if stripped.startswith(prefix) and stripped.endswith("]"):
            union_members = _split_top_level_values(stripped[len(prefix) : -1], separator=",")
            non_none_members = [member.strip() for member in union_members if member.strip() != "None"]
            if len(non_none_members) != len(union_members) and non_none_members:
                return f"{prefix}{', '.join(non_none_members)}]"
            return stripped
    union_members = _split_top_level_values(stripped, separator="|")
    non_none_members = [member.strip() for member in union_members if member.strip() != "None"]
    if len(non_none_members) != len(union_members) and non_none_members:
        return " | ".join(non_none_members)
    return stripped


def _split_top_level_values(source: str, *, separator: str) -> tuple[str, ...]:
    values: list[str] = []
    current: list[str] = []
    square_depth = 0
    round_depth = 0
    brace_depth = 0
    for character in source:
        if character == "[":
            square_depth += 1
        elif character == "]":
            square_depth -= 1
        elif character == "(":
            round_depth += 1
        elif character == ")":
            round_depth -= 1
        elif character == "{":
            brace_depth += 1
        elif character == "}":
            brace_depth -= 1
        if character == separator and square_depth == 0 and round_depth == 0 and brace_depth == 0:
            values.append("".join(current))
            current = []
            continue
        current.append(character)
    values.append("".join(current))
    return tuple(values)


def _first_sentence(value: str) -> str:
    sentence_match = re.match(r"^(.+?[.!?])(?:\s|$)", value)
    return sentence_match.group(1) if sentence_match is not None else value


def _normalize_summary_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _serialize_example_value(value: object) -> object:
    """Convert typed example payloads into JSON/YAML-serializable data."""

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
    raise TypeError(f"Unsupported reference example payload type: {type(value)!r}")
