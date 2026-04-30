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
from typing import Any

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
