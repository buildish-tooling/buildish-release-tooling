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

from pydantic import StringConstraints

from apache_buildish_release_tooling.contracts import BuildishContractModel

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CommandActionManifest(BuildishContractModel):
    """Common top-level shape for command action manifests."""

    component: NonEmptyString
    action: NonEmptyString


class CreateReleaseBranchManifest(CommandActionManifest):
    action: Literal["create-release-branch"] = "create-release-branch"
    release_line: NonEmptyString
    release_branch: NonEmptyString
    source_ref: NonEmptyString


class PrepareRcManifest(CommandActionManifest):
    action: Literal["prepare-rc"] = "prepare-rc"
    version: NonEmptyString
    resolved_source_ref: NonEmptyString
    source_date_epoch: NonEmptyString
    resolved_release_branch: NonEmptyString
    rc_number: NonEmptyString
    rc_tag: NonEmptyString
    final_tag: NonEmptyString
    source_artifact_name: NonEmptyString
    source_artifact_root_name: NonEmptyString
    source_artifact_prefix_path: NonEmptyString
    staging_url: NonEmptyString
    cleanup_existing_rc_staging: Literal["true"] = "true"
    draft_release_action: Literal["recreate"] = "recreate"
    final_tag_mode: NonEmptyString


class CleanupDevSvnRcsManifest(CommandActionManifest):
    action: Literal["cleanup-dev-svn-rcs"] = "cleanup-dev-svn-rcs"
    version: NonEmptyString
    dev_base_url: NonEmptyString
    deleted_rc_directories: list[NonEmptyString]


class CreateSourceArtifactManifest(CommandActionManifest):
    action: Literal["create-source-artifact"] = "create-source-artifact"
    version: NonEmptyString
    resolved_source_ref: NonEmptyString
    source_date_epoch: NonEmptyString
    source_artifact_name: NonEmptyString
    source_artifact_path: NonEmptyString
    source_artifact_sha512: NonEmptyString


class BuildSourceRcManifest(CommandActionManifest):
    action: Literal["build-source-rc"] = "build-source-rc"
    version: NonEmptyString
    resolved_source_ref: NonEmptyString
    source_date_epoch: NonEmptyString
    rc_tag: NonEmptyString
    source_artifact_name: NonEmptyString
    source_artifact_path: NonEmptyString
    source_artifact_sha512: NonEmptyString
    source_artifact_sha512_path: NonEmptyString
    source_artifact_asc_path: NonEmptyString
    staging_url: NonEmptyString


class MaterializeRcGitContentManifest(CommandActionManifest):
    action: Literal["materialize-rc-git-content"] = "materialize-rc-git-content"
    version: NonEmptyString
    resolved_source_ref: NonEmptyString
    rc_tag: NonEmptyString
    materialized_paths: list[NonEmptyString]
    materialized_commit_sha: NonEmptyString
    materialized_ref_name: NonEmptyString
    materialized_ref_mode: NonEmptyString


class CreateRcMaterializationTagManifest(CommandActionManifest):
    action: Literal["create-rc-materialization-tag"] = "create-rc-materialization-tag"
    version: NonEmptyString
    resolved_source_ref: NonEmptyString
    rc_tag: NonEmptyString
    target_commit: NonEmptyString
    tag_target_origin: Literal["materialized-commit", "source-commit"]
    cleanup_materialized_ref_name: str
    cleanup_materialized_ref_mode: NonEmptyString
    tag_creation_mode: NonEmptyString
    created_ref: str


class RecordArtifactManifest(CommandActionManifest):
    action: Literal["record-artifact"] = "record-artifact"
    artifact_id: NonEmptyString
    kind: NonEmptyString
    artifact_manifest_path: NonEmptyString
    artifact_bundle_dir: NonEmptyString
    inventory_paths: list[NonEmptyString]


class FinalizeRcVoteMaterialsManifest(CommandActionManifest):
    action: Literal["finalize-rc-vote-materials"] = "finalize-rc-vote-materials"
    version: NonEmptyString
    resolved_source_ref: NonEmptyString
    rc_tag: NonEmptyString
    final_tag: NonEmptyString
    rc_tag_target_commit: NonEmptyString
    source_artifact_url: NonEmptyString
    authoritative_manifest_url: NonEmptyString
    authoritative_manifest_sha512: NonEmptyString
    bootstrap_script_url: NonEmptyString
    bootstrap_script_sha512: NonEmptyString
    draft_release_url: NonEmptyString
    secondary_artifact_count: NonEmptyString
    mirrored_asset_names: list[NonEmptyString]
    gpg_fingerprint: NonEmptyString


class PublishAtrCandidateManifest(CommandActionManifest):
    action: Literal["publish-atr-candidate"] = "publish-atr-candidate"
    version: NonEmptyString
    rc_tag: NonEmptyString
    atr_base_url: NonEmptyString
    atr_committee: NonEmptyString
    atr_project: NonEmptyString
    atr_release_mode: NonEmptyString
    atr_phase: NonEmptyString
    atr_latest_revision: str
    uploaded_file_names: list[NonEmptyString]
    waited_for_checks: Literal["true", "false"]
    atr_total_checks: NonEmptyString
    atr_failure_count: NonEmptyString
    atr_exception_count: NonEmptyString
    atr_warning_count: NonEmptyString


