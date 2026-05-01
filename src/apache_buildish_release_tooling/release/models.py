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

"""Pydantic models for component configuration and derived release state."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apache_buildish_release_tooling.contracts import BuildishContractModel


class AtrConfig(BuildishContractModel):
    """Validated optional ATR integration policy and release coordinates."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    base_url: str | None = None
    committee: str | None = None
    product_line: str | None = None
    source_artifact_paths: list[str] = Field(default_factory=list)
    binary_artifact_paths: list[str] = Field(default_factory=list)
    strict_checking: bool = False
    license_check_mode: str = "both"

    @field_validator("source_artifact_paths", "binary_artifact_paths", mode="before")
    @classmethod
    def _normalize_path_patterns(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item for item in value.splitlines() if item.strip()]
        if isinstance(value, list):
            return [str(item) for item in value]
        raise TypeError("ATR path patterns must be a newline-separated string or a list")

    @field_validator("license_check_mode")
    @classmethod
    def _validate_license_check_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"both", "lightweight", "rat"}:
            raise ValueError("ATR license_check_mode must be one of: both, lightweight, rat")
        return normalized

    @model_validator(mode="after")
    def _validate_enabled_config(self) -> AtrConfig:
        if not self.enabled:
            return self
        if not self.base_url:
            raise ValueError("ATR config must define base_url when enabled")
        if not self.committee:
            raise ValueError("ATR config must define committee when enabled")
        if not self.product_line:
            raise ValueError("ATR config must define product_line when enabled")
        return self


class VerifyRcSelectionConfig(BuildishContractModel):
    """One canonical reproducibility profile selection."""

    profile_id: str
    mode: str | None = None


class VerifyRcSourceConfig(BuildishContractModel):
    """Source-artifact verification policy for verify-rc."""

    reproducibility: VerifyRcSelectionConfig | None = None


