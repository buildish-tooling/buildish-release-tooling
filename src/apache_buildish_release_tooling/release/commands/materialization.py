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

"""Detached materialization and RC-tag creation commands."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path

from apache_buildish_release_tooling.release.git_materialization import (
    add_detached_worktree,
    default_materialized_ref_name,
    delete_remote_ref_best_effort,
    git_config_set,
    has_staged_changes,
    push_remote_ref,
    remove_worktree,
    validate_full_ref_name,
    validate_materialized_paths,
)
from apache_buildish_release_tooling.release.git_repo import GitRepository
from apache_buildish_release_tooling.release.manifest import write_manifest
from apache_buildish_release_tooling.release.models import CommandContext, PrepareRcState
from apache_buildish_release_tooling.release.process import run_logged_command
from apache_buildish_release_tooling.release.summary import SummaryWriter

from apache_buildish_release_tooling.release.commands._shared import (
    _append_github_outputs,
    _context,
    _create_or_reuse_annotated_tag,
    _manifest_path,
    _rc_tag_message,
    _repository_slug_or_none,
    _resolve_prepare_rc_state_from_args,
    _temporary_build_dir,
)


@dataclass(frozen=True)
class MaterializedGitContent:
    """Resolved outcome from one detached RC content materialization run."""

    materialized_paths: list[str]
    materialized_commit_sha: str
    materialized_ref_name: str
    materialized_ref_mode: str


def _materialize_rc_git_content(
    repo: GitRepository,
    *,
    state: PrepareRcState,
    repository_slug: str | None,
    materialized_paths: list[str],
    materialized_ref_name: str,
    run_command: str,
) -> MaterializedGitContent:
    """Create, commit, and push one detached materialization worktree result."""

    with _temporary_build_dir("materialize-rc-git-content") as temp_root:
        worktree_path = temp_root / "worktree"
        add_detached_worktree(repo, worktree_path, state.resolved_source_ref)
        try:
            worktree_repo = GitRepository(worktree_path)
            git_config_set(worktree_path, "user.name", "Buildish Release Tooling")
            git_config_set(worktree_path, "user.email", "buildish-release-tooling@example.invalid")
            run_logged_command(["sh", "-lc", run_command], cwd=worktree_path, capture_output=False)
            run_logged_command(
                ["git", "-C", str(worktree_path), "add", "--force", "--", *materialized_paths],
                cwd=worktree_path,
                capture_output=False,
            )
            if not has_staged_changes(worktree_path):
                raise ValueError(
                    "materialized content commit would be empty for "
                    f"{state.resolved_source_ref}: {', '.join(materialized_paths)}"
                )
            run_logged_command(
                [
                    "git",
                    "-C",
                    str(worktree_path),
                    "commit",
                    "-m",
                    f"Materialize RC Git content for {state.rc_tag}",
                ],
                cwd=worktree_path,
                capture_output=False,
            )
            materialized_commit_sha = worktree_repo.current_head_commit()
            materialized_ref_mode = push_remote_ref(
                worktree_repo,
                repository_slug=repository_slug,
                source_ref="HEAD",
                target_ref=materialized_ref_name,
                force=True,
            )
            return MaterializedGitContent(
                materialized_paths=materialized_paths,
                materialized_commit_sha=materialized_commit_sha,
                materialized_ref_name=materialized_ref_name,
                materialized_ref_mode=materialized_ref_mode,
            )
        finally:
            remove_worktree(repo, worktree_path)


def _resolve_materialization_tag_target(
    context: CommandContext,
    state: PrepareRcState,
    target_commit: str | None,
) -> tuple[str, str]:
    """Resolve the commit to tag and whether it comes from source or detached materialization."""

    if target_commit is not None:
        if (
            context.component_config.final_tag_mode != "detached-materialization-commit"
            and target_commit != state.resolved_source_ref
        ):
            raise ValueError("target_commit override is only valid for detached-materialization components")
        tag_target_origin = (
            "materialized-commit" if target_commit != state.resolved_source_ref else "source-commit"
        )
        return target_commit, tag_target_origin
    if context.component_config.final_tag_mode == "detached-materialization-commit":
        raise ValueError("detached-materialization components require --target-commit")
    return state.resolved_source_ref, "source-commit"


def run_materialize_rc_git_content(args: Namespace) -> Path:
    """Create one detached RC materialization commit from release-only generated Git paths."""

    context = _context(args)
    if context.component_config.final_tag_mode != "detached-materialization-commit":
        raise ValueError(
            "materialize-rc-git-content is valid only for detached-materialization components"
        )
    repo = GitRepository.from_current_worktree()
    version, state = _resolve_prepare_rc_state_from_args(args, context, repo)
    materialized_paths = validate_materialized_paths(getattr(args, "materialized_paths", []))
    materialized_ref_name = getattr(args, "materialized_ref_name", None)
    if materialized_ref_name is not None:
        materialized_ref_name = validate_full_ref_name(materialized_ref_name)
    else:
        materialized_ref_name = default_materialized_ref_name(state)
    run_command = getattr(args, "run_command", "").strip()
    if not run_command:
        raise ValueError("--run-command must not be empty")

    materialized_content = _materialize_rc_git_content(
        repo,
        state=state,
        repository_slug=_repository_slug_or_none(repo),
        materialized_paths=materialized_paths,
        materialized_ref_name=materialized_ref_name,
        run_command=run_command,
    )
    manifest_path = _manifest_path(context.component_config.component_id, "materialize-rc-git-content")
    summary = SummaryWriter.from_environment()
    manifest_entries = {
        "component": context.component_config.component_id,
        "action": "materialize-rc-git-content",
        "version": version,
        "resolved_source_ref": state.resolved_source_ref,
        "rc_tag": state.rc_tag,
        "materialized_paths": ",".join(materialized_content.materialized_paths),
        "materialized_commit_sha": materialized_content.materialized_commit_sha,
        "materialized_ref_name": materialized_content.materialized_ref_name,
        "materialized_ref_mode": materialized_content.materialized_ref_mode,
    }
    write_manifest(manifest_path, manifest_entries)
    _append_github_outputs(
        {
            "materialized_commit_sha": materialized_content.materialized_commit_sha,
            "materialized_ref_name": materialized_content.materialized_ref_name,
        }
    )
    summary.append_heading("Materialize RC Git content")
    summary.append_plaintext_block("Resolved source ref", state.resolved_source_ref)
    summary.append_plaintext_block("RC tag", state.rc_tag)
    summary.append_plaintext_block(
        "Materialized paths",
        "\n".join(materialized_content.materialized_paths),
    )
    summary.append_plaintext_block("Materialized commit", materialized_content.materialized_commit_sha)
    summary.append_plaintext_block("Materialized ref", materialized_content.materialized_ref_name)
    summary.append_plaintext_block("Materialized ref mode", materialized_content.materialized_ref_mode)
    return manifest_path


def run_create_rc_materialization_tag(args: Namespace) -> Path:
    """Create the RC tag on either the source commit or one detached materialization commit."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version, state = _resolve_prepare_rc_state_from_args(args, context, repo)
    cleanup_materialized_ref_name = getattr(args, "cleanup_materialized_ref_name", None)
    if cleanup_materialized_ref_name is not None:
        cleanup_materialized_ref_name = validate_full_ref_name(cleanup_materialized_ref_name)
    target_commit, tag_target_origin = _resolve_materialization_tag_target(
        context,
        state,
        args.target_commit,
    )
    repository_slug = _repository_slug_or_none(repo)
    cleanup_materialized_ref_mode = "not-requested"
    try:
        tag_creation_mode, created_ref = _create_or_reuse_annotated_tag(
            repo=repo,
            repository_slug=repository_slug,
            tag_name=state.rc_tag,
            target_commit=target_commit,
            message=_rc_tag_message(context, version, state.rc_tag),
            allow_update=False,
            reuse_if_same_target=False,
        )
    finally:
        if cleanup_materialized_ref_name is not None:
            cleanup_materialized_ref_mode = delete_remote_ref_best_effort(
                repo,
                repository_slug=repository_slug,
                ref_name=cleanup_materialized_ref_name,
            )
    manifest_path = _manifest_path(context.component_config.component_id, "create-rc-materialization-tag")
    summary = SummaryWriter.from_environment()
    write_manifest(
        manifest_path,
        {
            "component": context.component_config.component_id,
            "action": "create-rc-materialization-tag",
            "version": version,
            "resolved_source_ref": state.resolved_source_ref,
            "rc_tag": state.rc_tag,
            "target_commit": target_commit,
            "tag_target_origin": tag_target_origin,
            "cleanup_materialized_ref_name": cleanup_materialized_ref_name or "",
            "cleanup_materialized_ref_mode": cleanup_materialized_ref_mode,
            "tag_creation_mode": tag_creation_mode,
            "created_ref": str(created_ref.get("ref") or ""),
        },
    )
    summary.append_heading("Create RC tag")
    summary.append_plaintext_block("Resolved source ref", state.resolved_source_ref)
    summary.append_plaintext_block("RC tag", state.rc_tag)
    summary.append_plaintext_block("Target commit", target_commit)
    summary.append_plaintext_block("Tag target origin", tag_target_origin)
    summary.append_plaintext_block(
        "Cleanup materialized ref",
        cleanup_materialized_ref_name or "<none>",
    )
    summary.append_plaintext_block("Cleanup materialized ref mode", cleanup_materialized_ref_mode)
    summary.append_plaintext_block("Tag creation mode", tag_creation_mode)
    return manifest_path
