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

"""Workspace, repository, and SVN fixture helpers for the `act` backend."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from apache_buildish_release_tooling.harness.config import (
    ResolvedReleaseHarnessConfig,
)
from apache_buildish_release_tooling.harness.models import (
    HarnessScenario,
    SvnRepositoryFixture,
    WorkspaceFile,
    WorkflowScenario,
)
from apache_buildish_release_tooling.harness.runtime import (
    HarnessWorkspace,
    create_workspace_root,
    ensure_workspace_directories,
    init_git_repository,
    workspace_paths,
    write_bash_env_hook,
    write_shim_state,
    write_workspace_file,
)
from apache_buildish_release_tooling.harness.backends.act.workflow import (
    _load_github_actions_yaml,
    _repository_slug,
    _write_bash_shim,
    _write_generic_tool_shims,
    _write_uv_shim,
)


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
        _materialize_git_checkout(self_repository_root, workspace_root)
    else:
        _materialize_git_repository_state(seed_workspace.root, workspace_root)
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

    _stage_repository_sources(workspace, bindings, seed_workspace=seed_workspace)
    workflow = _require_workflow(scenario)
    if workflow.gpg_fixture == "generated-signing-key":
        _generated_gpg_private_key_path(workspace)
    _prepare_local_svn_fixture(workspace, scenario, seed_workspace=seed_workspace)
    _overlay_release_config_for_local_svn(workspace)
    _apply_workflow_repository_fixture(workspace, scenario)
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


def _stage_repository_sources(
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
        _materialize_git_checkout(bindings.self_repository.local_path, self_origin_dir)
    else:
        seed_self_origin = seed_workspace.git_origins_dir / "self"
        if seed_self_origin.is_dir():
            _materialize_git_repository_state(seed_self_origin, self_origin_dir)
        else:
            _materialize_git_repository_state(seed_workspace.root, self_origin_dir)
    self_source_dir = repo_sources_dir / _repository_slug(bindings.self_repository.repository_id)
    if self_source_dir.exists():
        shutil.rmtree(self_source_dir)
    _materialize_git_checkout(bindings.self_repository.local_path, self_source_dir)
    github_origin_url = f"https://github.com/{bindings.self_repository.repository_id}.git"
    subprocess.run(
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
    subprocess.run(
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
        _materialize_source_tree(binding.local_path, source_dir)


def _apply_workflow_repository_fixture(
    workspace: HarnessWorkspace,
    scenario: HarnessScenario,
) -> None:
    """Create any scenario-declared branches and tags in the workflow repository checkout."""

    workflow = _require_workflow(scenario)
    fixture = workflow.repository_fixture
    for branch in fixture.branches:
        existing_branch = subprocess.run(
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
        subprocess.run(
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
        existing_tag = subprocess.run(
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
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )


def _prepare_local_svn_fixture(
    workspace: HarnessWorkspace,
    scenario: HarnessScenario,
    *,
    seed_workspace: HarnessWorkspace | None,
) -> None:
    """Create a local inspectable ASF SVN repository and working copy for one workflow scenario."""

    workflow = _require_workflow(scenario)
    repository_dir = workspace.svn_repository_dir
    working_copy_dir = workspace.svn_working_copy_dir
    if seed_workspace is None and repository_dir.exists():
        shutil.rmtree(repository_dir)
    if working_copy_dir.exists():
        shutil.rmtree(working_copy_dir)
    if not repository_dir.exists():
        subprocess.run(
            ["svnadmin", "create", str(repository_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
    component_config_path = _component_release_config_path(workspace)
    if not component_config_path.is_file():
        return
    config_payload = _load_github_actions_yaml(component_config_path)
    dev_base_relpath = _svn_repository_relpath(str(config_payload["asf_dist_dev_base"]))
    release_base_relpath = _svn_repository_relpath(str(config_payload["asf_dist_release_base"]))
    fixture = workflow.svn_fixture
    directories_to_create = _svn_fixture_directories(
        fixture=fixture,
        workflow=workflow,
        dev_base_relpath=dev_base_relpath,
        release_base_relpath=release_base_relpath,
    )
    for relative_directory in directories_to_create:
        _svn_mkdir_url(repository_dir.as_uri(), relative_directory)
    _refresh_svn_working_copy(workspace)
    _apply_svn_repository_file_fixtures(workspace, fixture.repository_files)


def _overlay_release_config_for_local_svn(workspace: HarnessWorkspace) -> None:
    """Rewrite the workspace release-config to use the harness-owned local ASF SVN repository."""

    component_config_path = _component_release_config_path(workspace)
    if not component_config_path.is_file():
        return
    config_payload = _load_github_actions_yaml(component_config_path)
    dev_base_relpath = _svn_repository_relpath(str(config_payload["asf_dist_dev_base"]))
    release_base_relpath = _svn_repository_relpath(str(config_payload["asf_dist_release_base"]))
    config_payload["asf_dist_dev_base"] = (workspace.svn_repository_dir / dev_base_relpath).as_uri()
    config_payload["asf_dist_release_base"] = (
        workspace.svn_repository_dir / release_base_relpath
    ).as_uri()
    component_config_path.write_text(
        yaml.safe_dump(config_payload, sort_keys=False),
        encoding="utf-8",
    )


def _component_release_config_path(workspace: HarnessWorkspace) -> Path:
    """Return the standard per-repository release-config path inside one workspace."""

    return workspace.root / "buildish-release-tooling" / "release-config.yaml"


def _svn_repository_relpath(base_url: str) -> Path:
    """Return the repository-relative path portion for one configured ASF SVN base URL."""

    parsed = urlsplit(base_url)
    return Path(parsed.path.lstrip("/"))


def _svn_fixture_directories(
    *,
    fixture: SvnRepositoryFixture,
    workflow: WorkflowScenario,
    dev_base_relpath: Path,
    release_base_relpath: Path,
) -> list[Path]:
    """Return the repository-relative directories that the local SVN fixture should contain."""

    directories: list[Path] = []
    if fixture.initial_state != "absent":
        directories.extend(_parent_paths(dev_base_relpath))
        directories.extend(_parent_paths(release_base_relpath))
        directories.append(dev_base_relpath)
        directories.append(release_base_relpath)
    version = fixture.version or workflow.inputs.get("version", "")
    rc_number = fixture.rc_number
    if fixture.initial_state == "preexisting-current-rc":
        directories.append(dev_base_relpath / f"{version}-rc{rc_number}")
    elif fixture.initial_state == "preexisting-previous-rc":
        directories.append(dev_base_relpath / f"{version}-rc{rc_number - 1}")
    elif fixture.initial_state == "preexisting-future-rc":
        directories.append(dev_base_relpath / f"{version}-rc{rc_number + 1}")
    elif fixture.initial_state == "preexisting-other-version":
        directories.append(dev_base_relpath / f"{fixture.other_version}-rc{rc_number}")
    directories.extend(dev_base_relpath / entry for entry in fixture.dev_dist_entries)
    directories.extend(release_base_relpath / entry for entry in fixture.release_dist_entries)
    expanded_directories: list[Path] = []
    for directory in directories:
        expanded_directories.extend(_parent_paths(directory))
        expanded_directories.append(directory)
    deduplicated: list[Path] = []
    seen: set[str] = set()
    for directory in expanded_directories:
        normalized = directory.as_posix().rstrip("/")
        if not normalized or normalized == ".":
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        deduplicated.append(Path(normalized))
    return deduplicated


def _parent_paths(path: Path) -> Iterable[Path]:
    """Yield all repository-relative parent paths needed to reach one target path."""

    parts = path.parts
    for index in range(1, len(parts)):
        yield Path(*parts[:index])


def _svn_mkdir_url(repo_url: str, relative_directory: Path) -> None:
    """Create one directory inside the harness local SVN repository when it does not exist yet."""

    directory_url = f"{repo_url.rstrip('/')}/{relative_directory.as_posix().lstrip('/')}"
    if _svn_url_exists(directory_url):
        return
    subprocess.run(
        ["svn", "mkdir", "-m", f"create {relative_directory.as_posix()}", directory_url],
        check=True,
        capture_output=True,
        text=True,
    )


def _svn_url_exists(target_url: str) -> bool:
    """Return whether one SVN repository URL currently exists."""

    completed = subprocess.run(
        ["svn", "info", target_url],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def _refresh_svn_working_copy(workspace: HarnessWorkspace) -> None:
    """Refresh the inspectable SVN working copy from the harness local repository."""

    repository_dir = workspace.svn_repository_dir
    if not repository_dir.is_dir():
        return
    working_copy_dir = workspace.svn_working_copy_dir
    repo_url = repository_dir.as_uri()
    if working_copy_dir.exists():
        subprocess.run(
            ["svn", "update", str(working_copy_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
        return
    subprocess.run(
        ["svn", "checkout", repo_url, str(working_copy_dir)],
        check=True,
        capture_output=True,
        text=True,
    )


def _apply_svn_repository_file_fixtures(
    workspace: HarnessWorkspace,
    file_fixtures: list[WorkspaceFile],
) -> None:
    """Create and commit any scenario-declared repository-relative SVN files."""

    if not file_fixtures:
        return
    working_copy_dir = workspace.svn_working_copy_dir
    added_any = False
    for file_fixture in file_fixtures:
        relative_path = Path(file_fixture.path)
        if relative_path.is_absolute():
            raise ValueError(f"SVN fixture paths must be repository-relative: {file_fixture.path}")
        destination = working_copy_dir / relative_path
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(file_fixture.content, encoding="utf-8")
        subprocess.run(
            ["svn", "add", "--parents", "--force", str(destination)],
            check=True,
            capture_output=True,
            text=True,
        )
        added_any = True
    if not added_any:
        return
    subprocess.run(
        ["svn", "commit", "-m", "seed harness SVN repository files", str(working_copy_dir)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["svn", "update", str(working_copy_dir)],
        check=True,
        capture_output=True,
        text=True,
    )


def _materialize_git_checkout(source_root: Path, destination_root: Path) -> None:
    """Clone one local Git repository and overlay the current working-tree files on top."""

    subprocess.run(
        ["git", "clone", "--local", str(source_root), str(destination_root)],
        check=True,
        capture_output=True,
        text=True,
    )
    _configure_git_identity(destination_root)
    _overlay_working_tree(source_root, destination_root)


def _materialize_git_repository_state(source_root: Path, destination_root: Path) -> None:
    """Clone one local Git repository without copying untracked working-tree files."""

    subprocess.run(
        ["git", "clone", "--local", str(source_root), str(destination_root)],
        check=True,
        capture_output=True,
        text=True,
    )
    _configure_git_identity(destination_root)


def _materialize_source_tree(source_root: Path, destination_root: Path) -> None:
    """Copy one local source tree into a deterministic workspace-visible directory."""

    destination_root.mkdir(parents=True, exist_ok=True)
    _overlay_working_tree(source_root, destination_root)


def _configure_git_identity(repository_root: Path) -> None:
    """Ensure annotated-tag operations have a deterministic local Git identity."""

    subprocess.run(
        ["git", "-C", str(repository_root), "config", "user.name", "Buildish Release Harness"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
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
    subprocess.run(
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
        subprocess.run(
            ["gpg", "--armor", "--export-secret-keys", identity],
            env=gpg_env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout,
        encoding="utf-8",
    )
    public_key_path.write_text(
        subprocess.run(
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
