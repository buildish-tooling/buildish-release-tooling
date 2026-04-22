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

"""SVN fixture helpers for the `act` backend."""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from buildish_release_tooling.harness.models import (
    HarnessScenario,
    SvnRepositoryFixture,
    WorkspaceFile,
    WorkflowScenario,
)
from buildish_release_tooling.harness.process import run_harness_command
from buildish_release_tooling.harness.runtime import HarnessWorkspace, resolve_workspace_relative_path

from .workflow_yaml import _load_github_actions_yaml


def prepare_local_svn_fixture(
    workspace: HarnessWorkspace,
    scenario: HarnessScenario,
    *,
    seed_workspace: HarnessWorkspace | None,
) -> None:
    """Create a local inspectable ASF SVN repository and working copy for one workflow scenario."""

    workflow = scenario.workflow
    if workflow is None:
        raise ValueError("act scenarios must define a workflow block")
    repository_dir = workspace.svn_repository_dir
    working_copy_dir = workspace.svn_working_copy_dir
    if seed_workspace is None and repository_dir.exists():
        shutil.rmtree(repository_dir)
    if working_copy_dir.exists():
        shutil.rmtree(working_copy_dir)
    if not repository_dir.exists():
        run_harness_command(
            ["svnadmin", "create", str(repository_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
    component_config_path = component_release_config_path(workspace)
    if not component_config_path.is_file():
        return
    config_payload = _load_github_actions_yaml(component_config_path)
    policy_profiles = config_payload.get("policy_profiles")
    if not isinstance(policy_profiles, dict):
        return
    asf_profile = policy_profiles.get("asf")
    if not isinstance(asf_profile, dict):
        return
    dev_base_relpath = _svn_repository_relpath(str(asf_profile["dist_dev_base"]))
    release_base_relpath = _svn_repository_relpath(str(asf_profile["dist_release_base"]))
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


def overlay_release_config_for_local_svn(workspace: HarnessWorkspace) -> None:
    """Rewrite the workspace release-config to use the harness-owned local ASF SVN repository."""

    component_config_path = component_release_config_path(workspace)
    if not component_config_path.is_file():
        return
    config_payload = _load_github_actions_yaml(component_config_path)
    policy_profiles = config_payload.get("policy_profiles")
    if not isinstance(policy_profiles, dict):
        return
    asf_profile = policy_profiles.get("asf")
    if not isinstance(asf_profile, dict):
        return
    dev_base_relpath = _svn_repository_relpath(str(asf_profile["dist_dev_base"]))
    release_base_relpath = _svn_repository_relpath(str(asf_profile["dist_release_base"]))
    asf_profile["dist_dev_base"] = (workspace.svn_repository_dir / dev_base_relpath).as_uri()
    asf_profile["dist_release_base"] = (
        workspace.svn_repository_dir / release_base_relpath
    ).as_uri()
    component_config_path.write_text(
        yaml.safe_dump(config_payload, sort_keys=False),
        encoding="utf-8",
    )


def component_release_config_path(workspace: HarnessWorkspace) -> Path:
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
    run_harness_command(
        ["svn", "mkdir", "-m", f"create {relative_directory.as_posix()}", directory_url],
        check=True,
        capture_output=True,
        text=True,
    )


def _svn_url_exists(target_url: str) -> bool:
    """Return whether one SVN repository URL currently exists."""

    completed = run_harness_command(
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
        run_harness_command(
            ["svn", "update", str(working_copy_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
        return
    run_harness_command(
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
        destination = resolve_workspace_relative_path(working_copy_dir, file_fixture.path)
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(file_fixture.content, encoding="utf-8")
        run_harness_command(
            ["svn", "add", "--parents", "--force", str(destination)],
            check=True,
            capture_output=True,
            text=True,
        )
        added_any = True
    if not added_any:
        return
    run_harness_command(
        ["svn", "commit", "-m", "seed harness SVN repository files", str(working_copy_dir)],
        check=True,
        capture_output=True,
        text=True,
    )
    run_harness_command(
        ["svn", "update", str(working_copy_dir)],
        check=True,
        capture_output=True,
        text=True,
    )