class ReportAtrChecksManifest(CommandActionManifest):
    action: Literal["report-atr-checks"] = "report-atr-checks"
    version: NonEmptyString
    rc_tag: NonEmptyString
    atr_base_url: NonEmptyString
    atr_committee: NonEmptyString
    atr_project: NonEmptyString
    atr_phase: NonEmptyString
    atr_latest_revision: str
    atr_reported_revision: str
    atr_total_checks: NonEmptyString
    atr_failure_count: NonEmptyString
    atr_exception_count: NonEmptyString
    atr_warning_count: NonEmptyString
    atr_success_count: NonEmptyString
    strict_checking: Literal["true", "false"]
    would_block_release: Literal["true", "false"]


class SyncDraftGithubReleaseManifest(CommandActionManifest):
    action: Literal["sync-draft-github-release"] = "sync-draft-github-release"
    version: NonEmptyString
    repository_slug: NonEmptyString
    resolved_source_ref: NonEmptyString
    rc_tag: NonEmptyString
    final_tag: NonEmptyString
    staging_url: NonEmptyString
    deleted_release_ids: list[NonEmptyString]
    release_id: str
    release_tag: str
    release_name: str
    release_url: NonEmptyString
    sync_mode: NonEmptyString


class PublishSourceReleaseSvnManifest(CommandActionManifest):
    action: Literal["publish-source-release-svn"] = "publish-source-release-svn"
    version: NonEmptyString
    selected_rc_tag: NonEmptyString
    source_url: NonEmptyString
    target_url: NonEmptyString
    verified_source_artifact_sha512: NonEmptyString
    publish_mode: NonEmptyString


class PruneOlderLineReleasesManifest(CommandActionManifest):
    action: Literal["prune-older-line-releases"] = "prune-older-line-releases"
    version: NonEmptyString
    release_line: NonEmptyString
    pruned_versions: list[NonEmptyString]
    release_base_url: NonEmptyString


class CreateFinalTagManifest(CommandActionManifest):
    action: Literal["create-final-tag"] = "create-final-tag"
    version: NonEmptyString
    selected_rc_tag: NonEmptyString
    final_tag: NonEmptyString
    target_commit: NonEmptyString
    tag_creation_mode: NonEmptyString
    created_ref: str


class FinalizeDraftGithubReleaseManifest(CommandActionManifest):
    action: Literal["finalize-draft-github-release"] = "finalize-draft-github-release"
    version: NonEmptyString
    repository_slug: NonEmptyString
    release_id: NonEmptyString
    release_tag: str
    release_name: str
    release_url: NonEmptyString
    deleted_asset_names: list[NonEmptyString]
    finalize_mode: NonEmptyString


class ReleaseVersionManifest(CommandActionManifest):
    action: Literal["release-version"] = "release-version"
    version: NonEmptyString
    release_line: NonEmptyString
    selected_rc_tag: NonEmptyString
    final_tag: NonEmptyString
    archive_versions: list[NonEmptyString]
    release_url: NonEmptyString
    moving_tags: list[NonEmptyString]
    final_tag_mode: NonEmptyString


class UpdateMovingTagsManifest(CommandActionManifest):
    action: Literal["update-moving-tags"] = "update-moving-tags"
    version: NonEmptyString
    final_tag: NonEmptyString
    target_commit: NonEmptyString
    updated_tags: list[NonEmptyString]
    skipped_tags: list[NonEmptyString]
    tag_update_modes: list[NonEmptyString]


class UpdateMovingImageAliasesManifest(CommandActionManifest):
    action: Literal["update-moving-image-aliases"] = "update-moving-image-aliases"
    version: NonEmptyString
    exact_image_tag: NonEmptyString
    image_aliases: list[NonEmptyString]


class PublishDockerhubMovingTagsManifest(CommandActionManifest):
    action: Literal["publish-dockerhub-moving-tags"] = "publish-dockerhub-moving-tags"
    version: NonEmptyString
    source_image: NonEmptyString
    image_repository: NonEmptyString
    published_alias_refs: list[NonEmptyString]


class AttachGithubReleaseAssetsManifest(CommandActionManifest):
    action: Literal["attach-github-release-assets"] = "attach-github-release-assets"
    version: NonEmptyString
    repository_slug: NonEmptyString
    release_id: NonEmptyString
    release_name: str
    release_tag: str
    release_url: NonEmptyString
    primary_asset_names: list[NonEmptyString]
    uploaded_asset_names: list[NonEmptyString]
    generated_checksum_asset_names: list[NonEmptyString]
    generated_signature_asset_names: list[NonEmptyString]
    checksum_algorithms: list[NonEmptyString]
    gpg_fingerprint: str
