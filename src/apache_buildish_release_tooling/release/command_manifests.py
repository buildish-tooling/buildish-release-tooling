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

"""Typed emitted command-manifest contracts written by release-tooling commands."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from apache_buildish_release_tooling.docs.documentation import ToolingDerivedModel as BuildishContractModel

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CommandActionManifest(BuildishContractModel):
    """Common top-level shape for command action manifests."""

    component: NonEmptyString = Field(description="Component identifier for the Buildish command manifest or emitted action record.")
    action: NonEmptyString = Field(description="Stable command action identifier written by one Buildish command manifest.")


class CreateReleaseBranchManifest(CommandActionManifest):
    """Action manifest emitted after resolving or creating a release branch."""

    action: Literal["create-release-branch"] = Field(default="create-release-branch", description="Stable command action identifier written by one Buildish command manifest.")
    release_line: NonEmptyString = Field(description="Maintenance-line identifier used to group related versions, branches, and moving tags.")
    release_branch: NonEmptyString = Field(description="Git branch name that Buildish resolved as the authoritative release branch.")
    source_ref: NonEmptyString = Field(description="Source ref that Buildish used as the starting point for the related release-branch or materialization action.")


class PrepareRcManifest(CommandActionManifest):
    """Action manifest emitted after prepare-rc resolves one RC workflow state bundle."""

    action: Literal["prepare-rc"] = Field(default="prepare-rc", description="Stable command action identifier written by one Buildish command manifest.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    resolved_source_ref: NonEmptyString = Field(description="Resolved source Git commit SHA that Buildish selected for release production or verification.")
    source_date_epoch: NonEmptyString = Field(description="Canonical `SOURCE_DATE_EPOCH` integer carried through RC production and verification.")
    resolved_release_branch: NonEmptyString = Field(description="Release branch name that Buildish resolved for the selected version.")
    rc_number: NonEmptyString = Field(description="Numeric RC sequence selected for the related version.")
    rc_tag: NonEmptyString = Field(description="Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix.")
    final_tag: NonEmptyString = Field(description="Final immutable Git tag that Buildish intends to publish for the released version.")
    source_artifact_name: NonEmptyString = Field(description="Filename of the staged source release artifact.")
    source_artifact_root_name: NonEmptyString = Field(description="Root directory name that the source release archive should unpack to.")
    source_artifact_prefix_path: NonEmptyString = Field(description="Top-level path prefix inside the source release archive.")
    staging_url: NonEmptyString = Field(description="ASF dev/dist staging directory URL selected for the current RC.")
    cleanup_existing_rc_staging: Literal["true"] = Field(default="true", description="Whether the prepare-rc flow cleaned up pre-existing same-version RC staging state before publishing new materials.")
    draft_release_action: Literal["recreate"] = Field(default="recreate", description="Draft GitHub release convergence action that prepare-rc used when emitting new vote materials.")
    final_tag_mode: NonEmptyString = Field(description="Configured or recorded policy describing how the final immutable release tag should be created for this component or release run.")


class CleanupDevSvnRcsManifest(CommandActionManifest):
    """Action manifest emitted after old or conflicting RC staging directories are removed."""

    action: Literal["cleanup-dev-svn-rcs"] = Field(default="cleanup-dev-svn-rcs", description="Stable command action identifier written by one Buildish command manifest.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    dev_base_url: NonEmptyString = Field(description="Configured ASF `dist/dev` base URL that the cleanup or publication action targeted.")
    deleted_rc_directories: list[NonEmptyString] = Field(description="ASF dev/dist RC directories that Buildish deleted during cleanup.")


class CreateSourceArtifactManifest(CommandActionManifest):
    """Action manifest emitted after creating one local source release artifact."""

    action: Literal["create-source-artifact"] = Field(default="create-source-artifact", description="Stable command action identifier written by one Buildish command manifest.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    resolved_source_ref: NonEmptyString = Field(description="Resolved source Git commit SHA that Buildish selected for release production or verification.")
    source_date_epoch: NonEmptyString = Field(description="Canonical `SOURCE_DATE_EPOCH` integer carried through RC production and verification.")
    source_artifact_name: NonEmptyString = Field(description="Filename of the staged source release artifact.")
    source_artifact_path: NonEmptyString = Field(description="Filesystem path of the locally produced or staged source release artifact.")
    source_artifact_sha512: NonEmptyString = Field(description="SHA-512 digest of the staged or locally produced source release artifact.")


class BuildSourceRcManifest(CommandActionManifest):
    """Action manifest emitted after building and staging the signed source RC bundle."""

    action: Literal["build-source-rc"] = Field(default="build-source-rc", description="Stable command action identifier written by one Buildish command manifest.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    resolved_source_ref: NonEmptyString = Field(description="Resolved source Git commit SHA that Buildish selected for release production or verification.")
    source_date_epoch: NonEmptyString = Field(description="Canonical `SOURCE_DATE_EPOCH` integer carried through RC production and verification.")
    rc_tag: NonEmptyString = Field(description="Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix.")
    source_artifact_name: NonEmptyString = Field(description="Filename of the staged source release artifact.")
    source_artifact_path: NonEmptyString = Field(description="Filesystem path of the locally produced or staged source release artifact.")
    source_artifact_sha512: NonEmptyString = Field(description="SHA-512 digest of the staged or locally produced source release artifact.")
    source_artifact_sha512_path: NonEmptyString = Field(description="Filesystem path of the `.sha512` sidecar generated for the locally produced source artifact.")
    source_artifact_asc_path: NonEmptyString = Field(description="Filesystem path of the detached OpenPGP signature file for the locally produced source artifact.")
    staging_url: NonEmptyString = Field(description="ASF dev/dist staging directory URL selected for the current RC.")


class MaterializeRcGitContentManifest(CommandActionManifest):
    """Action manifest emitted after building detached RC materialization Git content."""

    action: Literal["materialize-rc-git-content"] = Field(default="materialize-rc-git-content", description="Stable command action identifier written by one Buildish command manifest.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    resolved_source_ref: NonEmptyString = Field(description="Resolved source Git commit SHA that Buildish selected for release production or verification.")
    rc_tag: NonEmptyString = Field(description="Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix.")
    materialized_paths: list[NonEmptyString] = Field(description="Filesystem paths that the materialization step created or refreshed for the current RC.")
    materialized_commit_sha: NonEmptyString = Field(description="Git commit SHA of the materialized tree that Buildish created for the RC tagging workflow.")
    materialized_ref_name: NonEmptyString = Field(description="Temporary Git ref name that Buildish created or reused for RC materialization.")
    materialized_ref_mode: NonEmptyString = Field(description="Policy that Buildish used when creating or reusing the temporary materialization ref.")


class CreateRcMaterializationTagManifest(CommandActionManifest):
    """Action manifest emitted after tagging one detached RC materialization commit."""

    action: Literal["create-rc-materialization-tag"] = Field(default="create-rc-materialization-tag", description="Stable command action identifier written by one Buildish command manifest.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    resolved_source_ref: NonEmptyString = Field(description="Resolved source Git commit SHA that Buildish selected for release production or verification.")
    rc_tag: NonEmptyString = Field(description="Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix.")
    target_commit: NonEmptyString = Field(description="Git commit SHA that the related tag or alias operation targeted.")
    tag_target_origin: Literal["materialized-commit", "source-commit"] = Field(description="Origin that Buildish used for the target commit when tagging the RC materialization result.")
    cleanup_materialized_ref_name: str = Field(description="Temporary materialization ref that Buildish considered for cleanup after tagging the RC.")
    cleanup_materialized_ref_mode: NonEmptyString = Field(description="Policy that Buildish used when deciding whether to delete the temporary materialization ref after tagging.")
    tag_creation_mode: NonEmptyString = Field(description="Mode that Buildish used when creating or reusing the related annotated Git tag.")
    created_ref: str = Field(description="Git ref name that Buildish created or reused while performing the related tag or ref action.")


class RecordArtifactManifest(CommandActionManifest):
    """Action manifest emitted after writing one typed secondary-artifact bundle."""

    action: Literal["record-artifact"] = Field(default="record-artifact", description="Stable command action identifier written by one Buildish command manifest.")
    artifact_id: NonEmptyString = Field(description="Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling.")
    kind: NonEmptyString = Field(description="Declared artifact or report kind discriminator.")
    artifact_manifest_path: NonEmptyString = Field(description="Filesystem path to the emitted secondary-artifact manifest fragment.")
    artifact_bundle_dir: NonEmptyString = Field(description="Directory that contains one emitted secondary-artifact registration bundle.")
    inventory_paths: list[NonEmptyString] = Field(description="Filesystem paths of supplemental inventory files emitted alongside one artifact bundle.")


class FinalizeRcVoteMaterialsManifest(CommandActionManifest):
    """Action manifest emitted after publishing and signing final RC vote materials."""

    action: Literal["finalize-rc-vote-materials"] = Field(default="finalize-rc-vote-materials", description="Stable command action identifier written by one Buildish command manifest.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    resolved_source_ref: NonEmptyString = Field(description="Resolved source Git commit SHA that Buildish selected for release production or verification.")
    rc_tag: NonEmptyString = Field(description="Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix.")
    final_tag: NonEmptyString = Field(description="Final immutable Git tag that Buildish intends to publish for the released version.")
    rc_tag_target_commit: NonEmptyString = Field(description="Git commit SHA that the RC tag resolved to during verification or publication.")
    source_artifact_url: NonEmptyString = Field(description="Canonical staged download URL of the source release artifact referenced by the RC vote materials.")
    authoritative_manifest_url: NonEmptyString = Field(description="Canonical staged URL of the signed RC vote manifest.")
    authoritative_manifest_sha512: NonEmptyString = Field(description="SHA-512 digest of the authoritative staged RC vote manifest.")
    bootstrap_script_url: NonEmptyString = Field(description="Staged URL of the emitted verify-rc bootstrap helper script.")
    bootstrap_script_sha512: NonEmptyString = Field(description="SHA-512 digest of the emitted verify-rc bootstrap script.")
    draft_release_url: NonEmptyString = Field(description="GitHub draft release URL associated with the current RC or final release workflow.")
    secondary_artifact_count: NonEmptyString = Field(description="Count of secondary artifacts associated with the related manifest or publication step.")
    mirrored_asset_names: list[NonEmptyString] = Field(description="GitHub release asset names that Buildish mirrored from the staged vote materials into the draft release bundle.")
    gpg_fingerprint: NonEmptyString = Field(description="OpenPGP fingerprint of the signing key Buildish used or verified.")


class PublishAtrCandidateManifest(CommandActionManifest):
    """Action manifest emitted after publishing one release candidate to ATR."""

    action: Literal["publish-atr-candidate"] = Field(default="publish-atr-candidate", description="Stable command action identifier written by one Buildish command manifest.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    rc_tag: NonEmptyString = Field(description="Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix.")
    atr_base_url: NonEmptyString = Field(description="Base ATR service URL that Buildish used for the related candidate upload or status query.")
    atr_committee: NonEmptyString = Field(description="ASF committee slug that Buildish reported to ATR for the related release candidate.")
    atr_project: NonEmptyString = Field(description="ATR project or product-line identifier that Buildish reported for the related release candidate.")
    atr_release_mode: NonEmptyString = Field(description="ATR release mode that Buildish selected for the related publication run.")
    atr_phase: NonEmptyString = Field(description="ATR publication phase that Buildish targeted or reported for the related candidate.")
    atr_latest_revision: str = Field(description="Most recent ATR candidate revision known to Buildish when it emitted the related manifest or report.")
    uploaded_file_names: list[NonEmptyString] = Field(description="File names that Buildish uploaded to ATR for the related candidate.")
    waited_for_checks: Literal["true", "false"] = Field(description="Whether Buildish waited for ATR checks to complete before emitting the related command manifest.")
    atr_total_checks: NonEmptyString = Field(description="Total number of ATR checks observed for the related candidate revision.")
    atr_failure_count: NonEmptyString = Field(description="Number of ATR checks that reported a failing outcome for the related candidate or report.")
    atr_exception_count: NonEmptyString = Field(description="Number of ATR checks that ended in an exception state for the related candidate or report.")
    atr_warning_count: NonEmptyString = Field(description="Number of ATR checks that reported warnings for the related candidate or report.")


class ReportAtrChecksManifest(CommandActionManifest):
    """Action manifest emitted after summarizing ATR checks for one candidate revision."""

    action: Literal["report-atr-checks"] = Field(default="report-atr-checks", description="Stable command action identifier written by one Buildish command manifest.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    rc_tag: NonEmptyString = Field(description="Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix.")
    atr_base_url: NonEmptyString = Field(description="Base ATR service URL that Buildish used for the related candidate upload or status query.")
    atr_committee: NonEmptyString = Field(description="ASF committee slug that Buildish reported to ATR for the related release candidate.")
    atr_project: NonEmptyString = Field(description="ATR project or product-line identifier that Buildish reported for the related release candidate.")
    atr_phase: NonEmptyString = Field(description="ATR publication phase that Buildish targeted or reported for the related candidate.")
    atr_latest_revision: str = Field(description="Most recent ATR candidate revision known to Buildish when it emitted the related manifest or report.")
    atr_reported_revision: str = Field(description="ATR candidate revision that Buildish specifically reported in the related checks summary.")
    atr_total_checks: NonEmptyString = Field(description="Total number of ATR checks observed for the related candidate revision.")
    atr_failure_count: NonEmptyString = Field(description="Number of ATR checks that reported a failing outcome for the related candidate or report.")
    atr_exception_count: NonEmptyString = Field(description="Number of ATR checks that ended in an exception state for the related candidate or report.")
    atr_warning_count: NonEmptyString = Field(description="Number of ATR checks that reported warnings for the related candidate or report.")
    atr_success_count: NonEmptyString = Field(description="Number of ATR checks that reported success for the related candidate or report.")
    strict_checking: Literal["true", "false"] = Field(description="Whether the related check or reporting step should fail the command when warnings or failures are present.")
    would_block_release: Literal["true", "false"] = Field(description="Whether the related check result would block release publication under the requested strictness policy.")


class SyncDraftGithubReleaseManifest(CommandActionManifest):
    """Action manifest emitted after synchronizing the draft GitHub release with staged RC artifacts."""

    action: Literal["sync-draft-github-release"] = Field(default="sync-draft-github-release", description="Stable command action identifier written by one Buildish command manifest.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    repository_slug: NonEmptyString = Field(description="GitHub `owner/name` repository slug used for API calls and emitted release metadata.")
    resolved_source_ref: NonEmptyString = Field(description="Resolved source Git commit SHA that Buildish selected for release production or verification.")
    rc_tag: NonEmptyString = Field(description="Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix.")
    final_tag: NonEmptyString = Field(description="Final immutable Git tag that Buildish intends to publish for the released version.")
    staging_url: NonEmptyString = Field(description="ASF dev/dist staging directory URL selected for the current RC.")
    deleted_release_ids: list[NonEmptyString] = Field(description="GitHub draft release ids that Buildish deleted while converging on one selected release candidate.")
    release_id: str = Field(description="GitHub release id associated with the related draft or final release record.")
    release_tag: str = Field(description="GitHub release tag name as stored on the related release record.")
    release_name: str = Field(description="Human-facing GitHub release title used for the related draft or final release.")
    release_url: NonEmptyString = Field(description="Primary user-facing URL of the related GitHub release or published release artifact.")
    sync_mode: NonEmptyString = Field(description="Mode that Buildish used when reconciling the selected draft GitHub release with staged RC materials.")


class PublishSourceReleaseSvnManifest(CommandActionManifest):
    """Action manifest emitted after promoting a verified source artifact into dist/release."""

    action: Literal["publish-source-release-svn"] = Field(default="publish-source-release-svn", description="Stable command action identifier written by one Buildish command manifest.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    selected_rc_tag: NonEmptyString = Field(description="RC tag that Buildish selected as the winning release candidate for a final release action.")
    source_url: NonEmptyString = Field(description="Source URL that Buildish copied or verified during a publication action.")
    target_url: NonEmptyString = Field(description="Destination URL that Buildish published or copied content to.")
    verified_source_artifact_sha512: NonEmptyString = Field(description="Verified SHA-512 digest of the source release artifact promoted to ASF dist/release.")
    publish_mode: NonEmptyString = Field(description="Mode that Buildish used when publishing the verified source artifact to ASF `dist/release`.")


class PruneOlderLineReleasesManifest(CommandActionManifest):
    """Action manifest emitted after pruning older same-line releases from dist/release."""

    action: Literal["prune-older-line-releases"] = Field(default="prune-older-line-releases", description="Stable command action identifier written by one Buildish command manifest.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    release_line: NonEmptyString = Field(description="Maintenance-line identifier used to group related versions, branches, and moving tags.")
    pruned_versions: list[NonEmptyString] = Field(description="Older release versions that Buildish removed from the active release line while pruning prior dist/release artifacts.")
    release_base_url: NonEmptyString = Field(description="Base ASF dist/release URL associated with the related publication action.")


class CreateFinalTagManifest(CommandActionManifest):
    """Action manifest emitted after creating or validating the final immutable release tag."""

    action: Literal["create-final-tag"] = Field(default="create-final-tag", description="Stable command action identifier written by one Buildish command manifest.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    selected_rc_tag: NonEmptyString = Field(description="RC tag that Buildish selected as the winning release candidate for a final release action.")
    final_tag: NonEmptyString = Field(description="Final immutable Git tag that Buildish intends to publish for the released version.")
    target_commit: NonEmptyString = Field(description="Git commit SHA that the related tag or alias operation targeted.")
    tag_creation_mode: NonEmptyString = Field(description="Mode that Buildish used when creating or reusing the related annotated Git tag.")
    created_ref: str = Field(description="Git ref name that Buildish created or reused while performing the related tag or ref action.")


class FinalizeDraftGithubReleaseManifest(CommandActionManifest):
    """Action manifest emitted after finalizing a selected GitHub draft release."""

    action: Literal["finalize-draft-github-release"] = Field(default="finalize-draft-github-release", description="Stable command action identifier written by one Buildish command manifest.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    repository_slug: NonEmptyString = Field(description="GitHub `owner/name` repository slug used for API calls and emitted release metadata.")
    release_id: NonEmptyString = Field(description="GitHub release id associated with the related draft or final release record.")
    release_tag: str = Field(description="GitHub release tag name as stored on the related release record.")
    release_name: str = Field(description="Human-facing GitHub release title used for the related draft or final release.")
    release_url: NonEmptyString = Field(description="Primary user-facing URL of the related GitHub release or published release artifact.")
    deleted_asset_names: list[NonEmptyString] = Field(description="GitHub Release asset names that Buildish deleted during the related release-finalization step.")
    finalize_mode: NonEmptyString = Field(description="Mode that Buildish used when finalizing the selected draft GitHub release.")


class ReleaseVersionManifest(CommandActionManifest):
    """Action manifest emitted after a full release-version orchestration run completes."""

    action: Literal["release-version"] = Field(default="release-version", description="Stable command action identifier written by one Buildish command manifest.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    release_line: NonEmptyString = Field(description="Maintenance-line identifier used to group related versions, branches, and moving tags.")
    selected_rc_tag: NonEmptyString = Field(description="RC tag that Buildish selected as the winning release candidate for a final release action.")
    final_tag: NonEmptyString = Field(description="Final immutable Git tag that Buildish intends to publish for the released version.")
    archive_versions: list[NonEmptyString] = Field(description="Older same-line release versions that Buildish resolved for archival pruning.")
    release_url: NonEmptyString = Field(description="Primary user-facing URL of the related GitHub release or published release artifact.")
    moving_tags: list[NonEmptyString] = Field(description="Derived moving tags or aliases that should point at the final released version.")
    final_tag_mode: NonEmptyString = Field(description="Configured or recorded policy describing how the final immutable release tag should be created for this component or release run.")


class UpdateMovingTagsManifest(CommandActionManifest):
    """Action manifest emitted after updating moving Git tags for a final release."""

    action: Literal["update-moving-tags"] = Field(default="update-moving-tags", description="Stable command action identifier written by one Buildish command manifest.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    final_tag: NonEmptyString = Field(description="Final immutable Git tag that Buildish intends to publish for the released version.")
    target_commit: NonEmptyString = Field(description="Git commit SHA that the related tag or alias operation targeted.")
    updated_tags: list[NonEmptyString] = Field(description="Moving tags that Buildish updated during the related tag-publication action.")
    skipped_tags: list[NonEmptyString] = Field(description="Moving tags that Buildish intentionally left unchanged during the related update operation.")
    tag_update_modes: list[NonEmptyString] = Field(description="Per-tag update outcomes describing how each moving tag was handled during the related publication run.")


class UpdateMovingImageAliasesManifest(CommandActionManifest):
    """Action manifest emitted after resolving moving OCI image aliases for publication."""

    action: Literal["update-moving-image-aliases"] = Field(default="update-moving-image-aliases", description="Stable command action identifier written by one Buildish command manifest.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    exact_image_tag: NonEmptyString = Field(description="Exact released image tag that Buildish uses as the source for moving image aliases.")
    image_aliases: list[NonEmptyString] = Field(description="Derived moving container tags that should point at the exact released image tag.")


class PublishDockerhubMovingTagsManifest(CommandActionManifest):
    """Action manifest emitted after publishing moving Docker Hub image aliases."""

    action: Literal["publish-dockerhub-moving-tags"] = Field(default="publish-dockerhub-moving-tags", description="Stable command action identifier written by one Buildish command manifest.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    source_image: NonEmptyString = Field(description="Exact source OCI image reference that should be copied to produce the published moving aliases.")
    image_repository: NonEmptyString = Field(description="Container image repository name without the moving tag or digest suffix.")
    published_alias_refs: list[NonEmptyString] = Field(description="Fully qualified target image references that Buildish published as moving aliases.")


class AttachGithubReleaseAssetsManifest(CommandActionManifest):
    """Action manifest emitted after uploading primary and derived assets to a GitHub release."""

    action: Literal["attach-github-release-assets"] = Field(default="attach-github-release-assets", description="Stable command action identifier written by one Buildish command manifest.")
    version: NonEmptyString = Field(description="Release version string without a leading `v` prefix.")
    repository_slug: NonEmptyString = Field(description="GitHub `owner/name` repository slug used for API calls and emitted release metadata.")
    release_id: NonEmptyString = Field(description="GitHub release id associated with the related draft or final release record.")
    release_name: str = Field(description="Human-facing GitHub release title used for the related draft or final release.")
    release_tag: str = Field(description="GitHub release tag name as stored on the related release record.")
    release_url: NonEmptyString = Field(description="Primary user-facing URL of the related GitHub release or published release artifact.")
    primary_asset_names: list[NonEmptyString] = Field(description="Primary release asset names that Buildish attached or expected to attach to the selected GitHub release.")
    uploaded_asset_names: list[NonEmptyString] = Field(description="GitHub release asset names that Buildish uploaded during the related command.")
    generated_checksum_asset_names: list[NonEmptyString] = Field(description="Generated checksum asset names that Buildish attached or expected to attach to the GitHub release.")
    generated_signature_asset_names: list[NonEmptyString] = Field(description="Generated detached-signature asset names that Buildish attached or expected to attach to the GitHub release.")
    checksum_algorithms: list[NonEmptyString] = Field(description="Checksum algorithms that Buildish generated or expects for the related artifact set.")
    gpg_fingerprint: str = Field(description="OpenPGP fingerprint of the signing key Buildish used or verified.")
