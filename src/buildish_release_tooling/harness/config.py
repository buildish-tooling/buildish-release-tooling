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

"""Committed harness-config loading and local path resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import ConfigDict, Field

from buildish_release_tooling.shared.parsing import (
    DEFAULT_CONFIG_PARSE_MAX_BYTES,
    read_yaml_mapping_file_bounded,
)
from buildish_release_tooling.docs.documentation import (
    ConsumerOwnedAuthoredModel,
    RuntimeDerivedModel,
    SchemaExportSpecification,
)
from buildish_release_tooling.harness.yaml_types import (
    YamlMapping,
    deep_merge_yaml_mappings,
    require_yaml_mapping,
)

SelfRepositoryCheckoutMode = Literal["when_repository_omitted", "disabled"]
RepositoryOverrideCheckoutMode = Literal["always", "disabled"]


class SelfRepositoryConfig(ConsumerOwnedAuthoredModel):
    """Committed harness settings for the workflow repository under test."""

    model_config = ConfigDict(extra="forbid")

    repository_id: str = Field(description="Logical repository identifier used by the harness configuration layer.")
    local_checkout_mode: SelfRepositoryCheckoutMode = Field(default="when_repository_omitted", description="Policy describing whether the related repository binding should resolve to a local checkout path.")
    local_path: str | None = Field(default=None, description="Resolved or configured local filesystem path associated with the related repository binding.")


class RepositoryOverrideConfig(ConsumerOwnedAuthoredModel):
    """Committed harness settings for one explicit repository override."""

    model_config = ConfigDict(extra="forbid")

    local_checkout_mode: RepositoryOverrideCheckoutMode = Field(default="always", description="Policy describing whether the related repository binding should resolve to a local checkout path.")
    local_path: str | None = Field(default=None, description="Resolved or configured local filesystem path associated with the related repository binding.")


class ReleaseHarnessConfig(ConsumerOwnedAuthoredModel):
    """Committed `release-harness.yaml` plus optional local overrides."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = Field(default="1", description="Schema version of the enclosing Buildish JSON or YAML contract.")
    self_repository: SelfRepositoryConfig = Field(description="Resolved binding for the primary workflow repository under harness control.")
    repository_overrides: dict[str, RepositoryOverrideConfig] = Field(description="Per-repository local override bindings resolved from the harness configuration.", default_factory=dict)


class ResolvedRepositoryBindingJson(RuntimeDerivedModel):
    """Machine-readable JSON payload for one resolved harness repository binding."""

    model_config = ConfigDict(extra="forbid")

    repository_id: str = Field(description="Logical repository identifier used by the harness configuration layer.")
    local_checkout_mode: str = Field(description="Policy describing whether the related repository binding should resolve to a local checkout path.")
    local_path: str = Field(description="Resolved or configured local filesystem path associated with the related repository binding.")


class ResolvedReleaseHarnessConfigJson(RuntimeDerivedModel):
    """Machine-readable JSON payload for one resolved harness config file."""

    model_config = ConfigDict(extra="forbid")

    config_path: str = Field(description="Filesystem path of the resolved configuration document.")
    local_override_path: str = Field(description="Filesystem path of the optional local harness override file that was considered during config loading.")
    local_override_present: bool = Field(description="Whether the optional local harness override file existed and was merged into the effective harness config.")
    self_repository: ResolvedRepositoryBindingJson = Field(description="Resolved binding for the primary workflow repository under harness control.")
    repository_overrides: dict[str, ResolvedRepositoryBindingJson] = Field(description="Per-repository local override bindings resolved from the harness configuration.", default_factory=dict)


@dataclass(frozen=True)
class ResolvedRepositoryBinding:
    """Resolved repository binding for one logical repository identifier."""

    repository_id: str
    local_checkout_mode: str
    local_path: Path

    def to_json_model(self) -> ResolvedRepositoryBindingJson:
        """Return a typed JSON payload representation."""

        return ResolvedRepositoryBindingJson(
            repository_id=self.repository_id,
            local_checkout_mode=self.local_checkout_mode,
            local_path=str(self.local_path),
        )


