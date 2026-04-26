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

"""Git worktree, ref, and authenticated push helpers for RC materialization flows."""

from __future__ import annotations

import os
import secrets
import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path

from apache_buildish_release_tooling.git_repo import GitRepository
from apache_buildish_release_tooling.models import PrepareRcState
from apache_buildish_release_tooling.process import CommandExecutionError, run_logged_command


def validate_full_ref_name(ref_name: str) -> str:
    """Validate that one Git ref name is fully qualified and syntactically valid."""

    if not ref_name.startswith("refs/"):
        raise ValueError(f"Git ref name must start with refs/: {ref_name}")
    completed = run_logged_command(
        ["git", "check-ref-format", ref_name],
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(f"invalid Git ref name: {ref_name}")
    return ref_name


def default_materialized_ref_name(state: PrepareRcState) -> str:
    """Derive one temporary remote ref name for a detached materialization commit."""

    run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
    if run_id:
        run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "").strip() or "1"
        return validate_full_ref_name(
            f"refs/heads/buildish-internal/materialized/{state.rc_tag}/{run_id}-{run_attempt}"
        )
    random_suffix = secrets.token_hex(4)
    return validate_full_ref_name(
        "refs/heads/buildish-internal/materialized/"
        f"{state.rc_tag}/{state.resolved_source_ref[:12]}-{random_suffix}"
    )


def validate_materialized_paths(paths: Iterable[str]) -> list[str]:
    """Validate and deduplicate repository-relative materialized file or directory paths."""

    materialized_paths: list[str] = []
    for raw_path in paths:
        candidate = Path(raw_path)
        if candidate.is_absolute():
            raise ValueError(f"materialized paths must be repository-relative: {raw_path}")
        if ".." in candidate.parts:
            raise ValueError(f"materialized paths must not escape the repository root: {raw_path}")
        normalized = str(candidate)
        if normalized not in materialized_paths:
            materialized_paths.append(normalized)
    if not materialized_paths:
        raise ValueError("at least one --materialized-path is required")
    return materialized_paths


def git_config_set(repo_path: Path, key: str, value: str) -> None:
    """Set one local Git configuration value inside one repository or worktree."""

    run_logged_command(
        ["git", "-C", str(repo_path), "config", key, value],
        cwd=repo_path,
        capture_output=False,
    )


def add_detached_worktree(repo: GitRepository, worktree_path: Path, source_ref: str) -> None:
    """Create one detached Git worktree rooted at a resolved source ref."""

    run_logged_command(
        [
            "git",
            "-C",
            str(repo.path),
            "worktree",
            "add",
            "--detach",
            str(worktree_path),
            source_ref,
        ],
        cwd=repo.path,
        capture_output=False,
    )


def remove_worktree(repo: GitRepository, worktree_path: Path) -> None:
    """Best-effort removal of one Git worktree path."""

    run_logged_command(
        ["git", "-C", str(repo.path), "worktree", "remove", "--force", str(worktree_path)],
        cwd=repo.path,
        capture_output=False,
        check=False,
    )


def has_staged_changes(repo_path: Path) -> bool:
    """Return whether one repository currently has staged changes."""

    completed = run_logged_command(
        ["git", "-C", str(repo_path), "diff", "--cached", "--quiet"],
        cwd=repo_path,
        check=False,
    )
    if completed.returncode in (0, 1):
        return completed.returncode == 1
    raise CommandExecutionError("command failed: git diff --cached --quiet")


def push_remote_ref(
    repo: GitRepository,
    *,
    repository_slug: str | None,
    source_ref: str,
    target_ref: str,
    force: bool,
) -> str:
    """Push one local ref or commit expression to one remote full ref name."""

    push_target = _git_push_target(repo, repository_slug)
    helper_dir, push_env, secret_values = _git_push_auth_env(push_target)
    command = ["git", "-C", str(repo.path), "push"]
    if force:
        command.append("--force")
    command.extend([push_target, f"{source_ref}:{target_ref}"])
    try:
        run_logged_command(
            command,
            cwd=repo.path,
            env=push_env,
            capture_output=False,
            extra_secret_values=secret_values,
        )
    finally:
        if helper_dir is not None:
            shutil.rmtree(helper_dir, ignore_errors=True)
    return "pushed"


def delete_remote_ref_best_effort(
    repo: GitRepository,
    *,
    repository_slug: str | None,
    ref_name: str,
) -> str:
    """Delete one remote full ref name without failing the parent command on cleanup issues."""

    helper_dir: Path | None = None
    try:
        push_target = _git_push_target(repo, repository_slug)
        helper_dir, push_env, secret_values = _git_push_auth_env(push_target)
        run_logged_command(
            ["git", "-C", str(repo.path), "push", push_target, f":{ref_name}"],
            cwd=repo.path,
            env=push_env,
            capture_output=False,
            extra_secret_values=secret_values,
        )
    except Exception:  # noqa: BLE001
        return "delete-failed-ignored"
    finally:
        if helper_dir is not None:
            shutil.rmtree(helper_dir, ignore_errors=True)
    return "deleted"


def _github_push_token() -> str | None:
    """Return the GitHub token used for authenticated HTTPS pushes, when available."""

    return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")


def _write_git_askpass_script(script_path: Path) -> None:
    """Materialize one short-lived askpass helper that serves GitHub HTTPS credentials."""

    script_path.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "set -eu",
                'prompt="${1-}"',
                'case "$prompt" in',
                "  *Username*|*username*)",
                '    printf \'%s\\n\' "${BUILDISH_GIT_ASKPASS_USERNAME:-x-access-token}"',
                "    ;;",
                "  *)",
                '    printf \'%s\\n\' "${BUILDISH_GIT_ASKPASS_TOKEN:?}"',
                "    ;;",
                "esac",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    script_path.chmod(0o700)


def _git_push_target(repo: GitRepository, repository_slug: str | None) -> str:
    """Resolve the remote URL used for temporary detached-commit ref pushes."""

    if _github_push_token() and repository_slug is not None:
        return f"https://github.com/{repository_slug}.git"
    return repo.remote_url("origin")


def _git_push_auth_env(push_target: str) -> tuple[Path | None, dict[str, str] | None, list[str]]:
    """Return short-lived environment overrides for authenticated HTTPS Git pushes."""

    token = _github_push_token()
    if token is None or not push_target.startswith(("http://", "https://")):
        return (None, None, [])

    helper_dir = Path(tempfile.mkdtemp(prefix="buildish-git-askpass-"))
    script_path = helper_dir / "git-askpass.sh"
    _write_git_askpass_script(script_path)
    return (
        helper_dir,
        {
            "BUILDISH_GIT_ASKPASS_TOKEN": token,
            "BUILDISH_GIT_ASKPASS_USERNAME": "x-access-token",
            "GH_TOKEN": "",
            "GITHUB_TOKEN": "",
            "GIT_ASKPASS": str(script_path),
            "GIT_TERMINAL_PROMPT": "0",
        },
        [token],
    )
