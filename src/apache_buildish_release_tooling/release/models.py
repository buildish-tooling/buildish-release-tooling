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

from pydantic import ConfigDict, Field, field_validator, model_validator

from apache_buildish_release_tooling.docs.documentation import (
    ComponentOwnedAuthoredModel,
    ConsumerOwnedAuthoredModel,
    RuntimeDerivedModel,
    SchemaExportSpecification,
)
from apache_buildish_release_tooling.release.path_validation import validate_project_relative_path

ReleaseProgram = Literal["asf"]
ProjectStatus = Literal["tlp", "incubating"]


class AtrConfig(ComponentOwnedAuthoredModel):
    """Validated optional ATR integration policy and release coordinates."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="Whether the related optional integration or policy block is enabled for this component.")
    base_url: str | None = Field(default=None, description="Base URL used to discover or publish the related artifact or service resource.")
    committee: str | None = Field(default=None, description="ASF committee slug that owns the component or ATR publication target.")
    product_line: str | None = Field(default=None, description="ATR product-line identifier used for the related candidate publication.")
    source_artifact_paths: list[str] = Field(description="Path globs that select staged source artifacts for the related ATR publication or verification policy.", default_factory=list)
    binary_artifact_paths: list[str] = Field(description="Path globs that select staged binary artifacts for ATR publication.", default_factory=list)
    strict_checking: bool = Field(default=False, description="Whether the related check or reporting step should fail the command when warnings or failures are present.")
    license_check_mode: str = Field(default="both", description="ATR license-check flavor that Buildish should request or report for the related publication run.")

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


class VerifyRcSelectionConfig(ComponentOwnedAuthoredModel):
    """One canonical reproducibility profile selection."""

    profile_id: str = Field(description="Reproducibility profile identifier selected for the related artifact or source verification.")
    mode: str | None = Field(default=None, description="Optional future-facing mode hint recorded next to the selected reproducibility profile. When present, it narrows how the selected profile should be interpreted for this source-artifact policy block.")


class VerifyRcSourceConfig(ComponentOwnedAuthoredModel):
    """Source-artifact verification policy for verify-rc."""

    reproducibility: VerifyRcSelectionConfig | None = Field(default=None, description="Reproducibility policy or result block associated with the related source or secondary artifact.")


class VerifyRcBuildConfig(ComponentOwnedAuthoredModel):
    """Host-direct rebuild recipe configuration for one reproducibility profile."""

    command: list[str] = Field(description="Literal argv list that Buildish executed or recommends for the related step.")
    working_dir: str | None = Field(default=None, description="Repository-root-relative working directory that Buildish should use when running the related build recipe.")
    env: dict[str, str] = Field(description="Environment-variable mapping supplied to the related build, scenario, or command step.", default_factory=dict)
    output_globs: list[str] = Field(description="Repository-root-relative glob patterns that identify expected outputs of the related build recipe.")

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
        return validate_project_relative_path(value, field_name="verify_rc build.working_dir")

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
        return [
            validate_project_relative_path(item, field_name="verify_rc build.output_globs")
            for item in value
        ]


class VerifyRcBuildOverrideConfig(ConsumerOwnedAuthoredModel):
    """Local non-canonical rebuild overrides for one reproducibility profile."""

    command: list[str] | None = Field(default=None, description="Literal argv list that Buildish executed or recommends for the related step.")
    working_dir: str | None = Field(default=None, description="Repository-root-relative working directory that Buildish should use when running the related build recipe.")
    env: dict[str, str] = Field(description="Environment-variable mapping supplied to the related build, scenario, or command step.", default_factory=dict)
    output_globs: list[str] | None = Field(default=None, description="Repository-root-relative glob patterns that identify expected outputs of the related build recipe.")

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
        return validate_project_relative_path(
            value,
            field_name="verify_rc build override working_dir",
        )

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
        return [
            validate_project_relative_path(
                item,
                field_name="verify_rc build override output_globs",
            )
            for item in value
        ]

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


class VerifyRcExactBytesComparisonConfig(ComponentOwnedAuthoredModel):
    """Exact-byte comparison policy for source and file-like reproducibility profiles."""

    mode: Literal["exact-bytes"] = Field(default="exact-bytes", description="Comparison mode literal indicating that reproducibility succeeds only when the rebuilt artifact bytes match the staged bytes exactly.")


class VerifyRcMavenPathRuleConfig(ComponentOwnedAuthoredModel):
    """One regex-based per-path comparison override inside a Maven repository profile."""

    pattern: str = Field(description="Regular-expression pattern used to match one family of repository paths.")
    mode: Literal["exact-bytes", "zip-normalized", "content-only", "remote-only"] = Field(description="Comparison mode that should apply to Maven repository paths matching this regex rule instead of the repository default.")

    @field_validator("pattern")
    @classmethod
    def _validate_pattern(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("verify_rc maven path_rules pattern must not be empty")
        return normalized


class VerifyRcMavenRepositoryComparisonConfig(ComponentOwnedAuthoredModel):
    """Repository-tree comparison policy for Maven repository reproducibility profiles."""

    mode: Literal["repository-tree"] = Field(default="repository-tree", description="Comparison mode literal indicating that this reproducibility profile compares a rebuilt Maven repository tree against the staged repository tree.")
    repository_dir: str = Field(description="Repository-root-relative rebuild output directory that should contain the local Maven repository tree.")
    require_signatures: bool = Field(default=False, description="Whether Maven repository reproducibility should require detached signature files to exist and compare successfully.")
    path_rules: list[VerifyRcMavenPathRuleConfig] = Field(description="Regex-based per-path comparison rules that specialize the default Maven repository comparison behavior.", default_factory=list)

    @field_validator("repository_dir")
    @classmethod
    def _validate_repository_dir(cls, value: str) -> str:
        return validate_project_relative_path(
            value,
            field_name="verify_rc maven repository_dir",
        )


class VerifyRcOciImageComparisonConfig(ComponentOwnedAuthoredModel):
    """Digest-based OCI image comparison policy for image reproducibility profiles."""

    mode: Literal["platform-digest", "provenance-only"] = Field(description="Digest-comparison strategy used for OCI image reproducibility, either requiring matching platform digests or only provenance-level agreement.")
    image_ref: str = Field(description="Fully qualified OCI image reference used for inspection or local rebuild comparison.")

    @field_validator("image_ref")
    @classmethod
    def _validate_image_ref(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("verify_rc oci image_ref must not be empty")
        return normalized


class VerifyRcProfileOverrideConfig(ConsumerOwnedAuthoredModel):
    """Local non-canonical override for one canonical reproducibility profile."""

    build: VerifyRcBuildOverrideConfig = Field(description="Nested build recipe or effective build execution block for one reproducibility contract.")


class VerifyRcProfileConfig(ComponentOwnedAuthoredModel):
    """One canonical reproducibility profile selected by signed manifest metadata."""

    kind: Literal[
        "source-artifact",
        "generic-file",
        "generic-file-with-openpgp",
        "maven-repository",
        "npm-package",
        "oci-image",
        "python-distribution",
    ] = Field(description="Artifact-kind discriminator that selects which canonical reproducibility profile shape applies.")
    build: VerifyRcBuildConfig = Field(description="Nested build recipe or effective build execution block for one reproducibility contract.")
    comparison: (
        VerifyRcExactBytesComparisonConfig
        | VerifyRcMavenRepositoryComparisonConfig
        | VerifyRcOciImageComparisonConfig
    ) = Field(description="Artifact-kind-specific reproducibility comparison policy for the canonical profile.")

    @model_validator(mode="after")
    def _validate_comparison_for_kind(self) -> VerifyRcProfileConfig:
        if self.kind == "maven-repository":
            if not isinstance(self.comparison, VerifyRcMavenRepositoryComparisonConfig):
                raise ValueError(
                    "verify_rc maven-repository profiles must use comparison.mode 'repository-tree'"
                )
            return self
        if self.kind == "oci-image":
            if not isinstance(self.comparison, VerifyRcOciImageComparisonConfig):
                raise ValueError(
                    "verify_rc oci-image profiles must use comparison.mode 'platform-digest' or 'provenance-only'"
                )
            return self
        if not isinstance(self.comparison, VerifyRcExactBytesComparisonConfig):
            raise ValueError(
                "verify_rc source-artifact, generic-file, python-distribution, and npm-package profiles must use comparison.mode 'exact-bytes'"
            )
        return self


class VerifyRcConfig(ComponentOwnedAuthoredModel):
    """Structured verify-rc configuration for rebuild recipes and profile selection."""

    source: VerifyRcSourceConfig | None = Field(default=None, description="Source-artifact-specific verify-rc policy block nested inside the component configuration.")
    profiles: dict[str, VerifyRcProfileConfig] = Field(description="Canonical reproducibility profiles keyed by profile identifier in the component configuration.", default_factory=dict)

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


class VerifyRcOverrideConfig(ConsumerOwnedAuthoredModel):
    """Top-level local reproducibility override mapping keyed by profile_id."""

    profile_overrides: dict[str, VerifyRcProfileOverrideConfig] = Field(description="Local non-canonical reproducibility overrides keyed by canonical profile identifier.", default_factory=dict)


class VerifyRcOverrideFileConfig(ConsumerOwnedAuthoredModel):
    """Validated local override file for non-canonical reproducibility runs."""

    verify_rc: VerifyRcOverrideConfig = Field(description="Nested verify-rc configuration block for the component or local override file.")


class ComponentConfig(ComponentOwnedAuthoredModel):
    """Validated component policy and release-target configuration."""

    model_config = ConfigDict(extra="forbid")

    component_id: str = Field(description="Stable component identifier used across Buildish manifests, reports, and release-state records.")
    source_artifact_prefix: str = Field(description="Configured top-level directory prefix that the component's source archive should unpack to.")
    asf_dist_dev_base: str = Field(description="Configured ASF `dist/dev` base URL under which RC materials are staged for this component.")
    asf_dist_release_base: str = Field(description="Configured ASF `dist/release` base URL under which final source releases are published for this component.")
    asf_keys_url: str = Field(description="Configured ASF KEYS URL that this component treats as authoritative for RC signature verification.")
    moving_tags_enabled: bool = Field(description="Whether this component maintains moving release-line tags that are updated during final release publication.")
    latest_tag_enabled: bool = Field(description="Whether this component publishes a moving `latest` tag in addition to line-specific moving tags.")
    secondary_targets: list[str] = Field(description="Configured secondary target families that the component publishes in addition to the source artifact.")
    final_tag_mode: str = Field(description="Configured or recorded policy describing how the final immutable release tag should be created for this component or release run.")
    vote_release_name: str = Field(description="Human-facing release name that Buildish should use in vote mails, release summaries, and other user-visible output.")
    release_program: ReleaseProgram = Field(default="asf", description="Release-governance program whose policy model Buildish should apply to this component.")
    project_status: ProjectStatus = Field(default="tlp", description="Project lifecycle status within the configured release program.")
    incubator_disclaimer_file: str = Field(default="DISCLAIMER", description="Project-root-relative file path that supplies the approved incubating disclaimer text.")
    candidate_start_number: int = Field(default=0, description="First numeric candidate suffix to use when no matching candidate tag exists for a version and label.", ge=0)
    release_summary_include_final_tag_mode: bool = Field(default=False, description="Whether release summary output should explicitly include the configured final-tag mode.")
    release_verification_guide_url: str = Field(description="User-facing guide URL that Buildish should include when pointing verifiers at the release verification instructions.")
    verify_rc_instructions: str = Field(description="Human-facing verification instructions that Buildish should include for this component's RC vote materials.")
    prepare_rc_runs_tests: bool = Field(default=False, description="Whether the component's canonical prepare-rc workflow is expected to run project test steps.")
    release_branch_ci_required: bool = Field(default=False, description="Whether this component requires a green release-branch CI signal before final publication can proceed.")
    atr: AtrConfig | None = Field(default=None, description="Nested ATR integration configuration for this component.")
    verify_rc: VerifyRcConfig | None = Field(default=None, description="Nested verify-rc configuration block for the component or local override file.")

    @property
    def is_incubating(self) -> bool:
        """Return whether ASF incubating release policy applies."""

        return self.release_program == "asf" and self.project_status == "incubating"

    @field_validator("secondary_targets", mode="before")
    @classmethod
    def _normalize_secondary_targets(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [item for item in value.split() if item]
        if isinstance(value, list):
            return [str(item) for item in value]
        raise TypeError("secondary_targets must be a whitespace-separated string or a list")

    @field_validator("incubator_disclaimer_file")
    @classmethod
    def _validate_incubator_disclaimer_file(cls, value: str) -> str:
        return validate_project_relative_path(value, field_name="incubator_disclaimer_file")

    @model_validator(mode="after")
    def _validate_ci_policy(self) -> ComponentConfig:
        if not self.prepare_rc_runs_tests and not self.release_branch_ci_required:
            raise ValueError(
                "component policy must enable prepare_rc_runs_tests or release_branch_ci_required"
            )
        return self


class PrepareRcState(RuntimeDerivedModel):
    """Resolved source and artifact state for an RC workflow run."""

    model_config = ConfigDict(extra="forbid")

    resolved_release_branch: str = Field(description="Release branch name that Buildish resolved for the selected version.")
    resolved_source_ref: str = Field(description="Resolved source Git commit SHA that Buildish selected for release production or verification.")
    source_date_epoch: int = Field(description="Canonical `SOURCE_DATE_EPOCH` integer carried through RC production and verification.", ge=0)
    candidate_label: str = Field(default="rc", description="Candidate-series label used in the selected candidate tag.")
    rc_number: int = Field(description="Numeric RC sequence selected for the related version.", ge=0)
    rc_tag: str = Field(description="Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix.")
    final_tag: str = Field(description="Final immutable Git tag that Buildish intends to publish for the released version.")
    source_artifact_name: str = Field(description="Filename of the staged source release artifact.")
    source_artifact_root_name: str = Field(description="Root directory name that the source release archive should unpack to.")
    source_artifact_prefix_path: str = Field(description="Top-level path prefix inside the source release archive.")
    staging_url: str = Field(description="ASF dev/dist staging directory URL selected for the current RC.")


class ReleaseVersionState(RuntimeDerivedModel):
    """Resolved final-release state for a release workflow run."""

    model_config = ConfigDict(extra="forbid")

    selected_rc_tag: str = Field(description="RC tag that Buildish selected as the winning release candidate for a final release action.")
    final_tag: str = Field(description="Final immutable Git tag that Buildish intends to publish for the released version.")
    archive_versions: list[str] = Field(description="Older same-line release versions that Buildish resolved for archival pruning.")
    release_url: str = Field(description="Primary user-facing URL of the related GitHub release or published release artifact.")
    moving_tags: list[str] = Field(description="Derived moving tags or aliases that should point at the final released version.")


class CommandContext(RuntimeDerivedModel):
    """Common runtime context passed into command handlers."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    component_config: ComponentConfig = Field(description="Validated component configuration resolved for the current Buildish command run.")
    component_config_path: Path | None = Field(default=None, description="Filesystem path of the component configuration file used for the current Buildish command run.")


VerifyRcOverrideFileConfig.schema_export = SchemaExportSpecification(
    filename="verify-rc-override-file-config.schema.json",
    audience="internal",
    stability="stable",
    summary="Local non-canonical verify-rc reproducibility override file passed through `--repro-override-file`.",
)
ComponentConfig.schema_export = SchemaExportSpecification(
    filename="component-config.schema.json",
    file_path="release-config.yaml",
    summary="Component-authored `release-config.yaml` contract for release policy and target integration settings.",
)
PrepareRcState.schema_export = SchemaExportSpecification(
    filename="prepare-rc-state.schema.json",
    audience="internal",
    stability="stable",
    summary="Resolved prepare-rc state persisted between release workflow steps.",
)
ReleaseVersionState.schema_export = SchemaExportSpecification(
    filename="release-version-state.schema.json",
    audience="internal",
    stability="stable",
    summary="Resolved release-version state persisted across final release workflow steps.",
)
CommandContext.schema_export = SchemaExportSpecification(
    filename="command-context.schema.json",
    audience="internal",
    stability="stable",
    summary="Runtime command context built from CLI arguments and validated component configuration.",
)