class VerifyRcBuildConfig(BuildishContractModel):
    """Host-direct rebuild recipe configuration for one reproducibility profile."""

    command: list[str]
    working_dir: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    output_globs: list[str]

    @field_validator("command", mode="after")
    @classmethod
    def _validate_command(cls, value: list[str]) -> list[str]:
        if not value or any(not item.strip() for item in value):
            raise ValueError("verify_rc build.command must be a non-empty argv list")
        return value

    @field_validator("working_dir")
    @classmethod
    def _validate_working_dir(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("verify_rc build.working_dir must not be empty")
        if Path(normalized).is_absolute():
            raise ValueError("verify_rc build.working_dir must be relative to the project root")
        return normalized

    @field_validator("env", mode="after")
    @classmethod
    def _validate_env(cls, value: dict[str, str]) -> dict[str, str]:
        for key, env_value in value.items():
            if not key.strip():
                raise ValueError("verify_rc build.env keys must be non-empty strings")
            if not isinstance(env_value, str):
                raise TypeError("verify_rc build.env values must be strings")
        return value

    @field_validator("output_globs", mode="after")
    @classmethod
    def _validate_output_globs(cls, value: list[str]) -> list[str]:
        if not value or any(not item.strip() for item in value):
            raise ValueError("verify_rc build.output_globs must contain at least one non-empty glob")
        return value


class VerifyRcBuildOverrideConfig(BuildishContractModel):
    """Local non-canonical rebuild overrides for one reproducibility profile."""

    command: list[str] | None = None
    working_dir: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    output_globs: list[str] | None = None

    @field_validator("command", mode="after")
    @classmethod
    def _validate_command(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if not value or any(not item.strip() for item in value):
            raise ValueError("verify_rc build override command must be a non-empty argv list")
        return value

    @field_validator("working_dir")
    @classmethod
    def _validate_working_dir(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("verify_rc build override working_dir must not be empty")
        if Path(normalized).is_absolute():
            raise ValueError("verify_rc build override working_dir must be relative to the project root")
        return normalized

    @field_validator("env", mode="after")
    @classmethod
    def _validate_env(cls, value: dict[str, str]) -> dict[str, str]:
        for key, env_value in value.items():
            if not key.strip():
                raise ValueError("verify_rc build override env keys must be non-empty strings")
            if not isinstance(env_value, str):
                raise TypeError("verify_rc build override env values must be strings")
        return value

    @field_validator("output_globs", mode="after")
    @classmethod
    def _validate_output_globs(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if not value or any(not item.strip() for item in value):
            raise ValueError("verify_rc build override output_globs must contain at least one non-empty glob")
        return value

    @model_validator(mode="after")
    def _validate_non_empty_override(self) -> VerifyRcBuildOverrideConfig:
        if (
            self.command is None
            and self.working_dir is None
            and not self.env
            and self.output_globs is None
        ):
            raise ValueError("verify_rc build override must change at least one build field")
        return self


class VerifyRcProfileOverrideConfig(BuildishContractModel):
    """Local non-canonical override for one canonical reproducibility profile."""

    build: VerifyRcBuildOverrideConfig


class VerifyRcProfileConfig(BuildishContractModel):
    """One canonical reproducibility profile selected by signed manifest metadata."""

    kind: Literal[
        "source-artifact",
        "generic-file",
        "generic-file-with-openpgp",
        "maven-repository",
        "npm-package",
        "oci-image",
        "python-distribution",
    ]
    build: VerifyRcBuildConfig
    comparison: dict[str, Any]

    @field_validator("comparison", mode="after")
    @classmethod
    def _validate_comparison(cls, value: dict[str, Any]) -> dict[str, Any]:
        mode = value.get("mode")
        if not isinstance(mode, str) or not mode.strip():
            raise ValueError("verify_rc profile comparison must declare a non-empty mode")
        return value


class VerifyRcConfig(BuildishContractModel):
    """Structured verify-rc configuration for rebuild recipes and profile selection."""

    source: VerifyRcSourceConfig | None = None
    profiles: dict[str, VerifyRcProfileConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_source_profile_reference(self) -> VerifyRcConfig:
        reproducibility = self.source.reproducibility if self.source is not None else None
        if reproducibility is None:
            return self
        if reproducibility.profile_id not in self.profiles:
            raise ValueError(
                "verify_rc.source.reproducibility.profile_id must reference one configured profile"
            )
        return self


class VerifyRcOverrideConfig(BuildishContractModel):
    """Top-level local reproducibility override mapping keyed by profile_id."""

    profile_overrides: dict[str, VerifyRcProfileOverrideConfig] = Field(default_factory=dict)


class VerifyRcOverrideFileConfig(BuildishContractModel):
    """Validated local override file for non-canonical reproducibility runs."""

    verify_rc: VerifyRcOverrideConfig


class ComponentConfig(BuildishContractModel):
    """Validated component policy and release-target configuration."""

    model_config = ConfigDict(extra="forbid")

    component_id: str
    source_artifact_prefix: str
    asf_dist_dev_base: str
    asf_dist_release_base: str
    asf_keys_url: str
    moving_tags_enabled: bool
    latest_tag_enabled: bool
    secondary_targets: list[str]
    final_tag_mode: str
    vote_release_name: str
    incubator_vote_enabled: bool = False
    release_summary_include_final_tag_mode: bool = False
    release_verification_guide_url: str
    verify_rc_instructions: str
    prepare_rc_runs_tests: bool = False
    release_branch_ci_required: bool = False
    atr: AtrConfig | None = None
    verify_rc: VerifyRcConfig | None = None

    @field_validator("secondary_targets", mode="before")
    @classmethod
    def _normalize_secondary_targets(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [item for item in value.split() if item]
        if isinstance(value, list):
            return [str(item) for item in value]
        raise TypeError("secondary_targets must be a whitespace-separated string or a list")

    @model_validator(mode="after")
    def _validate_ci_policy(self) -> ComponentConfig:
        if not self.prepare_rc_runs_tests and not self.release_branch_ci_required:
            raise ValueError(
                "component policy must enable prepare_rc_runs_tests or release_branch_ci_required"
            )
        return self


class PrepareRcState(BaseModel):
    """Resolved source and artifact state for an RC workflow run."""

    model_config = ConfigDict(extra="forbid")

    resolved_release_branch: str
    resolved_source_ref: str
    source_date_epoch: int = Field(ge=0)
    rc_number: int = Field(ge=0)
    rc_tag: str
    final_tag: str
    source_artifact_name: str
    source_artifact_root_name: str
    source_artifact_prefix_path: str
    staging_url: str


class ReleaseVersionState(BaseModel):
    """Resolved final-release state for a release workflow run."""

    model_config = ConfigDict(extra="forbid")

    selected_rc_tag: str
    final_tag: str
    archive_versions: list[str]
    release_url: str
    moving_tags: list[str]


class CommandContext(BaseModel):
    """Common runtime context passed into command handlers."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    component_config: ComponentConfig
    component_config_path: Path | None = None
