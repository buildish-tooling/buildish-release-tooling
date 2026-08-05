# Copyright 2026 The Buildish Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Git and source-tree fixture helpers for the `act` backend."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from buildish_release_tooling.harness.config import ResolvedReleaseHarnessConfig
from buildish_release_tooling.harness.models import HarnessScenario
from buildish_release_tooling.harness.process import run_harness_command
from buildish_release_tooling.harness.runtime import HarnessWorkspace

from .workflow import _repository_slug

_WORKING_TREE_SNAPSHOT_MESSAGE = "Buildish release harness working-tree snapshot"
_WORKING_TREE_SNAPSHOT_TIMESTAMP = "2000-01-01T00:00:00Z"


def stage_repository_sources(
    workspace: HarnessWorkspace,
    bindings: ResolvedReleaseHarnessConfig,
    *,
    seed_workspace: HarnessWorkspace | None,
) -> None:
    """Stage local repository sources inside the workspace for checkout overrides and imports."""

    repo_sources_dir = workspace.repo_sources_dir
    self_origin_dir = workspace.git_origins_dir / "self"
    if self_origin_dir.exists():
        shutil.rmtree(self_origin_dir)
    if seed_workspace is None:
        materialize_git_checkout(bindings.self_repository.local_path, self_origin_dir)
    else:
        seed_self_origin = seed_workspace.git_origins_dir / "self"
        if seed_self_origin.is_dir():
            materialize_git_repository_state(seed_self_origin, self_origin_dir)
        else:
            materialize_git_repository_state(seed_workspace.root, self_origin_dir)
    self_source_dir = repo_sources_dir / _repository_slug(bindings.self_repository.repository_id)
    if self_source_dir.exists():
        shutil.rmtree(self_source_dir)
    materialize_git_checkout(bindings.self_repository.local_path, self_source_dir)
    github_origin_url = f"https://github.com/{bindings.self_repository.repository_id}.git"
    run_harness_command(
        [
            "git",
            "-C",
            str(workspace.root),
            "config",
            "url../.buildish-release-harness/git-origins/self.insteadOf",
            github_origin_url,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    run_harness_command(
        [
            "git",
            "-C",
            str(workspace.root),
            "remote",
            "set-url",
            "origin",
            github_origin_url,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    for repository_id, binding in bindings.repository_overrides.items():
        if repository_id == bindings.self_repository.repository_id:
            continue
        source_dir = repo_sources_dir / _repository_slug(repository_id)
        if source_dir.exists():
            shutil.rmtree(source_dir)
        materialize_source_tree(binding.local_path, source_dir)


def synchronize_self_repository_sources(
    workspace: HarnessWorkspace,
    bindings: ResolvedReleaseHarnessConfig,
) -> None:
    """Expose the workspace's final source snapshot through local self-repository clones."""

    self_source_dir = workspace.repo_sources_dir / _repository_slug(
        bindings.self_repository.repository_id
    )
    for destination_root in (workspace.git_origins_dir / "self", self_source_dir):
        if not (destination_root / ".git").is_dir():
            continue
        run_harness_command(
            [
                "git",
                "-C",
                str(destination_root),
                "fetch",
                "--no-tags",
                str(workspace.root),
                "HEAD",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        run_harness_command(
            ["git", "-C", str(destination_root), "reset", "--hard", "FETCH_HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )


def apply_workflow_repository_fixture(
    workspace: HarnessWorkspace,
    scenario: HarnessScenario,
) -> None:
    """Create any scenario-declared branches and tags in the workflow repository checkout."""

    workflow = scenario.workflow
    if workflow is None:
        raise ValueError("act scenarios must define a workflow block")
    fixture = workflow.repository_fixture
    for branch in fixture.branches:
        existing_branch = run_harness_command(
            [
                "git",
                "-C",
                str(workspace.root),
                "show-ref",
                "--verify",
                "--quiet",
                f"refs/heads/{branch.name}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if existing_branch.returncode == 0:
            continue
        run_harness_command(
            [
                "git",
                "-C",
                str(workspace.root),
                "branch",
                branch.name,
                branch.start_point,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    for tag in fixture.tags:
        existing_tag = run_harness_command(
            [
                "git",
                "-C",
                str(workspace.root),
                "show-ref",
                "--verify",
                "--quiet",
                f"refs/tags/{tag.name}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if existing_tag.returncode == 0:
            continue
        command = [
            "git",
            "-C",
            str(workspace.root),
            "tag",
        ]
        if tag.annotated:
            message = tag.message or f"Harness tag {tag.name}"
            command.extend(["-a", tag.name, "-m", message, tag.target])
        else:
            command.extend([tag.name, tag.target])
        run_harness_command(
            command,
            check=True,
            capture_output=True,
            text=True,
        )


def materialize_git_checkout(source_root: Path, destination_root: Path) -> None:
    """Clone a local repository and commit any overlaid working-tree differences."""

    run_harness_command(
        ["git", "clone", "--local", str(source_root), str(destination_root)],
        check=True,
        capture_output=True,
        text=True,
    )
    _configure_git_identity(destination_root)
    _overlay_working_tree(source_root, destination_root)
    commit_git_working_tree_snapshot(destination_root)


def materialize_git_repository_state(source_root: Path, destination_root: Path) -> None:
    """Clone one local Git repository without copying untracked working-tree files."""

    run_harness_command(
        ["git", "clone", "--local", str(source_root), str(destination_root)],
        check=True,
        capture_output=True,
        text=True,
    )
    _configure_git_identity(destination_root)


def overlay_git_working_tree(source_root: Path, destination_root: Path) -> None:
    """Overlay and commit current source files in an existing disposable clone."""

    _overlay_working_tree(source_root, destination_root)
    commit_git_working_tree_snapshot(destination_root)


def materialize_source_tree(source_root: Path, destination_root: Path) -> None:
    """Copy one local source tree into a deterministic workspace-visible directory."""

    destination_root.mkdir(parents=True, exist_ok=True)
    _overlay_working_tree(source_root, destination_root)


def _configure_git_identity(repository_root: Path) -> None:
    """Ensure annotated-tag operations have a deterministic local Git identity."""

    run_harness_command(
        ["git", "-C", str(repository_root), "config", "user.name", "Buildish Release Harness"],
        check=True,
        capture_output=True,
        text=True,
    )
    exclude_path = repository_root / ".git" / "info" / "exclude"
    exclude_entry = ".buildish-release-harness/"
    exclude_lines = exclude_path.read_text(encoding="utf-8").splitlines()
    if exclude_entry not in exclude_lines:
        with exclude_path.open("a", encoding="utf-8") as exclude_file:
            exclude_file.write(f"{exclude_entry}\n")
    run_harness_command(
        [
            "git",
            "-C",
            str(repository_root),
            "config",
            "user.email",
            "buildish-release-harness@example.invalid",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _overlay_working_tree(source_root: Path, destination_root: Path) -> None:
    """Copy the visible working-tree files from one local repo into another directory."""

    ignore_names = {
        ".git",
        ".mypy_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        ".agents",
        "build",
        "dist",
    }
    _remove_deleted_tracked_paths(source_root, destination_root)
    for child in source_root.iterdir():
        if child.name in ignore_names:
            continue
        destination = destination_root / child.name
        if child.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(child, destination)
        elif child.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, destination)


def _remove_deleted_tracked_paths(source_root: Path, destination_root: Path) -> None:
    """Mirror tracked paths deleted from the source working tree into the overlay."""

    deleted = run_harness_command(
        [
            "git",
            "-C",
            str(source_root),
            "diff",
            "--name-only",
            "--diff-filter=D",
            "-z",
            "HEAD",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    for relative_path in deleted.stdout.split("\0"):
        if not relative_path:
            continue
        destination = destination_root / relative_path
        if destination.is_dir() and not destination.is_symlink():
            shutil.rmtree(destination)
        else:
            destination.unlink(missing_ok=True)


def commit_git_working_tree_snapshot(repository_root: Path) -> None:
    """Commit a deterministic disposable snapshot when an overlay changed the clone."""

    run_harness_command(
        ["git", "-C", str(repository_root), "add", "--all"],
        check=True,
        capture_output=True,
        text=True,
    )
    unchanged = run_harness_command(
        ["git", "-C", str(repository_root), "diff", "--cached", "--quiet"],
        check=False,
        capture_output=True,
        text=True,
    )
    if unchanged.returncode == 0:
        return
    if unchanged.returncode != 1:
        raise RuntimeError("unable to inspect the harness working-tree snapshot")
    commit_env = {
        **os.environ,
        "GIT_AUTHOR_DATE": _WORKING_TREE_SNAPSHOT_TIMESTAMP,
        "GIT_COMMITTER_DATE": _WORKING_TREE_SNAPSHOT_TIMESTAMP,
    }
    run_harness_command(
        [
            "git",
            "-C",
            str(repository_root),
            "commit",
            "--no-gpg-sign",
            "-m",
            _WORKING_TREE_SNAPSHOT_MESSAGE,
        ],
        env=commit_env,
        check=True,
        capture_output=True,
        text=True,
    )
