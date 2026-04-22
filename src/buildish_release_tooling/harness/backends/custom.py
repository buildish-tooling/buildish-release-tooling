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

"""Custom execution backend for the Buildish release harness."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from buildish_release_tooling.harness.backends.base import Backend
from buildish_release_tooling.harness.job_selection import rerunnable_job_ids
from buildish_release_tooling.harness.models import HarnessScenario, JobScenario, validate_harness_identifier
from buildish_release_tooling.harness.process import (
    LONG_HARNESS_COMMAND_TIMEOUT_SECONDS,
    harness_command_timeout_seconds,
    run_harness_command,
)
from buildish_release_tooling.harness.runtime import (
    HarnessRunResult,
    HarnessWorkspace,
    create_workspace,
    load_existing_workspace,
    init_git_repository,
    repo_root,
    write_bash_env_hook,
    write_job_statuses,
    write_job_summaries,
    write_shim_state,
    write_workspace_file,
    load_job_statuses,
)
from buildish_release_tooling.harness.uv_shim import render_uv_shim_script, uv_shim_config


class CustomBackend(Backend):
    """Shell-script execution backend for synthetic harness scenarios."""

    name = "custom"

    def run_scenario(
        self,
        scenario: HarnessScenario,
        *,
        workspace_root: Path | None = None,
        seed_from: Path | None = None,
    ) -> HarnessRunResult:
        """Create a new workspace, initialize the scenario, and execute all jobs once."""

        if seed_from is not None:
            raise ValueError("custom harness backend does not support --seed-from")
        workspace = create_workspace(workspace_root)
        _bootstrap_workspace(workspace, scenario)
        selected_job_ids = [job.id for job in _topological_jobs(scenario)]
        result = _run_jobs(scenario, workspace, selected_job_ids)
        write_job_summaries(
            workspace,
            {job.id: [step.id for step in job.steps] for job in scenario.jobs},
        )
        return result

    def rerun_failed_jobs(self, scenario: HarnessScenario, workspace_root: Path) -> HarnessRunResult:
        """Rerun the failed jobs and their downstream dependents in an existing workspace."""

        workspace = load_existing_workspace(workspace_root)
        persisted_statuses = load_job_statuses(workspace)
        selected_job_ids = rerunnable_job_ids(
            [job.id for job in _topological_jobs(scenario)],
            {job.id: job.needs for job in scenario.jobs},
            persisted_statuses,
        )
        result = _run_jobs(scenario, workspace, selected_job_ids)
        write_job_summaries(
            workspace,
            {job.id: [step.id for step in job.steps] for job in scenario.jobs},
        )
        return result


def _bootstrap_workspace(workspace: HarnessWorkspace, scenario: HarnessScenario) -> None:
    """Materialize the initial workspace state and shim configuration."""

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
    _write_tool_shims(workspace, scenario)
    workspace.job_status_file.write_text("{}", encoding="utf-8")
    workspace.trace_file.write_text("", encoding="utf-8")


def _write_tool_shims(workspace: HarnessWorkspace, scenario: HarnessScenario) -> None:
    """Write executable shims for all intercepted tools."""

    tools = sorted(set(scenario.tool_behaviors) | {"docker", "gh", "gpg", "java", "javac", "uv"})
    for tool in tools:
        validate_harness_identifier(tool, field_name="tool behavior name")
        script_path = workspace.shims_dir / tool
        if tool == "uv":
            script_path.write_text(
                render_uv_shim_script(
                    uv_shim_config(shim_python_executable=sys.executable)
                ),
                encoding="utf-8",
            )
        else:
            script_path.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "set -euo pipefail",
                        (
                            f"exec {json.dumps(sys.executable)} -m "
                            "buildish_release_tooling.harness.shim_entrypoint "
                            f"{json.dumps(tool)} \"$@\""
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
        script_path.chmod(script_path.stat().st_mode | 0o111)


def _topological_jobs(
    scenario: HarnessScenario,
    selected_job_ids: set[str] | None = None,
) -> list[JobScenario]:
    """Return jobs in dependency order while preserving declaration order where possible."""

    selected = selected_job_ids if selected_job_ids is not None else {job.id for job in scenario.jobs}
    jobs_by_id = {job.id: job for job in scenario.jobs}
    pending = dict.fromkeys(selected)
    resolved: list[JobScenario] = []
    progress_made = True
    while pending and progress_made:
        progress_made = False
        for job in scenario.jobs:
            if job.id not in pending:
                continue
            relevant_needs = [need for need in job.needs if need in selected]
            if all(need in {resolved_job.id for resolved_job in resolved} for need in relevant_needs):
                resolved.append(jobs_by_id[job.id])
                del pending[job.id]
                progress_made = True
        if not progress_made and pending:
            unresolved = ", ".join(sorted(pending))
            raise RuntimeError(f"cyclic or unresolved job dependencies: {unresolved}")
    return resolved


def _run_jobs(
    scenario: HarnessScenario,
    workspace: HarnessWorkspace,
    selected_job_ids: list[str],
) -> HarnessRunResult:
    """Execute the selected jobs inside an initialized workspace."""

    selected_set = set(selected_job_ids)
    ordered_jobs = _topological_jobs(scenario, selected_set)
    persisted_statuses = load_job_statuses(workspace)
    current_statuses = dict(persisted_statuses)
    failed_job_ids: list[str] = []
    blocked_job_ids: list[str] = []
    for job in ordered_jobs:
        if any(current_statuses.get(need) != "success" for need in job.needs):
            current_statuses[job.id] = "blocked"
            blocked_job_ids.append(job.id)
            continue
        job_exit_code = _run_job(scenario, workspace, job)
        current_statuses[job.id] = "success" if job_exit_code == 0 else "failed"
        if job_exit_code != 0:
            failed_job_ids.append(job.id)
    write_job_statuses(workspace, current_statuses)
    return HarnessRunResult(
        workspace=workspace,
        selected_job_ids=selected_job_ids,
        failed_job_ids=failed_job_ids,
        blocked_job_ids=blocked_job_ids,
        job_statuses=current_statuses,
    )


def _run_job(scenario: HarnessScenario, workspace: HarnessWorkspace, job: JobScenario) -> int:
    """Run all steps in one job until one fails or all succeed."""

    for step in job.steps:
        exit_code = _run_step(
            scenario,
            workspace,
            job,
            step.id,
            step.run,
            step.cwd,
            {**job.env, **step.env},
            step.shell,
        )
        if exit_code != 0:
            return exit_code
    return 0


def _run_step(
    scenario: HarnessScenario,
    workspace: HarnessWorkspace,
    job: JobScenario,
    step_id: str,
    script_body: str,
    cwd: str | None,
    env: dict[str, str],
    shell: str,
) -> int:
    """Execute one shell step using the harness shims and summary capture wiring."""

    script_path = workspace.scripts_dir / f"{job.id}__{step_id}.sh"
    script_path.write_text(script_body, encoding="utf-8")
    script_path.chmod(script_path.stat().st_mode | 0o111)
    summary_path = workspace.summaries_dir / f"{job.id}__{step_id}.md"
    summary_path.write_text("", encoding="utf-8")
    step_env = dict(os.environ)
    step_env.update(scenario.env)
    step_env.update(scenario.secrets)
    step_env.update(job.env)
    step_env.update(env)
    step_env["PATH"] = f"{workspace.shims_dir}:{os.environ.get('PATH', '')}"
    step_env["PYTHONPATH"] = _pythonpath_for_subprocess()
    step_env["BUILDISH_HARNESS_STATE_FILE"] = str(workspace.state_file)
    step_env["BUILDISH_HARNESS_REAL_PATH"] = os.environ.get("PATH", "")
    step_env["GITHUB_STEP_SUMMARY"] = str(summary_path)
    if shell == "bash":
        step_env["BASH_ENV"] = str(workspace.bash_env_file)
        command = ["bash", "-e", "-u", "-o", "pipefail", str(script_path)]
    else:
        command = [shell, str(script_path)]
    completed = run_harness_command(
        command,
        cwd=str(workspace.root / cwd) if cwd is not None else str(workspace.root),
        env=step_env,
        text=True,
        capture_output=True,
        check=False,
        timeout=harness_command_timeout_seconds(LONG_HARNESS_COMMAND_TIMEOUT_SECONDS),
    )
    if completed.stdout:
        with (workspace.harness_dir / "step-stdout.log").open("a", encoding="utf-8") as handle:
            handle.write(completed.stdout)
    if completed.stderr:
        with (workspace.harness_dir / "step-stderr.log").open("a", encoding="utf-8") as handle:
            handle.write(completed.stderr)
    return completed.returncode


def _pythonpath_for_subprocess() -> str:
    """Return a `PYTHONPATH` value that keeps the local source tree importable."""

    src_dir = repo_root() / "src"
    existing = os.environ.get("PYTHONPATH")
    if existing:
        return f"{src_dir}:{existing}"
    return str(src_dir)


CUSTOM_BACKEND = CustomBackend()
