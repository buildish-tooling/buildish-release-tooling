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

"""`act` execution backend for the Buildish release harness."""

from __future__ import annotations

import copy
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import IO
from typing import Any
from urllib.parse import urlsplit

import yaml

from apache_buildish_release_tooling.harness.errors import HarnessExternalToolError
from apache_buildish_release_tooling.harness.config import (
    ResolvedReleaseHarnessConfig,
    ResolvedRepositoryBinding,
    load_release_harness_config,
)
from apache_buildish_release_tooling.harness.models import (
    HarnessScenario,
    SvnRepositoryFixture,
    WorkspaceFile,
    WorkflowScenario,
)
from apache_buildish_release_tooling.harness import runtime


@dataclass(frozen=True)
class WorkflowJobDefinition:
    """Normalized job metadata extracted from one workflow YAML file."""

    id: str
    needs: list[str]


class _GithubActionsYamlLoader(yaml.SafeLoader):
    """YAML loader that keeps GitHub Actions keys like `on` as plain strings."""


class _GithubActionsYamlDumper(yaml.SafeDumper):
    """YAML dumper that renders multiline shell snippets as literal blocks."""


_GithubActionsYamlLoader.yaml_implicit_resolvers = copy.deepcopy(
    yaml.SafeLoader.yaml_implicit_resolvers
)
for _first_char, _resolvers in list(_GithubActionsYamlLoader.yaml_implicit_resolvers.items()):
    _GithubActionsYamlLoader.yaml_implicit_resolvers[_first_char] = [
        (tag, pattern) for tag, pattern in _resolvers if tag != "tag:yaml.org,2002:bool"
    ]
yaml.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
    Loader=_GithubActionsYamlLoader,
)


def _represent_workflow_string(
    dumper: _GithubActionsYamlDumper,
    value: str,
) -> yaml.nodes.ScalarNode:
    """Represent multiline workflow strings as literal blocks for readable `run:` scripts."""

    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_GithubActionsYamlDumper.add_representer(str, _represent_workflow_string)


def _load_github_actions_yaml(path: Path) -> dict[str, Any]:
    """Load GitHub Actions YAML without converting keys like `on` into booleans."""

    payload = yaml.load(  # noqa: S506
        path.read_text(encoding="utf-8"),
        Loader=_GithubActionsYamlLoader,  # noqa: S506
    )
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"workflow {path} must be a top-level mapping")
    return payload


def run_scenario(
    scenario: HarnessScenario,
    *,
    workspace_root: Path | None = None,
    seed_from: Path | None = None,
) -> runtime.HarnessRunResult:
    """Run one `act`-backed harness scenario in a fresh disposable workspace."""

    workflow = _require_workflow(scenario)
    _progress(f"loading harness config {workflow.harness_config}")
    bindings = load_release_harness_config(Path(workflow.harness_config))
    seed_workspace = runtime.load_existing_workspace(seed_from) if seed_from is not None else None
    if seed_workspace is not None:
        _progress(f"seeding workspace state from {seed_workspace.root}")
    workspace = _create_workspace(
        bindings.self_repository.local_path,
        workspace_root,
        seed_workspace=seed_workspace,
    )
    _progress(f"created workspace {workspace.root}")
    _progress(f"bootstrapping workspace for scenario {scenario.name}")
    _bootstrap_workspace(workspace, scenario, bindings, seed_workspace=seed_workspace)
    job_definitions = _load_job_definitions(Path(workflow.path))
    selected_job_ids = _topological_job_ids(job_definitions)
    _progress(f"preparing rewritten workflow {workflow.path}")
    _prepare_workflow_execution(workspace, scenario, bindings)
    _progress("invoking act for all jobs")
    act_exit_code = _run_act(workspace, scenario, selected_job_ids=None)
    _refresh_svn_working_copy(workspace)
    result = _result_from_recorded_statuses(
        workspace=workspace,
        selected_job_ids=selected_job_ids,
        job_definitions=job_definitions,
        act_exit_code=act_exit_code,
    )
    runtime._write_job_statuses(workspace, result.job_statuses)
    runtime.write_job_summaries(workspace, _act_step_order_by_job(workspace))
    return result


def rerun_failed_jobs(scenario: HarnessScenario, workspace_root: Path) -> runtime.HarnessRunResult:
    """Rerun the failed `act` jobs and their downstream dependents in an existing workspace."""

    workflow = _require_workflow(scenario)
    workspace = runtime.load_existing_workspace(workspace_root)
    persisted_statuses = runtime._load_job_statuses(workspace)
    job_definitions = _load_job_definitions(Path(workflow.path))
    selected_job_ids = _rerunnable_job_ids(job_definitions, persisted_statuses)
    if not selected_job_ids:
        _progress("no failed jobs to rerun")
        return runtime.HarnessRunResult(
            workspace=workspace,
            selected_job_ids=[],
            failed_job_ids=[],
            blocked_job_ids=[],
            job_statuses=persisted_statuses,
        )
    bindings = load_release_harness_config(Path(workflow.harness_config))
    _progress(f"re-preparing workspace {workspace.root} for rerun")
    _prepare_workflow_execution(workspace, scenario, bindings)
    _clear_job_status_files(workspace, selected_job_ids)
    _progress(f"invoking act for rerun jobs: {', '.join(selected_job_ids)}")
    act_exit_code = _run_act(workspace, scenario, selected_job_ids=selected_job_ids)
    _refresh_svn_working_copy(workspace)
    result = _result_from_recorded_statuses(
        workspace=workspace,
        selected_job_ids=selected_job_ids,
        job_definitions=job_definitions,
        act_exit_code=act_exit_code,
    )
    runtime._write_job_statuses(workspace, result.job_statuses)
    runtime.write_job_summaries(workspace, _act_step_order_by_job(workspace))
    return result


