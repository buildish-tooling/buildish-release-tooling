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

"""Draft-release, publication, and release-state commands."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from apache_buildish_release_tooling.release.asf_svn import AsfSvnClient, url_join
from apache_buildish_release_tooling.release.command_manifests import (
    CreateFinalTagManifest,
    FinalizeDraftGithubReleaseManifest,
    PruneOlderLineReleasesManifest,
    PublishSourceReleaseSvnManifest,
    ReleaseVersionManifest,
    SyncDraftGithubReleaseManifest,
)
from apache_buildish_release_tooling.release.email_templates import (
    render_announce_email,
    render_project_vote_result_email,
)
from apache_buildish_release_tooling.release.git_repo import GitRepository
from apache_buildish_release_tooling.release.github_checks import resolve_repository_slug
from apache_buildish_release_tooling.release.github_release_selection import (
    asset_release_url,
    matching_draft_releases,
    plan_draft_release_sync,
    selected_github_release,
    upsert_draft_release,
)
from apache_buildish_release_tooling.release.github_release_text import render_draft_github_release_body
from apache_buildish_release_tooling.release.github_releases import (
    delete_release,
    delete_release_asset,
    list_releases,
    release_asset_ids_by_names,
    update_release,
)
from apache_buildish_release_tooling.release.manifest import write_manifest
from apache_buildish_release_tooling.release.models import CommandContext, PrepareRcState
from apache_buildish_release_tooling.release.rc_vote_verification import (
    required_rc_vote_manifest_file_names,
    required_source_release_file_names,
    verify_staged_source_release_against_vote_manifest,
)
from apache_buildish_release_tooling.release.release_state import derive_final_tag
from apache_buildish_release_tooling.release.summary import SummaryWriter

from apache_buildish_release_tooling.release.commands._shared import (
    _context,
    _create_or_reuse_annotated_tag,
    _latest_rc_directory_name,
    _manifest_path,
    _rc_number_from_tag,
    _release_name,
    _repository_slug_or_none,
    _resolve_prepare_rc_state_from_args,
    _resolve_release_version_state,
)


def _draft_release_body(context: CommandContext, state: PrepareRcState) -> str:
    """Render the body used for the draft GitHub Release placeholder."""

    return render_draft_github_release_body(
        context.component_config,
        state=state,
    )


def run_sync_draft_github_release(args: Namespace) -> Path:
    """Create or recreate the draft GitHub Release placeholder for an exact version."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version, state = _resolve_prepare_rc_state_from_args(args, context, repo)
    repository_slug = resolve_repository_slug(repo.path)
    release_name = _release_name(context, version)
    existing_releases = list_releases(repository_slug)
    matching_release_payloads = matching_draft_releases(
        existing_releases,
        version=version,
        tag_names=[state.final_tag, state.rc_tag],
        release_name=release_name,
    )
    sync_plan = plan_draft_release_sync(
        matching_release_payloads,
        version=version,
        state=state,
    )
    deleted_release_ids = sync_plan.deleted_release_ids
    for release_id in deleted_release_ids:
        delete_release(repository_slug, release_id)
    desired_release_body = _draft_release_body(context, state)
    created_release, sync_mode = upsert_draft_release(
        repository_slug,
        state=state,
        release_name=release_name,
        desired_release_body=desired_release_body,
        same_rc_release=sync_plan.same_rc_release,
    )
    created_release_id = created_release.get("id")
    created_release_tag = created_release.get("tag_name")
    created_release_title = created_release.get("name")
    created_release_url = asset_release_url(created_release)
    manifest_path = _manifest_path(context.component_config.component_id, "sync-draft-github-release")
    summary = SummaryWriter.from_environment()
    write_manifest(
        manifest_path,
        SyncDraftGithubReleaseManifest(
            component=context.component_config.component_id,
            version=version,
            repository_slug=repository_slug,
            resolved_source_ref=state.resolved_source_ref,
            rc_tag=state.rc_tag,
            final_tag=state.final_tag,
            staging_url=state.staging_url,
            deleted_release_ids=[str(item) for item in deleted_release_ids],
            release_id=str(created_release_id or ""),
            release_tag=str(created_release_tag or ""),
            release_name=str(created_release_title or ""),
            release_url=str(created_release_url),
            sync_mode=sync_mode,
        ),
    )
    summary.append_heading("Sync draft GitHub Release")
    summary.append_plaintext_block("GitHub repository", repository_slug)
    summary.append_plaintext_block(
        "Deleted draft release IDs",
        "\n".join(str(item) for item in deleted_release_ids) if deleted_release_ids else "<none>",
    )
    summary.append_plaintext_block(
        "Created draft release",
        "\n".join(
            [
                f"id: {created_release_id}",
                f"name: {created_release_title}",
                f"tag: {created_release_tag}",
                f"url: {created_release_url}",
                f"mode: {sync_mode}",
            ]
        ),
    )
    return manifest_path


