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

"""ASF-specific authored release, vote, ATR, and dist policy."""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator

from buildish_release_tooling.docs.documentation import ComponentOwnedAuthoredModel
from buildish_release_tooling.release.path_validation import validate_project_relative_path

_ASF_DIST_DEV_PREFIX = "https://dist.apache.org/repos/dist/dev/"
_ASF_DIST_RELEASE_PREFIX = "https://dist.apache.org/repos/dist/release/"


class AsfAtrConfig(ComponentOwnedAuthoredModel):
    """Optional Apache Trusted Release integration policy and coordinates."""

    enabled: bool = Field(
        default=False,
        description="Whether ATR publication and check reporting are enabled.",
    )
    base_url: str | None = Field(
        default=None,
        description="Base URL used for ATR publication and status queries.",
    )
    committee: str | None = Field(
        default=None,
        description="ASF committee slug supplied to ATR.",
    )
    product_line: str | None = Field(
        default=None,
        description="ATR project or product-line identifier.",
    )
    source_artifact_paths: list[str] = Field(
        default_factory=list,
        description="Path globs selecting source artifacts for ATR.",
    )
    binary_artifact_paths: list[str] = Field(
        default_factory=list,
        description="Path globs selecting binary artifacts for ATR.",
    )
    strict_checking: bool = Field(
        default=False,
        description="Whether ATR warnings or failures fail the command.",
    )
    license_check_mode: Literal["both", "lightweight", "rat"] = Field(
        default="both",
        description="ATR license-check flavor requested for the candidate.",
    )

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

    @model_validator(mode="after")
    def _validate_enabled_config(self) -> AsfAtrConfig:
        if not self.enabled:
            return self
        if not self.base_url:
            raise ValueError("ASF ATR config must define base_url when enabled")
        if not self.committee:
            raise ValueError("ASF ATR config must define committee when enabled")
        if not self.product_line:
            raise ValueError("ASF ATR config must define product_line when enabled")
        return self


class AsfReleaseProfileConfig(ComponentOwnedAuthoredModel):
    """ASF project policy and trusted release infrastructure."""

    project_status: Literal["tlp", "incubating"] = Field(
        default="tlp",
        description="Project lifecycle status under ASF release policy.",
    )
    dist_dev_base: str = Field(description="ASF dist/dev base URL for candidate materials.")
    dist_release_base: str = Field(description="ASF dist/release base URL for final releases.")
    keys_url: str = Field(description="Authoritative ASF KEYS URL for signature verification.")
    disclaimer_file: str = Field(
        default="DISCLAIMER",
        description="Repository-relative Incubator disclaimer file.",
    )
    atr: AsfAtrConfig | None = Field(
        default=None,
        description="Optional ASF ATR integration policy.",
    )

    @field_validator("disclaimer_file")
    @classmethod
    def _validate_disclaimer_file(cls, value: str) -> str:
        return validate_project_relative_path(value, field_name="asf disclaimer_file")

    @property
    def is_incubating(self) -> bool:
        """Return whether ASF Incubator policy applies."""

        return self.project_status == "incubating"


class AsfDistPublicationConfig(ComponentOwnedAuthoredModel):
    """ASF dist SVN authoritative publication target."""

    kind: Literal["asf-dist-svn"] = Field(
        default="asf-dist-svn",
        description="Publication target discriminator.",
    )


class AsfVoteMaterialsConfig(ComponentOwnedAuthoredModel):
    """ASF candidate vote-material rendering policy."""

    profile: Literal["asf"] = Field(
        default="asf",
        description="Vote-material profile discriminator.",
    )
    release_name: str = Field(description="Human-facing release name used in ASF vote text.")
    verification_guide_url: str = Field(
        description="User-facing release verification guide URL.",
    )
    instructions: str = Field(
        description="Human-facing verification instructions for the exact candidate.",
    )


def validate_asf_dist_urls(
    profile: AsfReleaseProfileConfig,
    *,
    allow_test_targets: bool,
) -> None:
    """Validate selected ASF dist targets for production or explicit test mode."""

    _validate_asf_dist_url(
        field_name="policy_profiles.asf.dist_dev_base",
        configured_url=profile.dist_dev_base,
        production_prefix=_ASF_DIST_DEV_PREFIX,
        allow_test_targets=allow_test_targets,
    )
    _validate_asf_dist_url(
        field_name="policy_profiles.asf.dist_release_base",
        configured_url=profile.dist_release_base,
        production_prefix=_ASF_DIST_RELEASE_PREFIX,
        allow_test_targets=allow_test_targets,
    )


def _validate_asf_dist_url(
    *,
    field_name: str,
    configured_url: str,
    production_prefix: str,
    allow_test_targets: bool,
) -> None:
    if _uses_production_prefix(configured_url, production_prefix):
        return
    parsed = urlparse(configured_url)
    if allow_test_targets and parsed.scheme in {"file", "http"}:
        return
    if allow_test_targets:
        raise ValueError(
            f"{field_name} must use {production_prefix} or a file:// or http:// URI "
            f"in test-target mode: {configured_url}"
        )
    raise ValueError(
        f"{field_name} must use {production_prefix}; pass --test-target-mode only for "
        f"local file:// or http:// fixtures: {configured_url}"
    )


def _uses_production_prefix(configured_url: str, production_prefix: str) -> bool:
    configured = urlparse(configured_url)
    production = urlparse(production_prefix)
    if configured.scheme != production.scheme or configured.netloc != production.netloc:
        return False
    production_path = production.path.rstrip("/") + "/"
    return configured.path.startswith(production_path)