def _require_workflow(scenario: HarnessScenario) -> WorkflowScenario:
    """Return the validated workflow block of an `act` scenario."""

    if scenario.workflow is None:
        raise ValueError("act scenarios must define a workflow block")
    return scenario.workflow


def _create_workspace(
    self_repository_root: Path,
    root_dir: Path | None,
    *,
    seed_workspace: runtime.HarnessWorkspace | None,
) -> runtime.HarnessWorkspace:
    """Create one fresh workspace rooted at a local clone of the workflow repository."""

    workspace_root = runtime.create_workspace_root(root_dir)
    if seed_workspace is None:
        _materialize_git_checkout(self_repository_root, workspace_root)
    else:
        _materialize_git_repository_state(seed_workspace.root, workspace_root)
    workspace = runtime.workspace_paths(workspace_root)
    runtime.ensure_workspace_directories(workspace)
    if seed_workspace is not None:
        _seed_workspace_state(seed_workspace, workspace)
    return workspace


def _seed_workspace_state(
    seed_workspace: runtime.HarnessWorkspace,
    workspace: runtime.HarnessWorkspace,
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
    workspace: runtime.HarnessWorkspace,
    scenario: HarnessScenario,
    bindings: ResolvedReleaseHarnessConfig,
    *,
    seed_workspace: runtime.HarnessWorkspace | None,
) -> None:
    """Materialize repo bindings, workspace fixtures, and shims for an `act` run."""

    _stage_repository_sources(workspace, bindings, seed_workspace=seed_workspace)
    workflow = _require_workflow(scenario)
    if workflow.gpg_fixture == "generated-signing-key":
        _generated_gpg_private_key_path(workspace)
    _prepare_local_svn_fixture(workspace, scenario, seed_workspace=seed_workspace)
    _overlay_release_config_for_local_svn(workspace, scenario)
    _apply_workflow_repository_fixture(workspace, scenario)
    for file_fixture in scenario.workspace_files:
        runtime._write_workspace_file(
            workspace.root,
            file_fixture.path,
            file_fixture.content,
            file_fixture.executable,
        )
    for repository in scenario.git_repositories:
        runtime._init_git_repository(workspace.root, repository)
    runtime._write_shim_state(workspace, scenario)
    runtime._write_bash_env_hook(workspace, scenario)
    _write_generic_tool_shims(workspace, scenario)
    _write_bash_shim(workspace)
    _write_uv_shim(workspace, scenario)
    workspace.job_status_file.write_text("{}", encoding="utf-8")
    workspace.trace_file.write_text("", encoding="utf-8")


