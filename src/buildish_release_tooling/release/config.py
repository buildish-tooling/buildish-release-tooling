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

"""Authored release configuration composition, loading, and capability helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from buildish_release_tooling.docs.documentation import (
    ComponentOwnedAuthoredModel,
    RuntimeDerivedModel,
    SchemaExportSpecification,
)
from buildish_release_tooling.release.core.config import (
    ArtifactPolicyConfig,
    BuiltSourceSnapshotConfig,
    CandidateConfig,
    ComponentIdentityConfig,
    GenericVoteMaterialsConfig,
    LifecycleConfig,
    SourceConfig,
    TagPolicyConfig,
    VersioningConfig,
)
from buildish_release_tooling.release.foundations.asf.config import (
    AsfDistPublicationConfig,
    AsfReleaseProfileConfig,
    AsfVoteMaterialsConfig,
    validate_asf_dist_urls,
)
from buildish_release_tooling.release.models import (
    VerifyRcConfig,
    VerifyRcOverrideConfig,
    VerifyRcOverrideFileConfig,
)
from buildish_release_tooling.release.platforms.github.config import (
    GitHubActionPublicationConfig,
    GitHubReleaseAssetsPublicationConfig,
    GitHubReleasePublicationConfig,
)
from buildish_release_tooling.shared.parsing import (
    DEFAULT_CONFIG_PARSE_MAX_BYTES,
    read_yaml_mapping_file_bounded,
)


class PythonPackagePublicationConfig(ComponentOwnedAuthoredModel):
    """Secondary publication to the configured Python package index."""

    kind: Literal["pypi"] = Field(
        default="pypi",
        description="Secondary publication target discriminator.",
    )


class DockerHubPublicationConfig(ComponentOwnedAuthoredModel):
    """Secondary publication to Docker Hub."""

    kind: Literal["dockerhub"] = Field(
        default="dockerhub",
        description="Secondary publication target discriminator.",
    )


PrimaryPublicationTargetConfig = Annotated[
    GitHubReleasePublicationConfig | AsfDistPublicationConfig,
    Field(discriminator="kind"),
]
SecondaryPublicationTargetConfig = Annotated[
    GitHubActionPublicationConfig
    | GitHubReleaseAssetsPublicationConfig
    | PythonPackagePublicationConfig
    | DockerHubPublicationConfig,
    Field(discriminator="kind"),
]
VoteMaterialsConfig = Annotated[
    GenericVoteMaterialsConfig | AsfVoteMaterialsConfig,
    Field(discriminator="profile"),
]


class PublicationConfig(ComponentOwnedAuthoredModel):
    """Authoritative, convenience, and secondary publication targets."""

    authoritative: PrimaryPublicationTargetConfig = Field(
        description="Canonical publication target for the release.",
    )
    convenience: list[PrimaryPublicationTargetConfig] = Field(
        default_factory=list,
        description="Non-authoritative release publication mirrors or pages.",
    )
    secondary: list[SecondaryPublicationTargetConfig] = Field(
        default_factory=list,
        description="Additional package, image, action, or asset publication targets.",
    )


class PolicyProfilesConfig(ComponentOwnedAuthoredModel):
    """Explicit foundation policy profiles selected by a component."""

    asf: AsfReleaseProfileConfig | None = Field(
        default=None,
        description="Optional Apache Software Foundation release policy.",
    )


class ReleaseConfig(ComponentOwnedAuthoredModel):
    """Component-authored release lifecycle and capability configuration."""

    component: ComponentIdentityConfig = Field(
        description="Stable component identity.",
    )
    versioning: VersioningConfig = Field(
        default_factory=VersioningConfig,
        description="Version and final-tag naming policy.",
    )
    source: SourceConfig = Field(description="Source selection and snapshot policy.")
    lifecycle: LifecycleConfig = Field(description="Direct or candidate release lifecycle.")
    candidate: CandidateConfig | None = Field(
        default=None,
        description="Candidate policy required only for the candidate lifecycle.",
    )
    artifacts: ArtifactPolicyConfig = Field(
        default_factory=ArtifactPolicyConfig,
        description="Produced artifact and checksum policy.",
    )
    publication: PublicationConfig = Field(
        description="Authoritative and additional publication targets.",
    )
    tags: TagPolicyConfig = Field(
        default_factory=TagPolicyConfig,
        description="Immutable and moving tag policy.",
    )
    vote_materials: VoteMaterialsConfig | None = Field(
        default=None,
        description="Optional vote-material policy for an exact candidate.",
    )
    policy_profiles: PolicyProfilesConfig = Field(
        default_factory=PolicyProfilesConfig,
        description="Explicit foundation-specific policy profiles.",
    )
    verification: VerifyRcConfig | None = Field(
        default=None,
        description="Artifact verification and reproducibility policy.",
    )

    @model_validator(mode="after")
    def _validate_capability_composition(self) -> ReleaseConfig:
        candidate_mode = self.lifecycle.mode == "candidate"
        if candidate_mode != (self.candidate is not None):
            raise ValueError(
                "candidate config must be present exactly when lifecycle.mode is candidate"
            )
        if not candidate_mode and self.vote_materials is not None:
            raise ValueError("vote_materials requires lifecycle.mode candidate")

        targets = (
            self.publication.authoritative,
            *self.publication.convenience,
        )
        requires_asf = any(target.kind == "asf-dist-svn" for target in targets) or (
            self.vote_materials is not None and self.vote_materials.profile == "asf"
        )
        if requires_asf and self.policy_profiles.asf is None:
            raise ValueError(
                "ASF publication or vote materials require policy_profiles.asf"
            )
        if any(target.kind == "asf-dist-svn" for target in targets) and not isinstance(
            self.source.snapshot, BuiltSourceSnapshotConfig
        ):
            raise ValueError("ASF dist publication requires source.snapshot.mode built-asset")
        return self


class CommandContext(RuntimeDerivedModel):
    """Common runtime context passed into command handlers."""

    release_config: ReleaseConfig = Field(
        description="Validated release configuration for the current command.",
    )
    release_config_path: Path | None = Field(
        default=None,
        description="Filesystem path of the authored release configuration.",
    )


def load_release_config(release_config_path: str) -> ReleaseConfig:
    """Load one required component-authored release configuration file."""

    path = Path(release_config_path)
    payload = read_yaml_mapping_file_bounded(path, max_bytes=DEFAULT_CONFIG_PARSE_MAX_BYTES)
    return ReleaseConfig.model_validate(payload)


def load_verification_override_config(override_config_path: str) -> VerifyRcOverrideConfig:
    """Load one local non-canonical reproducibility override file from YAML."""

    path = Path(override_config_path)
    payload = read_yaml_mapping_file_bounded(path, max_bytes=DEFAULT_CONFIG_PARSE_MAX_BYTES)
    return VerifyRcOverrideFileConfig.model_validate(payload).verify_rc


def validate_selected_release_targets(
    release_config: ReleaseConfig,
    *,
    allow_test_targets: bool,
) -> None:
    """Validate only the external targets selected by the effective configuration."""

    asf_profile = release_config.policy_profiles.asf
    if asf_profile is not None:
        validate_asf_dist_urls(asf_profile, allow_test_targets=allow_test_targets)


def require_asf_profile(release_config: ReleaseConfig) -> AsfReleaseProfileConfig:
    """Return the selected ASF profile or reject an ASF-only command."""

    profile = release_config.policy_profiles.asf
    if profile is None:
        raise ValueError("this command requires policy_profiles.asf")
    return profile


def require_candidate_config(release_config: ReleaseConfig) -> CandidateConfig:
    """Return candidate policy or reject a candidate-only command."""

    candidate = release_config.candidate
    if candidate is None:
        raise ValueError("this command requires lifecycle.mode candidate")
    return candidate


def require_built_source_snapshot(
    release_config: ReleaseConfig,
) -> BuiltSourceSnapshotConfig:
    """Return built-source policy or reject a source-archive-only command."""

    snapshot = release_config.source.snapshot
    if not isinstance(snapshot, BuiltSourceSnapshotConfig):
        raise ValueError("this command requires source.snapshot.mode built-asset")
    return snapshot


def require_vote_materials(release_config: ReleaseConfig) -> VoteMaterialsConfig:
    """Return vote-material policy or reject a vote-only command."""

    vote_materials = release_config.vote_materials
    if vote_materials is None:
        raise ValueError("this command requires vote_materials")
    return vote_materials


def secondary_target_kinds(release_config: ReleaseConfig) -> list[str]:
    """Return selected secondary publication discriminator values."""

    return [target.kind for target in release_config.publication.secondary]


def moving_tags_enabled(release_config: ReleaseConfig) -> bool:
    """Return whether any moving tag policy is enabled."""

    return bool(release_config.tags.moving)


def latest_tag_enabled(release_config: ReleaseConfig) -> bool:
    """Return whether the explicit `latest` moving tag is enabled."""

    return "latest" in release_config.tags.moving


ReleaseConfig.schema_export = SchemaExportSpecification(
    filename="component-config.schema.json",
    file_path="release-config.yaml",
    summary=(
        "Component-authored `release-config.yaml` contract for release policy "
        "and target integration settings."
    ),
)
CommandContext.schema_export = SchemaExportSpecification(
    filename="command-context.schema.json",
    audience="internal",
    stability="stable",
    summary="Runtime command context built from validated release configuration.",
)