def run_publish_source_release_svn(args: Namespace) -> Path:
    """Promote the latest staged source RC from ASF `dist/dev` into `dist/release`."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version = args.version
    selected_release = selected_github_release(
        repo=repo,
        version=version,
        expected_selected_rc_tag=getattr(args, "selected_rc_tag", None),
    )
    rc_directory_name = _latest_rc_directory_name(version, selected_release.selected_rc_tag)
    source_url = url_join(context.component_config.asf_dist_dev_base.rstrip("/"), rc_directory_name)
    target_url = url_join(context.component_config.asf_dist_release_base.rstrip("/"), version)
    svn_client = AsfSvnClient.from_environment()
    if not svn_client.path_exists(source_url):
        raise ValueError(f"RC staging directory does not exist: {source_url}")
    staged_entries = sorted(svn_client.list_entries(source_url, recursive=True))
    required_source_release_files = required_source_release_file_names(
        context.component_config.source_artifact_prefix,
        version,
    )
    required_file_names = [
        *required_source_release_files,
        *required_rc_vote_manifest_file_names(),
    ]
    missing_required_files = [
        file_name for file_name in required_file_names if file_name not in staged_entries
    ]
    if missing_required_files:
        raise ValueError(
            "RC staging directory is missing required staged release files: "
            + ", ".join(missing_required_files)
        )
    verified_source_artifact_sha512 = verify_staged_source_release_against_vote_manifest(
        context,
        repository_slug=selected_release.repository_slug,
        release_payload=selected_release.release_payload,
        source_url=source_url,
        version=version,
        selected_rc_tag=selected_release.selected_rc_tag,
        expected_source_artifact_name=required_source_release_files[0],
    )
    if svn_client.path_exists(target_url):
        target_entries = sorted(svn_client.list_entries(target_url, recursive=True))
        if staged_entries != target_entries:
            raise ValueError(
                f"final release directory already exists with different contents: {target_url}"
            )
        publish_mode = "already-present"
    else:
        svn_client.copy_url(
            source_url,
            target_url,
            f"publish source release for {context.component_config.component_id} {version}",
        )
        publish_mode = "copied"
    manifest_path = _manifest_path(context.component_config.component_id, "publish-source-release-svn")
    summary = SummaryWriter.from_environment()
    write_manifest(
        manifest_path,
        PublishSourceReleaseSvnManifest(
            component=context.component_config.component_id,
            version=version,
            selected_rc_tag=selected_release.selected_rc_tag,
            source_url=f"{source_url}/",
            target_url=f"{target_url}/",
            verified_source_artifact_sha512=verified_source_artifact_sha512,
            publish_mode=publish_mode,
        ),
    )
    summary.append_heading("Publish source release SVN")
    summary.append_plaintext_block("Selected RC", selected_release.selected_rc_tag)
    summary.append_plaintext_block("Promoted source URL", f"{source_url}/")
    summary.append_plaintext_block("Published release URL", f"{target_url}/")
    summary.append_sha512_block(
        required_source_release_files[0],
        verified_source_artifact_sha512,
    )
    summary.append_plaintext_block("Publish mode", publish_mode)
    return manifest_path


def run_prune_older_line_releases(args: Namespace) -> Path:
    """Delete older same-line releases from ASF `dist/release`."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version = args.version
    release_line, state = _resolve_release_version_state(context, repo, version)
    release_base_url = context.component_config.asf_dist_release_base.rstrip("/")
    svn_client = AsfSvnClient.from_environment()
    for archived_version in state.archive_versions:
        svn_client.delete_url(
            url_join(release_base_url, archived_version),
            f"prune older same-line release for {context.component_config.component_id} {archived_version}",
        )
    manifest_path = _manifest_path(context.component_config.component_id, "prune-older-line-releases")
    summary = SummaryWriter.from_environment()
    write_manifest(
        manifest_path,
        PruneOlderLineReleasesManifest(
            component=context.component_config.component_id,
            version=version,
            release_line=release_line,
            pruned_versions=state.archive_versions,
            release_base_url=f"{release_base_url}/",
        ),
    )
    summary.append_heading("Prune older line releases")
    summary.append_plaintext_block("Release line", release_line)
    summary.append_plaintext_block("ASF SVN release base", f"{release_base_url}/")
    summary.append_plaintext_block(
        "Pruned versions",
        "\n".join(state.archive_versions) if state.archive_versions else "<none>",
    )
    return manifest_path


