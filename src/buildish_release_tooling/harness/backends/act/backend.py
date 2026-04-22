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

"""`act` execution backend for the Buildish release harness."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import IO

from buildish_release_tooling.harness.backends.base import Backend
from buildish_release_tooling.harness.config import load_release_harness_config
from buildish_release_tooling.harness.errors import HarnessExternalToolError
from buildish_release_tooling.harness.job_selection import rerunnable_job_ids
from buildish_release_tooling.harness.models import (
    HarnessJobStatus,
    HarnessScenario,
    HarnessShimState,
    WorkflowScenario,
)
from buildish_release_tooling.harness.process import wait_for_harness_process
from buildish_release_tooling.harness.runtime import (
    HarnessRunResult,
    HarnessWorkspace,
    load_existing_workspace,
    load_job_statuses,
    write_job_statuses,
    write_job_summaries,
)
from buildish_release_tooling.shared.parsing import (
    DEFAULT_CONFIG_PARSE_MAX_BYTES,
    read_pydantic_json_file_bounded,
)

from . import fixtures, workflow


class ActBackend(Backend):
    """GitHub Actions workflow backend powered by the local `act` runner."""

    name = "act"

    def run_scenario(
        self,
        scenario: HarnessScenario,
        *,
        workspace_root: Path | None = None,
        seed_from: Path | None = None,
    ) -> HarnessRunResult:
        """Run one `act`-backed harness scenario in a fresh disposable workspace."""

        workflow_scenario = _require_workflow(scenario)
        _progress(f"loading harness config {workflow_scenario.harness_config}")
        bindings = load_release_harness_config(Path(workflow_scenario.harness_config))
        seed_workspace = (
            load_existing_workspace(seed_from) if seed_from is not None else None
        )
        if seed_workspace is not None:
            _progress(f"seeding workspace state from {seed_workspace.root}")
        workspace = fixtures._create_workspace(
            bindings.self_repository.local_path,
            workspace_root,
            seed_workspace=seed_workspace,
        )
        _progress(f"created workspace {workspace.root}")
        _progress(f"bootstrapping workspace for scenario {scenario.name}")
        fixtures._bootstrap_workspace(
            workspace, scenario, bindings, seed_workspace=seed_workspace
        )
        job_definitions = workflow._load_job_definitions(Path(workflow_scenario.path))
        selected_job_ids = workflow._topological_job_ids(job_definitions)
        _progress(f"preparing rewritten workflow {workflow_scenario.path}")
        _prepare_workflow_execution(workspace, scenario, bindings)
        _progress("invoking act for all jobs")
        act_exit_code = _run_act(workspace, scenario, selected_job_ids=None)
        fixtures._refresh_svn_working_copy(workspace)
        result = _result_from_recorded_statuses(
            workspace=workspace,
            selected_job_ids=selected_job_ids,
            job_definitions=job_definitions,
            act_exit_code=act_exit_code,
        )
        write_job_statuses(workspace, result.job_statuses)
        write_job_summaries(
            workspace,
            workflow._act_step_order_by_job(fixtures._active_workflow_path(workspace)),
        )
        return result

    def rerun_failed_jobs(
        self, scenario: HarnessScenario, workspace_root: Path
    ) -> HarnessRunResult:
        """Rerun the failed `act` jobs and their downstream dependents in an existing workspace."""

        workflow_scenario = _require_workflow(scenario)
        workspace = load_existing_workspace(workspace_root)
        persisted_statuses = load_job_statuses(workspace)
        job_definitions = workflow._load_job_definitions(Path(workflow_scenario.path))
        selected_job_ids = rerunnable_job_ids(
            workflow._topological_job_ids(job_definitions),
            {definition.id: definition.needs for definition in job_definitions},
            persisted_statuses,
        )
        if not selected_job_ids:
            _progress("no failed jobs to rerun")
            return HarnessRunResult(
                workspace=workspace,
                selected_job_ids=[],
                failed_job_ids=[],
                blocked_job_ids=[],
                job_statuses=persisted_statuses,
            )
        bindings = load_release_harness_config(Path(workflow_scenario.harness_config))
        _progress(f"re-preparing workspace {workspace.root} for rerun")
        _prepare_workflow_execution(workspace, scenario, bindings)
        _clear_job_status_files(workspace, selected_job_ids)
        _progress(f"invoking act for rerun jobs: {', '.join(selected_job_ids)}")
        act_exit_code = _run_act(workspace, scenario, selected_job_ids=selected_job_ids)
        fixtures._refresh_svn_working_copy(workspace)
        result = _result_from_recorded_statuses(
            workspace=workspace,
            selected_job_ids=selected_job_ids,
            job_definitions=job_definitions,
            act_exit_code=act_exit_code,
        )
        write_job_statuses(workspace, result.job_statuses)
        write_job_summaries(
            workspace,
            workflow._act_step_order_by_job(fixtures._active_workflow_path(workspace)),
        )
        return result


def _require_workflow(scenario: HarnessScenario) -> WorkflowScenario:
    """Return the validated workflow block of an `act` scenario."""

    if scenario.workflow is None:
        raise ValueError("act scenarios must define a workflow block")
    return scenario.workflow


def _prepare_workflow_execution(
    workspace: HarnessWorkspace,
    scenario: HarnessScenario,
    bindings,
) -> None:
    """Write generated composite actions, event payload, and rewritten workflow YAML."""

    workflow_scenario = _require_workflow(scenario)
    workflow._write_setup_uv_noop_action(workspace)
    workflow._write_local_checkout_action(workspace)
    workflow._write_local_artifact_actions(workspace)
    rewritten_workflow = workflow._rewrite_workflow(
        workspace=workspace,
        workflow_path=Path(workflow_scenario.path),
        scenario_env=scenario.env,
        bindings=bindings,
        real_cli_commands=set(workflow_scenario.real_cli_commands),
        generated_gpg_fixture=workflow_scenario.gpg_fixture == "generated-signing-key",
    )
    event_payload = {"inputs": _resolved_workflow_inputs(workspace, workflow_scenario)}
    (workspace.harness_dir / "act-event.json").write_text(
        json.dumps(event_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (workspace.harness_dir / "active-workflow.txt").write_text(
        str(rewritten_workflow), encoding="utf-8"
    )


def _resolved_workflow_inputs(
    workspace: HarnessWorkspace,
    workflow: WorkflowScenario,
) -> dict[str, str]:
    """Resolve explicit harness-only inputs from retained seeded provider state."""

    inputs = dict(workflow.inputs)
    prefix = "harness:seeded-release-asset-sha256:"
    for input_name, value in tuple(inputs.items()):
        if not value.startswith(prefix):
            continue
        asset_name = value.removeprefix(prefix)
        candidate_tag = inputs.get("candidate_tag", "")
        state = read_pydantic_json_file_bounded(
            HarnessShimState,
            workspace.state_file,
            max_bytes=DEFAULT_CONFIG_PARSE_MAX_BYTES,
        )
        release = state.gh_releases.get(candidate_tag)
        if release is None:
            continue
        matching_assets = [
            asset for asset in release.assets if asset.name == asset_name
        ]
        if len(matching_assets) != 1:
            raise ValueError(f"seeded GitHub Release requires one {asset_name} asset")
        algorithm, separator, digest = matching_assets[0].digest.partition(":")
        if separator != ":" or algorithm != "sha256" or not digest:
            raise ValueError("seeded GitHub Release asset lacks a SHA-256 digest")
        inputs[input_name] = digest
    return inputs


def _run_act(
    workspace: HarnessWorkspace,
    scenario: HarnessScenario,
    *,
    selected_job_ids: list[str] | None,
) -> int:
    """Execute the rewritten workflow through `act` and return its exit code."""

    workflow_scenario = _require_workflow(scenario)
    rewritten_workflow = fixtures._active_workflow_path(workspace)
    command = [
        *_resolve_act_command(),
        workflow_scenario.event,
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
    with (
        stdout_path.open("a", encoding="utf-8") as stdout_handle,
        stderr_path.open("a", encoding="utf-8") as stderr_handle,
    ):
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
        try:
            return_code = wait_for_harness_process(process)
        finally:
            stdout_thread.join()
            stderr_thread.join()
    return return_code


def _start_stream_thread(
    stream: IO[str] | None, log_handle: IO[str]
) -> threading.Thread:
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


def _write_secrets_file(workspace: HarnessWorkspace, scenario: HarnessScenario) -> Path:
    """Write one `act` secret file from the scenario-provided secret map."""

    secrets = dict(scenario.secrets)
    destination = workspace.harness_dir / "act.secrets"
    lines = [f"{key}={value}" for key, value in sorted(secrets.items())]
    destination.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return destination


def _job_status_directory(workspace: HarnessWorkspace) -> Path:
    """Return the directory containing per-job status files emitted by the rewritten workflow."""

    return workspace.job_statuses_dir


def _collect_recorded_job_statuses(
    workspace: HarnessWorkspace,
) -> dict[str, HarnessJobStatus]:
    """Load all job-status files emitted by the rewritten workflow."""

    statuses: dict[str, HarnessJobStatus] = {}
    for path in sorted(_job_status_directory(workspace).glob("*.status")):
        statuses[path.stem] = _normalize_job_status(
            path.read_text(encoding="utf-8").strip()
        )
    return statuses


def _clear_job_status_files(
    workspace: HarnessWorkspace, selected_job_ids: list[str]
) -> None:
    """Remove stale status files for the jobs that are about to be rerun."""

    for job_id in selected_job_ids:
        path = _job_status_directory(workspace) / f"{job_id}.status"
        if path.exists():
            path.unlink()


def _result_from_recorded_statuses(
    *,
    workspace: HarnessWorkspace,
    selected_job_ids: list[str],
    job_definitions: list[workflow.WorkflowJobDefinition],
    act_exit_code: int,
) -> HarnessRunResult:
    """Normalize per-job status files into the shared harness run-result shape."""

    recorded_statuses = _collect_recorded_job_statuses(workspace)
    all_statuses = load_job_statuses(workspace)
    all_statuses.update(recorded_statuses)
    selected_set = set(selected_job_ids)
    failed_job_ids: list[str] = []
    blocked_job_ids: list[str] = []
    pending_failure = act_exit_code != 0 and not recorded_statuses
    for job_id in workflow._topological_job_ids(job_definitions):
        if job_id not in selected_set:
            continue
        recorded = recorded_statuses.get(job_id)
        if recorded is not None:
            all_statuses[job_id] = recorded
            if recorded != "success":
                failed_job_ids.append(job_id)
            continue
        needs = _job_needs(job_definitions, job_id)
        if any(
            all_statuses.get(need) != "success"
            for need in needs
            if need in selected_set
        ):
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
    return HarnessRunResult(
        workspace=workspace,
        selected_job_ids=selected_job_ids,
        failed_job_ids=failed_job_ids,
        blocked_job_ids=blocked_job_ids,
        job_statuses=all_statuses,
    )


def _job_needs(
    job_definitions: list[workflow.WorkflowJobDefinition], job_id: str
) -> list[str]:
    """Return the normalized `needs` list for one workflow job."""

    for definition in job_definitions:
        if definition.id == job_id:
            return definition.needs
    raise KeyError(job_id)


def _normalize_job_status(raw_status: str) -> HarnessJobStatus:
    """Normalize runner-reported job states into the shared harness status vocabulary."""

    if raw_status == "success":
        return "success"
    if raw_status == "blocked":
        return "blocked"
    return "failed"


ACT_BACKEND = ActBackend()
