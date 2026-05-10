# Copyright 2026 The Apache Software Foundation
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

import shutil
from pathlib import Path

from apache_buildish_release_tooling.harness.config import ResolvedReleaseHarnessConfig
from apache_buildish_release_tooling.harness.models import HarnessScenario
from apache_buildish_release_tooling.harness.process import run_harness_command
from apache_buildish_release_tooling.harness.runtime import HarnessWorkspace

from .workflow import _repository_slug


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
    """Clone one local Git repository and overlay the current working-tree files on top."""

    run_harness_command(
        ["git", "clone", "--local", str(source_root), str(destination_root)],
        check=True,
        capture_output=True,
        text=True,
    )
    _configure_git_identity(destination_root)
    _overlay_working_tree(source_root, destination_root)


def materialize_git_repository_state(source_root: Path, destination_root: Path) -> None:
    """Clone one local Git repository without copying untracked working-tree files."""

    run_harness_command(
        ["git", "clone", "--local", str(source_root), str(destination_root)],
        check=True,
        capture_output=True,
        text=True,
    )
    _configure_git_identity(destination_root)


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
        "build",
        "dist",
    }
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