@dataclass(frozen=True)
class ResolvedReleaseHarnessConfig:
    """Resolved harness repository bindings with local path defaults applied."""

    config_path: Path
    local_override_path: Path
    local_override_present: bool
    self_repository: ResolvedRepositoryBinding
    repository_overrides: dict[str, ResolvedRepositoryBinding]

    def to_json_model(self) -> ResolvedReleaseHarnessConfigJson:
        """Return a typed JSON payload representation."""

        return ResolvedReleaseHarnessConfigJson(
            config_path=str(self.config_path),
            local_override_path=str(self.local_override_path),
            local_override_present=self.local_override_present,
            self_repository=self.self_repository.to_json_model(),
            repository_overrides={
                repository_id: binding.to_json_model()
                for repository_id, binding in sorted(self.repository_overrides.items())
            },
        )


def repository_root_for_config(config_path: Path) -> Path:
    """Return the repository root implied by one harness config path."""

    if (
        config_path.parent.name == "harness"
        and config_path.parent.parent.name == "buildish-release-tooling"
    ):
        return config_path.parent.parent.parent.resolve(strict=False)
    if config_path.parent.name == "buildish-release-harness":
        return config_path.parent.parent.resolve(strict=False)
    return config_path.parent.resolve(strict=False)


def default_local_override_path(config_path: Path) -> Path:
    """Return the default `release-harness.local.yaml` path next to a committed config."""

    return config_path.with_name(f"{config_path.stem}.local{config_path.suffix}")


def load_release_harness_config(config_path: Path) -> ResolvedReleaseHarnessConfig:
    """Load, merge, validate, and resolve one harness config file."""

    repository_root = repository_root_for_config(config_path)
    committed_payload = _load_yaml_mapping(config_path)
    local_override_path = default_local_override_path(config_path)
    local_payload = _load_yaml_mapping(local_override_path) if local_override_path.exists() else {}
    merged_payload = _deep_merge_dicts(committed_payload, local_payload)
    config = ReleaseHarnessConfig.model_validate(merged_payload)
    return ResolvedReleaseHarnessConfig(
        config_path=config_path,
        local_override_path=local_override_path,
        local_override_present=local_override_path.exists(),
        self_repository=_resolve_binding(
            repository_root,
            config.self_repository.repository_id,
            config.self_repository.local_checkout_mode,
            config.self_repository.local_path,
        ),
        repository_overrides={
            repository_id: _resolve_binding(
                repository_root,
                repository_id,
                override.local_checkout_mode,
                override.local_path,
            )
            for repository_id, override in config.repository_overrides.items()
        },
    )


def _load_yaml_mapping(path: Path) -> YamlMapping:
    """Load one YAML document and require a mapping payload."""

    return require_yaml_mapping(
        read_yaml_mapping_file_bounded(path, max_bytes=DEFAULT_CONFIG_PARSE_MAX_BYTES),
        source=str(path),
    )


def _deep_merge_dicts(base: YamlMapping, overlay: YamlMapping) -> YamlMapping:
    """Return a recursive dict merge where overlay values win."""

    return deep_merge_yaml_mappings(base, overlay)


def _resolve_binding(
    repository_root: Path,
    repository_id: str,
    local_checkout_mode: str,
    local_path: str | None,
) -> ResolvedRepositoryBinding:
    """Resolve one repository binding to a concrete local path relative to the repository root."""

    raw_path = Path(local_path) if local_path is not None else _default_repository_path(repository_id)
    resolved_path = raw_path if raw_path.is_absolute() else (repository_root / raw_path)
    return ResolvedRepositoryBinding(
        repository_id=repository_id,
        local_checkout_mode=local_checkout_mode,
        local_path=resolved_path.resolve(strict=False),
    )


def _default_repository_path(repository_id: str) -> Path:
    """Derive the default repository-root-relative sibling checkout path `../<repo-name>`."""

    return Path("..") / repository_id.rsplit("/", 1)[-1]


ReleaseHarnessConfig.schema_export = SchemaExportSpecification(
    filename="release-harness-config.schema.json",
    audience="internal",
    stability="stable",
    file_path="harness/release-harness.yaml",
    summary="Committed harness configuration contract for local repository bindings and optional overrides.",
)
ResolvedReleaseHarnessConfigJson.schema_export = SchemaExportSpecification(
    filename="resolved-release-harness-config-json.schema.json",
    audience="internal",
    stability="stable",
    summary="Machine-readable JSON payload for one resolved harness configuration.",
)
