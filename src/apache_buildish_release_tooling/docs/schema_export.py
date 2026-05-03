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

"""Generate checked-in JSON Schema files and reference docs for release-tooling contracts."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from inspect import cleandoc
from pathlib import Path
import re
import sys
from typing import Any, Literal

from apache_buildish_release_tooling.docs.documentation import (
    ContractDocumentation,
    DocumentedContractModel,
    contract_documentation_for,
)
from apache_buildish_release_tooling.harness import config as harness_config_models
from apache_buildish_release_tooling.harness import models as harness_models
from apache_buildish_release_tooling.harness import shim_builtins as harness_shim_models
from apache_buildish_release_tooling.release import command_manifests as release_command_manifests
from apache_buildish_release_tooling.release import contracts as release_contracts
from apache_buildish_release_tooling.release import models as release_models

_JSON_SCHEMA_DRAFT_202012 = "https://json-schema.org/draft/2020-12/schema"
_PUBLISHED_SCHEMA_BASE_URL = (
    "https://buildish.apache.org/components/buildish-release-tooling/schemas"
)
_GENERATED_COMMENT = (
    "Generated from the Buildish Release Tooling Pydantic models. "
    "Do not edit by hand; regenerate with `make schemas`."
)
_CAMEL_TO_KEBAB_PATTERN = re.compile(r"(?<!^)(?=[A-Z])")

SchemaBuilder = Callable[[], dict[str, Any]]
ExampleValueBuilder = Callable[[], object]
ExampleRenderFormat = Literal["json", "yaml"]
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


@dataclass(frozen=True)
class SchemaExample:
    """One generated example shared by schema files and reference docs."""

    summary: str
    value_builder: ExampleValueBuilder
    render_format: ExampleRenderFormat = "json"


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


@dataclass(frozen=True)
class RootModelExportSpec:
    """Inventory specification for one exported release-tooling root model."""

    model: type[DocumentedContractModel]
    audience: SchemaAudience
    stability: SchemaStability
    file_path: str | None = None
    summary: str | None = None
    description: str | None = None
    reference_group: ReferenceGroup | None = None


def _model_schema(model: type[DocumentedContractModel]) -> SchemaBuilder:
    def build() -> dict[str, Any]:
        return model.model_json_schema(by_alias=True)

    return build


def _schema_filename_for_model(model: type[DocumentedContractModel]) -> str:
    return f"buildish-release-tooling-{_kebab_case(model.__name__)}.schema.json"


def _kebab_case(value: str) -> str:
    return _CAMEL_TO_KEBAB_PATTERN.sub("-", value).replace("_", "-").lower()


def _first_sentence(value: str) -> str:
    sentence_match = re.match(r"^(.+?[.!?])(?:\s|$)", value)
    return sentence_match.group(1) if sentence_match is not None else value


def _docstring_for_model(model: type[DocumentedContractModel]) -> str:
    docstring = cleandoc(model.__doc__ or "")
    if not docstring:
        raise ValueError(f"Exported schema root is missing a docstring: {model.__module__}.{model.__name__}")
    return docstring


def _documentation_for_export(
    model: type[DocumentedContractModel],
    *,
    summary: str | None = None,
    file_path: str | None = None,
) -> ContractDocumentation:
    base = contract_documentation_for(model)
    if base is None:
        raise ValueError(
            f"Exported schema root is missing contract documentation: {model.__module__}.{model.__name__}"
        )
    return ContractDocumentation(
        category=base.category,
        ownership=base.ownership,
        summary=summary or base.summary or _first_sentence(_docstring_for_model(model)),
        file_path=file_path if file_path is not None else base.file_path,
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


def _schema_export_from_spec(spec: RootModelExportSpec) -> SchemaExport:
    description = spec.description or _docstring_for_model(spec.model)
    documentation = _documentation_for_export(
        spec.model,
        summary=spec.summary,
        file_path=spec.file_path,
    )
    return SchemaExport(
        filename=_schema_filename_for_model(spec.model),
        title=f"Buildish Release Tooling {spec.model.__name__}",
        schema_builder=_model_schema(spec.model),
        description=description,
        documentation=documentation,
        reference_roots=(spec.model,),
        audience=spec.audience,
        stability=spec.stability,
        reference_group=spec.reference_group
        or _default_reference_group(
            audience=spec.audience,
            stability=spec.stability,
            documentation=documentation,
        ),
    )


def _command_action_manifest_exports() -> tuple[SchemaExport, ...]:
    exports: list[SchemaExport] = []
    command_models = [
        candidate
        for candidate in vars(release_command_manifests).values()
        if isinstance(candidate, type)
        and issubclass(candidate, release_command_manifests.CommandActionManifest)
        and candidate.__module__ == release_command_manifests.__name__
    ]
    command_models.sort(
        key=lambda model: (
            0 if model is release_command_manifests.CommandActionManifest else 1,
            model.__name__,
        )
    )
    for model in command_models:
        action_field = model.model_fields.get("action")
        action_name = action_field.default if action_field is not None and isinstance(action_field.default, str) else None
        if model is release_command_manifests.CommandActionManifest:
            summary = (
                "Common top-level shape for internal unstable command action manifests "
                "written through `MANIFEST_PATH`."
            )
            description = (
                f"{_docstring_for_model(model)} "
                "This schema is documented for maintenance and debugging only and is not "
                "a supported external API."
            )
        else:
            summary = (
                f"Internal unstable JSON action manifest emitted by `{action_name}`."
                if action_name is not None
                else "Internal unstable JSON action manifest emitted by one release-tooling command."
            )
            description = (
                f"{_docstring_for_model(model)} "
                "This command manifest is internal Buildish workflow I/O and is not a supported external API."
            )
        exports.append(
            _schema_export_from_spec(
                RootModelExportSpec(
                    model=model,
                    audience="internal",
                    stability="unstable",
                    summary=summary,
                    description=description,
                    reference_group="internal-unstable-root",
                )
            )
        )
    return tuple(exports)


_MANUAL_EXPORT_SPECS = (
    RootModelExportSpec(
        model=release_models.ComponentConfig,
        audience="supported",
        stability="stable",
        file_path="release-config.yaml",
        summary="Component-authored `release-config.yaml` contract for release policy and target integration settings.",
    ),
    RootModelExportSpec(
        model=release_contracts.RcVoteManifestV1,
        audience="supported",
        stability="stable",
        file_path="rc-vote-manifest.json",
        summary="Signed RC vote manifest that declares the source artifact, trust roots, and secondary artifacts that verifiers must inspect.",
    ),
    RootModelExportSpec(
        model=release_contracts.VerifyRcReportV1,
        audience="supported",
        stability="stable",
        summary="Machine-readable `verify-rc` report contract, typically written through `--report-json`.",
    ),
    RootModelExportSpec(
        model=release_contracts.InspectionBundleManifestV1,
        audience="supported",
        stability="stable",
        file_path="inspection-bundle.json",
        summary="Top-level manifest for a retained verify-rc inspection bundle.",
    ),
    RootModelExportSpec(
        model=release_contracts.InspectReproReportV1,
        audience="supported",
        stability="stable",
        summary="Machine-readable `inspect-repro --json` output contract.",
    ),
    RootModelExportSpec(
        model=release_models.VerifyRcOverrideFileConfig,
        audience="internal",
        stability="stable",
        summary="Local non-canonical verify-rc reproducibility override file passed through `--repro-override-file`.",
    ),
    RootModelExportSpec(
        model=release_contracts.SecondaryArtifactManifestV1,
        audience="internal",
        stability="stable",
        file_path="artifact-manifest.json",
        summary="Typed secondary-artifact registration manifest fragment written by `record-artifact`.",
    ),
    RootModelExportSpec(
        model=release_contracts.MavenRepositoryInventoryV1,
        audience="internal",
        stability="stable",
        summary="Signed Maven repository inventory contract emitted for staged Maven repository verification.",
    ),
    RootModelExportSpec(
        model=release_models.PrepareRcState,
        audience="internal",
        stability="stable",
        summary="Resolved prepare-rc state persisted between release workflow steps.",
    ),
    RootModelExportSpec(
        model=release_models.ReleaseVersionState,
        audience="internal",
        stability="stable",
        summary="Resolved release-version state persisted across final release workflow steps.",
    ),
    RootModelExportSpec(
        model=release_models.CommandContext,
        audience="internal",
        stability="stable",
        summary="Runtime command context built from CLI arguments and validated component configuration.",
    ),
    RootModelExportSpec(
        model=release_contracts.VoteMaterialsRead,
        audience="internal",
        stability="stable",
        summary="Tolerant read model for vote materials consumed during verification and bootstrap workflows.",
    ),
    RootModelExportSpec(
        model=release_contracts.VoteMaterialsStrict,
        audience="internal",
        stability="stable",
        summary="Strict typed vote-materials bundle assembled by release-tooling before RC publication.",
    ),
    RootModelExportSpec(
        model=release_contracts.AsfKeysTrustRootRead,
        audience="internal",
        stability="stable",
        summary="Tolerant read model for ASF KEYS trust-root references carried through vote-materials loading.",
    ),
    RootModelExportSpec(
        model=release_contracts.AuthoritativeManifestReferenceRead,
        audience="internal",
        stability="stable",
        summary="Tolerant read model for the authoritative signed manifest reference used by vote-materials loading.",
    ),
    RootModelExportSpec(
        model=release_contracts.DraftGithubReleaseRead,
        audience="internal",
        stability="stable",
        summary="Tolerant read model for draft GitHub release coordinates recorded in vote materials.",
    ),
    RootModelExportSpec(
        model=release_contracts.SecondaryArtifactBase,
        audience="internal",
        stability="stable",
        summary="Common base shape shared across supported secondary-artifact manifest entries.",
    ),
    RootModelExportSpec(
        model=release_contracts.FileLikeReproducibilityMetadata,
        audience="internal",
        stability="stable",
        summary="Inspection-bundle metadata payload for file-like reproducibility comparisons.",
    ),
    RootModelExportSpec(
        model=release_contracts.SourceArtifactReproducibilityMetadata,
        audience="internal",
        stability="stable",
        summary="Inspection-bundle metadata payload for source-artifact reproducibility evidence.",
    ),
    RootModelExportSpec(
        model=release_contracts.MavenRepositoryPathRuleReport,
        audience="internal",
        stability="stable",
        summary="Rendered Maven repository per-path comparison rule retained in reproducibility metadata.",
    ),
    RootModelExportSpec(
        model=release_contracts.MavenRepositoryPathResultReport,
        audience="internal",
        stability="stable",
        summary="Per-path Maven repository reproducibility comparison result retained in bundle metadata.",
    ),
    RootModelExportSpec(
        model=release_contracts.MavenRepositoryReproducibilityMetadata,
        audience="internal",
        stability="stable",
        summary="Inspection-bundle metadata payload for Maven repository reproducibility evidence.",
    ),
    RootModelExportSpec(
        model=release_contracts.OciImageReproducibilityMetadata,
        audience="internal",
        stability="stable",
        summary="Inspection-bundle metadata payload for OCI image reproducibility evidence.",
    ),
    RootModelExportSpec(
        model=release_contracts.RetainedArtifactSnapshot,
        audience="internal",
        stability="stable",
        summary="Snapshot of one retained staged or rebuilt artifact captured in reproducibility metadata.",
    ),
    RootModelExportSpec(
        model=release_contracts.RebuiltOutputSnapshot,
        audience="internal",
        stability="stable",
        summary="Snapshot of one rebuilt output retained in reproducibility metadata.",
    ),
    RootModelExportSpec(
        model=harness_config_models.ReleaseHarnessConfig,
        audience="internal",
        stability="stable",
        file_path="harness/release-harness.yaml",
        summary="Committed harness configuration contract for local repository bindings and optional overrides.",
    ),
    RootModelExportSpec(
        model=harness_models.HarnessScenario,
        audience="internal",
        stability="stable",
        file_path="harness/scenarios/*.yaml",
        summary="Harness scenario contract for synthetic or `act`-backed release-workflow integration tests.",
    ),
    RootModelExportSpec(
        model=harness_config_models.ResolvedReleaseHarnessConfigJson,
        audience="internal",
        stability="stable",
        summary="Machine-readable JSON payload for one resolved harness configuration.",
    ),
    RootModelExportSpec(
        model=harness_models.HarnessRunResultJson,
        audience="internal",
        stability="stable",
        summary="Machine-readable JSON result for one harness scenario run.",
    ),
    RootModelExportSpec(
        model=harness_models.HarnessSequenceRunResultJson,
        audience="internal",
        stability="stable",
        summary="Machine-readable JSON result for a multi-scenario harness sequence run.",
    ),
    RootModelExportSpec(
        model=harness_models.HarnessShimState,
        audience="internal",
        stability="stable",
        summary="Persisted subprocess-facing harness shim state used by intercepted tool wrappers.",
    ),
    RootModelExportSpec(
        model=harness_models.HarnessCommandTraceEntry,
        audience="internal",
        stability="stable",
        summary="Structured command-trace record emitted by the harness shim for one intercepted invocation.",
    ),
    RootModelExportSpec(
        model=harness_shim_models.HarnessBuiltinGhRefMutationPayload,
        audience="internal",
        stability="stable",
        summary="Harness shim builtin payload describing a synthetic GitHub ref mutation request.",
    ),
)


_SCHEMA_EXPORTS = tuple(
    list(_schema_export_from_spec(spec) for spec in _MANUAL_EXPORT_SPECS)
    + list(_command_action_manifest_exports())
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


def write_reference_file(output_path: Path) -> Path:
    """Write the generated Markdown schema reference document."""

    from apache_buildish_release_tooling.docs.reference_export import (
        write_reference_markdown_file,
    )

    return write_reference_markdown_file(output_path, schema_exports())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m apache_buildish_release_tooling.docs.schema_export"
    )
    parser.add_argument(
        "--output-dir",
        default="site/pages/schemas",
        help="Directory that should receive the generated JSON Schema files.",
    )
    parser.add_argument(
        "--reference-output",
        default="docs/reference/release-model-schema-reference.md",
        help="Path that should receive the generated Markdown schema reference.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Generate the checked-in JSON Schema files and Markdown reference docs."""

    args = _build_parser().parse_args(argv)
    for output_path in write_schema_files(Path(args.output_dir)):
        sys.stdout.write(output_path.as_posix())  # noqa: TID251
        sys.stdout.write("\n")  # noqa: TID251
    reference_path = write_reference_file(Path(args.reference_output))
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