def _prepare_workflow_execution(
    workspace: runtime.HarnessWorkspace,
    scenario: HarnessScenario,
    bindings: ResolvedReleaseHarnessConfig,
) -> None:
    """Write generated composite actions, event payload, and rewritten workflow YAML."""

    workflow = _require_workflow(scenario)
    _write_setup_uv_noop_action(workspace)
    _write_local_checkout_action(workspace)
    rewritten_workflow = _rewrite_workflow(
        workspace=workspace,
        workflow_path=Path(workflow.path),
        scenario=scenario,
        bindings=bindings,
    )
    event_payload = {
        "inputs": dict(workflow.inputs),
    }
    (workspace.harness_dir / "act-event.json").write_text(
        json.dumps(event_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (workspace.harness_dir / "active-workflow.txt").write_text(str(rewritten_workflow), encoding="utf-8")


def _run_act(
    workspace: runtime.HarnessWorkspace,
    scenario: HarnessScenario,
    *,
    selected_job_ids: list[str] | None,
) -> int:
    """Execute the rewritten workflow through `act` and return its exit code."""

    workflow = _require_workflow(scenario)
    rewritten_workflow = _active_workflow_path(workspace)
    command = [
        *_resolve_act_command(),
        workflow.event,
        "--bind",
        "-W",
        str(rewritten_workflow),
        "-e",
        str(workspace.harness_dir / "act-event.json"),
        "--secret-file",
        str(_write_secrets_file(workspace, scenario)),
        "--rm",
        *_runner_image_args(),
    ]
    if selected_job_ids:
        for job_id in selected_job_ids:
            command.extend(["-j", job_id])
    _progress(f"running command: {shlex.join(command)}")
    stdout_path = workspace.harness_dir / "act-stdout.log"
    stderr_path = workspace.harness_dir / "act-stderr.log"
    with stdout_path.open("a", encoding="utf-8") as stdout_handle, stderr_path.open(
        "a", encoding="utf-8"
    ) as stderr_handle:
        process = subprocess.Popen(  # noqa: S603
            command,
            cwd=str(workspace.root),
            env=_act_process_env(scenario),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout_thread = _start_stream_thread(process.stdout, stdout_handle)
        stderr_thread = _start_stream_thread(process.stderr, stderr_handle)
        return_code = process.wait()
        stdout_thread.join()
        stderr_thread.join()
    return return_code


def _start_stream_thread(stream: IO[str] | None, log_handle: IO[str]) -> threading.Thread:
    """Start one background forwarder that tees a process stream into the log and stderr."""

    def forward() -> None:
        if stream is None:
            return
        try:
            for chunk in iter(stream.readline, ""):
                if not chunk:
                    break
                log_handle.write(chunk)
                log_handle.flush()
                sys.stderr.write(chunk)
                sys.stderr.flush()
        finally:
            stream.close()

    thread = threading.Thread(target=forward, daemon=True)
    thread.start()
    return thread


def _runner_image_args() -> list[str]:
    """Return explicit `act` runner-image mappings to avoid first-run interactive prompts."""

    return [
        "-P",
        "ubuntu-latest=catthehacker/ubuntu:act-latest",
        "-P",
        "ubuntu-22.04=catthehacker/ubuntu:act-22.04",
        "-P",
        "ubuntu-20.04=catthehacker/ubuntu:act-20.04",
        "-P",
        "ubuntu-18.04=catthehacker/ubuntu:act-18.04",
    ]


def _resolve_act_command() -> list[str]:
    """Resolve the preferred local `act` command, with the gh-act extension binary as fallback."""

    if shutil.which("act") is not None:
        return ["act"]
    gh_act_path = _find_gh_act_extension_binary()
    if gh_act_path is not None:
        return [str(gh_act_path)]
    raise HarnessExternalToolError(
        "buildish-release-harness act backend requires either the 'act' executable on PATH "
        "or GitHub CLI with the 'gh act' extension installed"
    )


def _find_gh_act_extension_binary() -> Path | None:
    """Return the installed gh-act extension binary path when present."""

    candidate_roots = [
        Path.home() / ".local" / "share" / "gh" / "extensions",
        Path.home() / ".config" / "gh" / "extensions",
    ]
    for root in candidate_roots:
        candidate = root / "gh-act" / "gh-act"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def _act_process_env(scenario: HarnessScenario) -> dict[str, str]:
    """Return the host-side environment used to launch `act` itself."""

    env = dict(os.environ)
    env.update(scenario.env)
    return env


def _progress(message: str) -> None:
    """Emit one human-facing progress line for the `act` backend."""

    sys.stderr.write(f"buildish-release-harness: {message}\n")
    sys.stderr.flush()


def _write_secrets_file(workspace: runtime.HarnessWorkspace, scenario: HarnessScenario) -> Path:
    """Write one `act` secret file from the scenario-provided secret map."""

    secrets = dict(scenario.secrets)
    destination = workspace.harness_dir / "act.secrets"
    lines = [f"{key}={value}" for key, value in sorted(secrets.items())]
    destination.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return destination


def _generated_gpg_private_key(workspace: runtime.HarnessWorkspace) -> str:
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


def _generated_gpg_private_key_path(workspace: runtime.HarnessWorkspace) -> Path:
    """Return the workspace file that stores the generated harness private key."""

    _generated_gpg_private_key(workspace)
    return workspace.harness_dir / "gpg-fixture" / "private.asc"


def _active_workflow_path(workspace: runtime.HarnessWorkspace) -> Path:
    """Return the currently prepared rewritten workflow path for one workspace."""

    return Path((workspace.harness_dir / "active-workflow.txt").read_text(encoding="utf-8").strip())


def _act_step_order_by_job(workspace: runtime.HarnessWorkspace) -> dict[str, list[str]]:
    """Return original step identifiers in workflow order for each rewritten job."""

    payload = _load_github_actions_yaml(_active_workflow_path(workspace))
    jobs = payload.get("jobs")
    if not isinstance(jobs, dict):
        return {}
    step_order_by_job: dict[str, list[str]] = {}
    for job_id, job_payload in jobs.items():
        if not isinstance(job_payload, dict):
            continue
        step_ids: list[str] = []
        for step_payload in list(job_payload.get("steps") or []):
            if not isinstance(step_payload, dict):
                continue
            env = step_payload.get("env")
            if not isinstance(env, dict):
                continue
            step_id = env.get("BUILDISH_HARNESS_STEP_ID")
            if isinstance(step_id, str) and step_id:
                step_ids.append(step_id)
        step_order_by_job[str(job_id)] = step_ids
    return step_order_by_job


def _stage_repository_sources(
    workspace: runtime.HarnessWorkspace,
    bindings: ResolvedReleaseHarnessConfig,
    *,
    seed_workspace: runtime.HarnessWorkspace | None,
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
    workspace: runtime.HarnessWorkspace,
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
    workspace: runtime.HarnessWorkspace,
    scenario: HarnessScenario,
    *,
    seed_workspace: runtime.HarnessWorkspace | None,
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


def _overlay_release_config_for_local_svn(
    workspace: runtime.HarnessWorkspace,
    scenario: HarnessScenario,
) -> None:
    """Rewrite the workspace release-config to use the harness-owned local ASF SVN repository."""

    del scenario
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


def _component_release_config_path(workspace: runtime.HarnessWorkspace) -> Path:
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


def _refresh_svn_working_copy(workspace: runtime.HarnessWorkspace) -> None:
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
    workspace: runtime.HarnessWorkspace,
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


def _load_job_definitions(workflow_path: Path) -> list[WorkflowJobDefinition]:
    """Load one workflow YAML file and extract the declared job graph."""

    payload = _load_github_actions_yaml(workflow_path)
    jobs = payload.get("jobs")
    if not isinstance(jobs, dict):
        raise ValueError(f"workflow {workflow_path} does not define a jobs mapping")
    definitions: list[WorkflowJobDefinition] = []
    for job_id, job_payload in jobs.items():
        if not isinstance(job_payload, dict):
            raise ValueError(f"workflow job {job_id} must be a mapping")
        definitions.append(
            WorkflowJobDefinition(
                id=str(job_id),
                needs=_normalize_needs(job_payload.get("needs")),
            )
        )
    return definitions


def _normalize_needs(raw_needs: Any) -> list[str]:
    """Normalize one workflow `needs` field into a flat string list."""

    if raw_needs is None:
        return []
    if isinstance(raw_needs, str):
        return [raw_needs]
    if isinstance(raw_needs, list):
        return [str(item) for item in raw_needs]
    raise ValueError(f"unsupported needs value: {raw_needs!r}")


def _topological_job_ids(job_definitions: list[WorkflowJobDefinition]) -> list[str]:
    """Return workflow job identifiers in dependency order."""

    pending = {definition.id: definition for definition in job_definitions}
    ordered: list[str] = []
    resolved: set[str] = set()
    while pending:
        progress_made = False
        for definition in job_definitions:
            if definition.id not in pending:
                continue
            if all(need in resolved for need in definition.needs):
                ordered.append(definition.id)
                resolved.add(definition.id)
                del pending[definition.id]
                progress_made = True
        if not progress_made:
            unresolved = ", ".join(sorted(pending))
            raise RuntimeError(f"cyclic or unresolved workflow jobs: {unresolved}")
    return ordered


def _rewrite_workflow(
    *,
    workspace: runtime.HarnessWorkspace,
    workflow_path: Path,
    scenario: HarnessScenario,
    bindings: ResolvedReleaseHarnessConfig,
) -> Path:
    """Rewrite a workflow for deterministic local execution through `act`."""

    payload = _load_github_actions_yaml(workflow_path)
    payload.setdefault("env", {})
    if not isinstance(payload["env"], dict):
        raise ValueError(f"workflow {workflow_path} has a non-mapping env block")
    payload["env"] = {**payload["env"], **scenario.env}
    jobs = payload.get("jobs")
    if not isinstance(jobs, dict):
        raise ValueError(f"workflow {workflow_path} does not define a jobs mapping")
    for job_id, job_payload in jobs.items():
        if not isinstance(job_payload, dict):
            raise ValueError(f"workflow job {job_id} must be a mapping")
        original_steps = list(job_payload.get("steps") or [])
        rewritten_steps: list[dict[str, Any]] = [_bootstrap_step()]
        generated_action_references = _generated_action_references(workspace)
        real_cli_commands = set(_require_workflow(scenario).real_cli_commands)
        for index, step_payload in enumerate(original_steps, start=1):
            if not isinstance(step_payload, dict):
                raise ValueError(f"workflow job {job_id} contains a non-mapping step")
            rewritten_steps.append(
                _rewrite_step(
                    job_id=str(job_id),
                    step_payload=step_payload,
                    step_index=index,
                    bindings=bindings,
                    generated_action_references=generated_action_references,
                    real_cli_commands=real_cli_commands,
                    generated_gpg_fixture=_require_workflow(scenario).gpg_fixture
                    == "generated-signing-key",
                )
            )
        rewritten_steps.append(_job_status_step(str(job_id)))
        job_payload["steps"] = rewritten_steps
    destination = workspace.root / ".github" / "workflows" / workflow_path.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    original_copy = destination.with_name(f"{destination.stem}.original{destination.suffix}")
    original_copy.write_text(workflow_path.read_text(encoding="utf-8"), encoding="utf-8")
    destination.write_text(
        _render_rewritten_workflow_yaml(
            payload,
            original_workflow_path=workflow_path,
            original_copy_name=original_copy.name,
        ),
        encoding="utf-8",
    )
    return destination


def _dump_workflow_yaml(payload: dict[str, Any]) -> str:
    """Dump rewritten workflow YAML while keeping the GitHub Actions `on` key literal."""

    rendered = yaml.dump(
        payload,
        Dumper=_GithubActionsYamlDumper,
        sort_keys=False,
        width=1000,
    )
    return re.sub(r"(?m)^([ ]*)['\"]on['\"]:$", r"\1on:", rendered)


def _render_rewritten_workflow_yaml(
    payload: dict[str, Any],
    *,
    original_workflow_path: Path,
    original_copy_name: str,
) -> str:
    """Render one rewritten workflow with a prominent harness-generated header comment."""

    header = "\n".join(
        [
            "# WARNING: This is not the original workflow file.",
            "# This file was generated by buildish-release-harness for local test execution.",
            f"# Original workflow source: {original_workflow_path}",
            f"# Verbatim original copy in this directory: {original_copy_name}",
            "",
        ]
    )
    return header + _dump_workflow_yaml(payload)


def _bootstrap_step() -> dict[str, Any]:
    """Return the injected step that exports harness paths through `GITHUB_ENV`."""

    return {
        "name": "Harness bootstrap environment",
        "shell": "bash",
        "run": (
            "mkdir -p \"$GITHUB_WORKSPACE/.buildish-release-harness/job-statuses\"\n"
            "{\n"
            "  printf 'PATH=%s/.buildish-release-harness/shims:%s\\n' \"$GITHUB_WORKSPACE\" \"$PATH\"\n"
            "  printf 'BUILDISH_HARNESS_STATE_FILE=%s/.buildish-release-harness/shim-state.json\\n' \"$GITHUB_WORKSPACE\"\n"
            "  printf 'BUILDISH_HARNESS_REAL_PATH=%s\\n' \"$PATH\"\n"
            "  printf 'BUILDISH_HARNESS_BASH_ENV_FILE=%s/.buildish-release-harness/bash-env.sh\\n' \"$GITHUB_WORKSPACE\"\n"
            "  printf 'BUILDISH_HARNESS_SUMMARIES_DIR=%s/.buildish-release-harness/summaries\\n' \"$GITHUB_WORKSPACE\"\n"
            "  printf 'BUILDISH_HARNESS_TOOLING_SOURCE_DIR=%s/.buildish-release-harness/repo-sources/apache__buildish-release-tooling\\n' \"$GITHUB_WORKSPACE\"\n"
            "  printf 'BUILDISH_ALLOW_NON_PRODUCTION_RELEASE_TARGETS=true\\n'\n"
            "  if [[ -n \"${PYTHONPATH:-}\" ]]; then\n"
            "    printf 'PYTHONPATH=%s/.buildish-release-harness/repo-sources/apache__buildish-release-tooling/src:%s\\n' \"$GITHUB_WORKSPACE\" \"$PYTHONPATH\"\n"
            "  else\n"
            "    printf 'PYTHONPATH=%s/.buildish-release-harness/repo-sources/apache__buildish-release-tooling/src\\n' \"$GITHUB_WORKSPACE\"\n"
            "  fi\n"
            "} >> \"$GITHUB_ENV\"\n"
            "gpg_key_file=\"$GITHUB_WORKSPACE/.buildish-release-harness/gpg-fixture/private.asc\"\n"
            "if [[ -f \"$gpg_key_file\" ]]; then\n"
            "  {\n"
            "    printf 'BUILDISH_GPG_PRIVATE_KEY<<__BUILDISH_HARNESS_GPG_KEY__\\n'\n"
            "    cat \"$gpg_key_file\"\n"
            "    printf '__BUILDISH_HARNESS_GPG_KEY__\\n'\n"
            "  } >> \"$GITHUB_ENV\"\n"
            "fi\n"
        ),
    }


def _rewrite_step(
    *,
    job_id: str,
    step_payload: dict[str, Any],
    step_index: int,
    bindings: ResolvedReleaseHarnessConfig,
    generated_action_references: dict[str, str],
    real_cli_commands: set[str],
    generated_gpg_fixture: bool,
) -> dict[str, Any]:
    """Rewrite one workflow step for local harness execution."""

    uses = step_payload.get("uses")
    if (
        isinstance(uses, str)
        and uses.startswith("astral-sh/setup-uv@")
        and not real_cli_commands
    ):
        rewritten = {key: value for key, value in step_payload.items() if key not in {"uses", "with"}}
        rewritten["uses"] = generated_action_references["setup-uv-noop"]
        return rewritten
    if isinstance(uses, str) and uses.startswith("actions/checkout@"):
        rewritten_checkout = _rewrite_checkout_step(
            step_payload,
            bindings,
            generated_action_references["local-checkout"],
        )
        if rewritten_checkout is not None:
            return rewritten_checkout
    if "run" not in step_payload:
        return dict(step_payload)
    step_id = _step_identifier(step_payload, step_index)
    rewritten = dict(step_payload)
    env = dict(rewritten.get("env") or {})
    if generated_gpg_fixture:
        env.pop("BUILDISH_GPG_PRIVATE_KEY", None)
    env["BUILDISH_HARNESS_JOB_ID"] = job_id
    env["BUILDISH_HARNESS_STEP_ID"] = step_id
    rewritten["env"] = env
    return rewritten


def _rewrite_checkout_step(
    step_payload: dict[str, Any],
    bindings: ResolvedReleaseHarnessConfig,
    generated_action_reference: str,
) -> dict[str, Any] | None:
    """Rewrite one `actions/checkout` step to the generated local composite action."""

    with_payload = dict(step_payload.get("with") or {})
    repository_id = str(with_payload.get("repository", bindings.self_repository.repository_id))
    source_binding: ResolvedRepositoryBinding | None = None
    mode: str | None = None
    if "repository" not in with_payload:
        if bindings.self_repository.local_checkout_mode == "when_repository_omitted":
            source_binding = bindings.self_repository
            mode = "local-git-clone"
    else:
        source_binding = bindings.repository_overrides.get(repository_id)
        if source_binding is not None and source_binding.local_checkout_mode == "always":
            mode = "local-source-tree"
    if source_binding is None or mode is None:
        return None
    rewritten = {key: value for key, value in step_payload.items() if key not in {"uses", "with"}}
    rewritten["uses"] = generated_action_reference
    rewritten["with"] = {
        "source_path": f".buildish-release-harness/repo-sources/{_repository_slug(repository_id)}",
        "path": str(with_payload.get("path", ".")),
        "ref": str(with_payload.get("ref", "")),
        "mode": mode,
    }
    return rewritten


def _generated_action_references(workspace: runtime.HarnessWorkspace) -> dict[str, str]:
    """Return stable `uses:` references for generated harness actions from the repo root."""

    return {
        "local-checkout": "./.buildish-release-harness/actions/local-checkout",
        "setup-uv-noop": "./.buildish-release-harness/actions/setup-uv-noop",
    }


def _step_identifier(step_payload: dict[str, Any], step_index: int) -> str:
    """Return a stable identifier for one workflow step."""

    raw_identifier = step_payload.get("id")
    if isinstance(raw_identifier, str) and raw_identifier:
        return raw_identifier
    raw_name = step_payload.get("name")
    if isinstance(raw_name, str) and raw_name:
        normalized = re.sub(r"[^A-Za-z0-9]+", "-", raw_name).strip("-").lower()
        if normalized:
            return normalized
    return f"step-{step_index}"


def _job_status_step(job_id: str) -> dict[str, Any]:
    """Return the injected terminal step that records the job outcome."""

    return {
        "name": "Harness record job status",
        "if": "${{ always() }}",
        "shell": "bash",
        "env": {
            "BUILDISH_HARNESS_JOB_STATUS": "${{ job.status }}",
        },
        "run": (
            "printf '%s\\n' \"$BUILDISH_HARNESS_JOB_STATUS\" > "
            f"\"$GITHUB_WORKSPACE/.buildish-release-harness/job-statuses/{job_id}.status\"\n"
        ),
    }


def _write_setup_uv_noop_action(workspace: runtime.HarnessWorkspace) -> None:
    """Write the generated no-op composite action used to replace `setup-uv`."""

    action_dir = workspace.actions_dir / "setup-uv-noop"
    action_dir.mkdir(parents=True, exist_ok=True)
    (action_dir / "action.yml").write_text(
        yaml.safe_dump(
            {
                "name": "Buildish harness setup-uv noop",
                "runs": {
                    "using": "composite",
                    "steps": [
                        {
                            "shell": "bash",
                            "run": "printf 'buildish-release-harness: setup-uv no-op\\n'",
                        }
                    ],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_local_checkout_action(workspace: runtime.HarnessWorkspace) -> None:
    """Write the generated composite action that materializes local checkout overrides."""

    action_dir = workspace.actions_dir / "local-checkout"
    action_dir.mkdir(parents=True, exist_ok=True)
    script_path = action_dir / "local-checkout.sh"
    script_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'source_path="${INPUT_SOURCE_PATH:?}"',
                'mode="${INPUT_MODE:?}"',
                'target_path="${INPUT_PATH:-.}"',
                'ref="${INPUT_REF:-}"',
                'if [[ "$source_path" != /* ]]; then',
                '  source_path="$GITHUB_WORKSPACE/$source_path"',
                "fi",
                'if [[ "$target_path" == "." ]]; then',
                "  exit 0",
                "fi",
                'destination="$GITHUB_WORKSPACE/$target_path"',
                'rm -rf "$destination"',
                'mkdir -p "$(dirname "$destination")"',
                'case "$mode" in',
                '  local-git-clone)',
                '    git clone --local "$source_path" "$destination"',
                '    if [[ -n "$ref" ]]; then',
                '      git -C "$destination" checkout "$ref"',
                "    fi",
                "    ;;",
                '  local-source-tree)',
                '    mkdir -p "$destination"',
                '    cp -a "$source_path"/. "$destination"/',
                '    rm -rf "$destination/.git"',
                "    ;;",
                "  *)",
                '    printf "unsupported harness checkout mode: %s\\n" "$mode" >&2',
                "    exit 2",
                "    ;;",
                "esac",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    script_path.chmod(script_path.stat().st_mode | 0o111)
    (action_dir / "action.yml").write_text(
        yaml.safe_dump(
            {
                "name": "Buildish harness local checkout",
                "inputs": {
                    "source_path": {"required": True},
                    "path": {"required": False},
                    "ref": {"required": False},
                    "mode": {"required": True},
                },
                "runs": {
                    "using": "composite",
                    "steps": [
                        {
                            "shell": "bash",
                            "run": 'bash "$GITHUB_ACTION_PATH/local-checkout.sh"',
                        }
                    ],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_bash_shim(workspace: runtime.HarnessWorkspace) -> None:
    """Write the `bash` shim that redirects step summaries and enables `BASH_ENV` hooks."""

    script_path = workspace.shims_dir / "bash"
    script_path.write_text(
        "\n".join(
            [
                "#!/bin/bash",
                "set -euo pipefail",
                'real_path="${BUILDISH_HARNESS_REAL_PATH:-/usr/bin:/bin}"',
                'real_bash="$(PATH="$real_path" command -v bash || true)"',
                'if [[ -z "$real_bash" ]]; then',
                '  printf "buildish-release-harness: could not locate real bash\\n" >&2',
                "  exit 127",
                "fi",
                'original_summary="${GITHUB_STEP_SUMMARY:-}"',
                'capture_summary=""',
                'if [[ -n "${BUILDISH_HARNESS_SUMMARIES_DIR:-}" && -n "${BUILDISH_HARNESS_JOB_ID:-}" && -n "${BUILDISH_HARNESS_STEP_ID:-}" ]]; then',
                '  capture_summary="$BUILDISH_HARNESS_SUMMARIES_DIR/${BUILDISH_HARNESS_JOB_ID}__${BUILDISH_HARNESS_STEP_ID}.md"',
                '  mkdir -p "$(dirname "$capture_summary")"',
                '  : > "$capture_summary"',
                '  export BUILDISH_ORIGINAL_GITHUB_STEP_SUMMARY="$original_summary"',
                '  export GITHUB_STEP_SUMMARY="$capture_summary"',
                "fi",
                'if [[ -n "${BUILDISH_HARNESS_BASH_ENV_FILE:-}" ]]; then',
                '  export BASH_ENV="$BUILDISH_HARNESS_BASH_ENV_FILE"',
                "fi",
                "set +e",
                '"$real_bash" "$@"',
                'status="$?"',
                "set -e",
                'if [[ -n "$capture_summary" && -n "$original_summary" && "$capture_summary" != "$original_summary" ]]; then',
                '  cat "$capture_summary" > "$original_summary"',
                "fi",
                'exit "$status"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    script_path.chmod(script_path.stat().st_mode | 0o111)


def _write_generic_tool_shims(workspace: runtime.HarnessWorkspace, scenario: HarnessScenario) -> None:
    """Write container-safe executable shims for all intercepted non-shell tools."""

    tools = sorted(set(scenario.tool_behaviors) | {"gh", "docker", "java", "javac"})
    for tool in tools:
        script_path = workspace.shims_dir / tool
        script_path.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env bash",
                    "set -euo pipefail",
                    "exec python3 -m apache_buildish_release_tooling.harness.shim_entrypoint "
                    f"{json.dumps(tool)} \"$@\"",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        script_path.chmod(script_path.stat().st_mode | 0o111)


def _render_uv_shim_script(real_cli_commands: list[str]) -> str:
    """Return the generated `uv` shim script for one act workspace."""

    real_cli_case = "|".join(real_cli_commands)
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        'original_args=("$@")',
        'resolve_real_uv() {',
        '  local shim_dir resolved_path joined_path',
        '  local -a path_parts=()',
        '  local -a search_parts=()',
        '  shim_dir="$(cd "$(dirname "$0")" && pwd)"',
        '  IFS=: read -r -a path_parts <<<"${PATH:-}"',
        '  for part in "${path_parts[@]}"; do',
        '    if [[ -n "$part" && "$part" != "$shim_dir" ]]; then',
        '      search_parts+=("$part")',
        "    fi",
        "  done",
        '  joined_path="$(IFS=:; printf "%s" "${search_parts[*]}")"',
        '  resolved_path="$(PATH="$joined_path" command -v uv || true)"',
        '  if [[ -n "$resolved_path" ]]; then',
        '    printf "%s\\n" "$resolved_path"',
        "  fi",
        "}",
        'if [[ "${1:-}" == "python" && "${2:-}" == "install" ]]; then',
        '  if resolved_uv="$(resolve_real_uv)"; then',
        '    exec "$resolved_uv" "${original_args[@]}"',
        "  fi",
        "  exit 0",
        "fi",
        'if [[ "${1:-}" != "run" ]]; then',
        '  printf "buildish-release-harness: unsupported uv invocation: %s\\n" "$*" >&2',
        "  exit 2",
        "fi",
        "shift",
        'while [[ $# -gt 0 ]]; do',
        '  case "$1" in',
        '    --project)',
        "      shift 2",
        "      ;;",
        '    --frozen)',
        "      shift",
        "      ;;",
        '    buildish-release-tooling)',
        "      shift",
        '      command_name="${1:-}"',
        '      if [[ "$command_name" == "--allow-non-production-release-targets" ]]; then',
        '        command_name="${2:-}"',
        "      fi",
        '      if [[ -z "$command_name" ]]; then',
        '        printf "buildish-release-harness: missing buildish-release-tooling command\\n" >&2',
        "        exit 2",
        "      fi",
    ]
    if real_cli_case:
        lines.extend(
            [
                '      case "$command_name" in',
                f"        {real_cli_case})",
                '          if resolved_uv="$(resolve_real_uv)"; then',
                '            exec "$resolved_uv" "${original_args[@]}"',
                "          fi",
                '          exec python3 -m apache_buildish_release_tooling "$@"',
                "          ;;",
                "      esac",
            ]
        )
    lines.extend(
        [
            '      filtered_args=()',
            '      while [[ $# -gt 0 ]]; do',
            '        case "$1" in',
            '          --allow-non-production-release-targets)',
            "            shift",
            "            ;;",
            '          --component-config)',
            "            shift 2",
            "            ;;",
            "          *)",
            '            filtered_args+=("$1")',
            "            shift",
            "            ;;",
            "        esac",
            "      done",
            '      exec python3 -m apache_buildish_release_tooling.harness.shim_entrypoint buildish-release-tooling "${filtered_args[@]}"',
            "      ;;",
            "    *)",
            '      printf "buildish-release-harness: unexpected uv arguments: %s\\n" "$*" >&2',
            "      exit 2",
            "      ;;",
            "  esac",
            "done",
            'printf "buildish-release-harness: uv did not receive a command\\n" >&2',
            "exit 2",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_uv_shim(workspace: runtime.HarnessWorkspace, scenario: HarnessScenario) -> None:
    """Write the `uv` shim used by the rewritten workflows."""

    script_path = workspace.shims_dir / "uv"
    workflow = _require_workflow(scenario)
    script_path.write_text(
        _render_uv_shim_script(workflow.real_cli_commands),
        encoding="utf-8",
    )
    script_path.chmod(script_path.stat().st_mode | 0o111)


def _repository_slug(repository_id: str) -> str:
    """Return a filesystem-safe repository slug used under `.buildish-release-harness/repo-sources`."""

    return repository_id.replace("/", "__")


def _job_status_directory(workspace: runtime.HarnessWorkspace) -> Path:
    """Return the directory containing per-job status files emitted by the rewritten workflow."""

    return workspace.job_statuses_dir


def _collect_recorded_job_statuses(workspace: runtime.HarnessWorkspace) -> dict[str, str]:
    """Load all job-status files emitted by the rewritten workflow."""

    statuses: dict[str, str] = {}
    for path in sorted(_job_status_directory(workspace).glob("*.status")):
        statuses[path.stem] = _normalize_job_status(path.read_text(encoding="utf-8").strip())
    return statuses


def _clear_job_status_files(workspace: runtime.HarnessWorkspace, selected_job_ids: list[str]) -> None:
    """Remove stale status files for the jobs that are about to be rerun."""

    for job_id in selected_job_ids:
        path = _job_status_directory(workspace) / f"{job_id}.status"
        if path.exists():
            path.unlink()


def _result_from_recorded_statuses(
    *,
    workspace: runtime.HarnessWorkspace,
    selected_job_ids: list[str],
    job_definitions: list[WorkflowJobDefinition],
    act_exit_code: int,
) -> runtime.HarnessRunResult:
    """Normalize per-job status files into the shared harness run-result shape."""

    recorded_statuses = _collect_recorded_job_statuses(workspace)
    all_statuses = runtime._load_job_statuses(workspace)
    all_statuses.update(recorded_statuses)
    selected_set = set(selected_job_ids)
    failed_job_ids: list[str] = []
    blocked_job_ids: list[str] = []
    pending_failure = act_exit_code != 0 and not recorded_statuses
    for job_id in _topological_job_ids(job_definitions):
        if job_id not in selected_set:
            continue
        recorded = recorded_statuses.get(job_id)
        if recorded is not None:
            all_statuses[job_id] = recorded
            if recorded != "success":
                failed_job_ids.append(job_id)
            continue
        needs = _job_needs(job_definitions, job_id)
        if any(all_statuses.get(need) != "success" for need in needs if need in selected_set):
            all_statuses[job_id] = "blocked"
            blocked_job_ids.append(job_id)
            continue
        if pending_failure:
            all_statuses[job_id] = "failed"
            failed_job_ids.append(job_id)
            pending_failure = False
            continue
        if act_exit_code == 0:
            all_statuses[job_id] = "success"
        else:
            all_statuses[job_id] = "failed"
            failed_job_ids.append(job_id)
    return runtime.HarnessRunResult(
        workspace=workspace,
        selected_job_ids=selected_job_ids,
        failed_job_ids=failed_job_ids,
        blocked_job_ids=blocked_job_ids,
        job_statuses=all_statuses,
    )


def _job_needs(job_definitions: list[WorkflowJobDefinition], job_id: str) -> list[str]:
    """Return the normalized `needs` list for one workflow job."""

    for definition in job_definitions:
        if definition.id == job_id:
            return definition.needs
    raise KeyError(job_id)


def _rerunnable_job_ids(
    job_definitions: list[WorkflowJobDefinition],
    statuses: dict[str, str],
) -> list[str]:
    """Return failed jobs and their downstream dependents in workflow-topological order."""

    failed_or_blocked = {
        job_id for job_id, status in statuses.items() if status in {"failed", "blocked"}
    }
    if not failed_or_blocked:
        return []
    dependents: dict[str, set[str]] = {definition.id: set() for definition in job_definitions}
    for definition in job_definitions:
        for need in definition.needs:
            dependents.setdefault(need, set()).add(definition.id)
    selected = set(failed_or_blocked)
    stack = list(failed_or_blocked)
    while stack:
        current = stack.pop()
        for dependent in dependents.get(current, set()):
            if dependent not in selected:
                selected.add(dependent)
                stack.append(dependent)
    return [job_id for job_id in _topological_job_ids(job_definitions) if job_id in selected]


def _normalize_job_status(raw_status: str) -> str:
    """Normalize runner-reported job states into the shared harness status vocabulary."""

    return {
        "failure": "failed",
        "success": "success",
    }.get(raw_status, raw_status or "unknown")