def run_create_final_tag(args: Namespace) -> Path:
    """Create the immutable exact final Git tag for a released version."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version = args.version
    selected_release = selected_github_release(
        repo=repo,
        version=version,
        expected_selected_rc_tag=getattr(args, "selected_rc_tag", None),
    )
    final_tag = derive_final_tag(version)
    final_tag_message = f"Release {context.component_config.vote_release_name} {version}"
    target_commit = repo.resolve_commit(selected_release.selected_rc_tag)
    repository_slug = _repository_slug_or_none(repo)
    tag_creation_mode, created_ref = _create_or_reuse_annotated_tag(
        repo=repo,
        repository_slug=repository_slug,
        tag_name=final_tag,
        target_commit=target_commit,
        message=final_tag_message,
        allow_update=False,
    )
    manifest_path = _manifest_path(context.component_config.component_id, "create-final-tag")
    summary = SummaryWriter.from_environment()
    write_manifest(
        manifest_path,
        CreateFinalTagManifest(
            component=context.component_config.component_id,
            version=version,
            selected_rc_tag=selected_release.selected_rc_tag,
            final_tag=final_tag,
            target_commit=target_commit,
            tag_creation_mode=tag_creation_mode,
            created_ref=str(created_ref.get("ref") or ""),
        ),
    )
    summary.append_heading("Create final tag")
    summary.append_plaintext_block("Selected RC", selected_release.selected_rc_tag)
    summary.append_plaintext_block("Final tag", final_tag)
    summary.append_plaintext_block("Target commit", target_commit)
    summary.append_plaintext_block("Tag creation mode", tag_creation_mode)
    return manifest_path


def run_finalize_draft_github_release(args: Namespace) -> Path:
    """Publish the existing draft GitHub Release for an exact final version."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version = args.version
    expected_selected_rc_tag = getattr(args, "selected_rc_tag", None)
    selected_release = selected_github_release(
        repo=repo,
        version=version,
        expected_selected_rc_tag=expected_selected_rc_tag,
    )
    release_name = _release_name(context, version)
    final_tag = derive_final_tag(version)
    final_tag_target_commit = repo.resolve_commit(selected_release.selected_rc_tag)
    release_id = selected_release.require_release_id(reference_tag=final_tag)
    deleted_asset_names: list[str] = []
    for asset_name, asset_id in release_asset_ids_by_names(
        selected_release.release_payload,
        asset_names=[
            "rc-vote-manifest.json",
            "rc-vote-manifest.json.asc",
            "rc-vote-manifest.json.sha512",
        ],
    ).items():
        delete_release_asset(selected_release.repository_slug, asset_id)
        deleted_asset_names.append(asset_name)
    if selected_release.release_payload.get("draft") is False:
        finalized_release = selected_release.release_payload
        finalize_mode = "already-finalized"
    else:
        finalized_release = update_release(
            selected_release.repository_slug,
            release_id,
            payload={
                "tag_name": final_tag,
                "target_commitish": final_tag_target_commit,
                "draft": False,
                "prerelease": False,
                "name": release_name,
            },
        )
        finalize_mode = "published-draft"
    finalized_release_tag = finalized_release.get("tag_name")
    finalized_release_name = finalized_release.get("name")
    finalized_release_url = asset_release_url(finalized_release)
    manifest_path = _manifest_path(context.component_config.component_id, "finalize-draft-github-release")
    summary = SummaryWriter.from_environment()
    write_manifest(
        manifest_path,
        FinalizeDraftGithubReleaseManifest(
            component=context.component_config.component_id,
            version=version,
            repository_slug=selected_release.repository_slug,
            release_id=str(release_id),
            release_tag=str(finalized_release_tag or ""),
            release_name=str(finalized_release_name or ""),
            release_url=str(finalized_release_url),
            deleted_asset_names=sorted(deleted_asset_names),
            finalize_mode=finalize_mode,
        ),
    )
    summary.append_heading("Finalize draft GitHub Release")
    summary.append_plaintext_block("GitHub repository", selected_release.repository_slug)
    summary.append_plaintext_block(
        "Removed draft-only assets",
        "\n".join(sorted(deleted_asset_names)) if deleted_asset_names else "<none>",
    )
    summary.append_plaintext_block(
        "Finalized release",
        "\n".join(
            [
                f"id: {release_id}",
                f"name: {finalized_release_name}",
                f"tag: {finalized_release_tag}",
                f"url: {finalized_release_url}",
                f"mode: {finalize_mode}",
            ]
        ),
    )
    announce_email = render_announce_email(
        component_config=context.component_config,
        version=version,
    )
    summary.append_email_template_blocks(
        "ANNOUNCE",
        announce_email.subject,
        announce_email.body,
    )
    return manifest_path


