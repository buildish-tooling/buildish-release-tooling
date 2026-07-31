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

"""Pydantic models for component configuration and derived release state."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from buildish_release_tooling.docs.documentation import (
    ComponentOwnedAuthoredModel,
    ConsumerOwnedAuthoredModel,
    SchemaExportSpecification,
)
from buildish_release_tooling.release.path_validation import validate_project_relative_path

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


VerifyRcOverrideFileConfig.schema_export = SchemaExportSpecification(
    filename="verify-rc-override-file-config.schema.json",
    audience="internal",
    stability="stable",
    summary="Local non-canonical verify-rc reproducibility override file passed through `--repro-override-file`.",
)
