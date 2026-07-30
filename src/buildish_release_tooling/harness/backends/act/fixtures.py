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

"""Workspace bootstrap orchestration for the `act` backend."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from buildish_release_tooling.harness.config import ResolvedReleaseHarnessConfig
from buildish_release_tooling.harness.models import HarnessScenario, WorkflowScenario
from buildish_release_tooling.harness.process import run_harness_command
from buildish_release_tooling.harness.runtime import (
    HarnessWorkspace,
    create_workspace_root,
    ensure_workspace_directories,
    init_git_repository,
    workspace_paths,
    write_bash_env_hook,
    write_shim_state,
    write_workspace_file,
)
from buildish_release_tooling.harness.backends.act.workflow import (
    _write_bash_shim,
    _write_generic_tool_shims,
    _write_uv_shim,
)

from .fixtures_git import (
    apply_workflow_repository_fixture,
    materialize_git_checkout,
    materialize_git_repository_state,
    stage_repository_sources,
)
from . import fixtures_svn
from .fixtures_svn import overlay_release_config_for_local_svn, prepare_local_svn_fixture

_refresh_svn_working_copy = fixtures_svn._refresh_svn_working_copy


def _require_workflow(scenario: HarnessScenario) -> WorkflowScenario:
    """Return the validated workflow block of an `act` scenario."""

    if scenario.workflow is None:
        raise ValueError("act scenarios must define a workflow block")
    return scenario.workflow


def _create_workspace(
    self_repository_root: Path,
    root_dir: Path | None,
    *,
    seed_workspace: HarnessWorkspace | None,
) -> HarnessWorkspace:
    """Create one fresh workspace rooted at a local clone of the workflow repository."""

    workspace_root = create_workspace_root(root_dir)
    if seed_workspace is None:
        materialize_git_checkout(self_repository_root, workspace_root)
    else:
        materialize_git_repository_state(seed_workspace.root, workspace_root)
    workspace = workspace_paths(workspace_root)
    ensure_workspace_directories(workspace)
    if seed_workspace is not None:
        _seed_workspace_state(seed_workspace, workspace)
    return workspace


def _seed_workspace_state(
    seed_workspace: HarnessWorkspace,
    workspace: HarnessWorkspace,
) -> None:
    """Copy the mutable harness-owned state from a prior workspace into a fresh one."""

    _copy_directory(seed_workspace.git_origins_dir, workspace.git_origins_dir)
    _copy_directory(seed_workspace.svn_repository_dir, workspace.svn_repository_dir)


def _copy_directory(source: Path, destination: Path) -> None:
    """Copy one directory tree when the source exists."""

    if not source.exists():
        return
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _bootstrap_workspace(
    workspace: HarnessWorkspace,
    scenario: HarnessScenario,
    bindings: ResolvedReleaseHarnessConfig,
    *,
    seed_workspace: HarnessWorkspace | None,
) -> None:
    """Materialize repo bindings, workspace fixtures, and shims for an `act` run."""

    stage_repository_sources(workspace, bindings, seed_workspace=seed_workspace)
    workflow = _require_workflow(scenario)
    if workflow.gpg_fixture == "generated-signing-key":
        _generated_gpg_private_key_path(workspace)
    prepare_local_svn_fixture(workspace, scenario, seed_workspace=seed_workspace)
    overlay_release_config_for_local_svn(workspace)
    apply_workflow_repository_fixture(workspace, scenario)
    for file_fixture in scenario.workspace_files:
        write_workspace_file(
            workspace.root,
            file_fixture.path,
            file_fixture.content,
            file_fixture.executable,
        )
    for repository in scenario.git_repositories:
        init_git_repository(workspace.root, repository)
    write_shim_state(workspace, scenario)
    write_bash_env_hook(workspace, scenario)
    _write_generic_tool_shims(workspace, scenario)
    _write_bash_shim(workspace)
    _write_uv_shim(workspace, workflow.real_cli_commands)
    workspace.job_status_file.write_text("{}", encoding="utf-8")
    workspace.trace_file.write_text("", encoding="utf-8")


def _generated_gpg_private_key(workspace: HarnessWorkspace) -> str:
    """Return one reusable armored private key for harness signing scenarios."""

    fixture_dir = workspace.harness_dir / "gpg-fixture"
    source_home = fixture_dir / "source-home"
    private_key_path = fixture_dir / "private.asc"
    public_key_path = fixture_dir / "public.asc"
    if private_key_path.is_file():
        return private_key_path.read_text(encoding="utf-8")
    fixture_dir.mkdir(parents=True, exist_ok=True)
    source_home.mkdir(parents=True, exist_ok=True)
    source_home.chmod(0o700)
    gpg_env = {**os.environ, "GNUPGHOME": str(source_home)}
    identity = "Buildish Release Harness <buildish-release-harness@example.invalid>"
    run_harness_command(
        [
            "gpg",
            "--batch",
            "--pinentry-mode",
            "loopback",
            "--passphrase",
            "",
            "--quick-gen-key",
            identity,
            "ed25519",
            "sign",
            "1d",
        ],
        env=gpg_env,
        check=True,
        capture_output=True,
        text=True,
    )
    private_key_path.write_text(
        run_harness_command(
            ["gpg", "--armor", "--export-secret-keys", identity],
            env=gpg_env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout,
        encoding="utf-8",
    )
    public_key_path.write_text(
        run_harness_command(
            ["gpg", "--armor", "--export", identity],
            env=gpg_env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout,
        encoding="utf-8",
    )
    return private_key_path.read_text(encoding="utf-8")


def _generated_gpg_private_key_path(workspace: HarnessWorkspace) -> Path:
    """Return the workspace file that stores the generated harness private key."""

    _generated_gpg_private_key(workspace)
    return workspace.harness_dir / "gpg-fixture" / "private.asc"


def _active_workflow_path(workspace: HarnessWorkspace) -> Path:
    """Return the currently prepared rewritten workflow path for one workspace."""

    return Path((workspace.harness_dir / "active-workflow.txt").read_text(encoding="utf-8").strip())