def run_release_version(args: Namespace) -> Path:
    """Resolve final release state, same-line pruning, and moving aliases."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version = args.version
    release_line, state = _resolve_release_version_state(
        context,
        repo,
        version,
        expected_selected_rc_tag=getattr(args, "selected_rc_tag", None),
    )
    manifest_path = _manifest_path(context.component_config.component_id, "release-version")
    summary = SummaryWriter.from_environment()
    write_manifest(
        manifest_path,
        ReleaseVersionManifest(
            component=context.component_config.component_id,
            version=version,
            release_line=release_line,
            selected_rc_tag=state.selected_rc_tag,
            final_tag=state.final_tag,
            archive_versions=state.archive_versions,
            release_url=state.release_url,
            moving_tags=state.moving_tags,
            final_tag_mode=context.component_config.final_tag_mode,
        ),
    )
    summary.append_heading("Release version")
    summary.append_plaintext_block("Selected RC", state.selected_rc_tag)
    summary.append_plaintext_block(
        "Archive older same-line releases",
        "\n".join(state.archive_versions) if state.archive_versions else "<none>",
    )
    summary.append_plaintext_block(
        "Derived moving tags", " ".join(state.moving_tags) if state.moving_tags else "<none>"
    )
    if context.component_config.release_summary_include_final_tag_mode:
        summary.append_plaintext_block("Final tag mode", context.component_config.final_tag_mode)
    vote_result_email = render_project_vote_result_email(
        component_config=context.component_config,
        version=version,
        rc_number=_rc_number_from_tag(version, state.selected_rc_tag),
    )
    summary.append_email_template_blocks(
        "Project vote result",
        vote_result_email.subject,
        vote_result_email.body,
    )
    return manifest_path
