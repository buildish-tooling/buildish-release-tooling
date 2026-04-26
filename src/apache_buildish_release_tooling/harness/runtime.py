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

"""Custom execution backend for the Buildish release harness."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apache_buildish_release_tooling.harness.models import GitRepositoryFixture, HarnessScenario, JobScenario


@dataclass(frozen=True)
class HarnessWorkspace:
    """Filesystem layout for a single harness workspace."""

    root: Path
    harness_dir: Path
    scripts_dir: Path
    summaries_dir: Path
    job_summaries_dir: Path
    job_statuses_dir: Path
    actions_dir: Path
    repo_sources_dir: Path
    git_origins_dir: Path
    git_checkouts_dir: Path
    svn_dir: Path
    svn_repository_dir: Path
    svn_working_copy_dir: Path
    state_file: Path
    job_status_file: Path
    trace_file: Path
    shims_dir: Path
    bash_env_file: Path

    def inspectable_paths(self) -> dict[str, str]:
        """Return stable inspectable workspace paths for CLI output and JSON results."""

        return {
            "workspace_root": str(self.root),
            "primary_git_checkout": str(self.root),
            "rewritten_workflows": str(self.root / ".github" / "workflows"),
            "harness_root": str(self.harness_dir),
            "generated_actions": str(self.actions_dir),
            "repo_sources": str(self.repo_sources_dir),
            "git_origins": str(self.git_origins_dir),
            "self_git_origin": str(self.git_origins_dir / "self"),
            "git_checkouts": str(self.git_checkouts_dir),
            "svn_root": str(self.svn_dir),
            "svn_repository": str(self.svn_repository_dir),
            "svn_working_copy": str(self.svn_working_copy_dir),
            "step_summaries": str(self.summaries_dir),
            "job_summaries": str(self.job_summaries_dir),
            "job_statuses": str(self.job_statuses_dir),
            "command_trace": str(self.trace_file),
        }


@dataclass(frozen=True)
class HarnessRunResult:
    """Outcome of one harness run or rerun."""

    workspace: HarnessWorkspace
    selected_job_ids: list[str]
    failed_job_ids: list[str]
    blocked_job_ids: list[str]
    job_statuses: dict[str, str]


def repo_root() -> Path:
    """Return the root directory of the buildish-release-tooling repository."""

    return Path(__file__).resolve().parents[3]


def default_workspace_root() -> Path:
    """Return the default directory for disposable harness workspaces."""

    root = repo_root() / "build" / "harness"
    root.mkdir(parents=True, exist_ok=True)
    return root


def create_workspace_root(root_dir: Path | None = None) -> Path:
    """Create one sortable disposable workspace directory under the configured harness root."""

    base_dir = root_dir if root_dir is not None else default_workspace_root()
    base_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=UTC).astimezone().strftime("%Y-%m-%d-%H-%M-%S")
    return Path(tempfile.mkdtemp(prefix=f"scenario.{timestamp}.", dir=base_dir))


def create_workspace(root_dir: Path | None = None) -> HarnessWorkspace:
    """Create a fresh workspace for a harness scenario."""

    workspace_root = create_workspace_root(root_dir)
    workspace = workspace_paths(workspace_root)
    ensure_workspace_directories(workspace)
    return workspace


def load_existing_workspace(workspace_root: Path) -> HarnessWorkspace:
    """Reconstruct a workspace descriptor for a previously initialized workspace."""

    return workspace_paths(workspace_root)


def workspace_paths(workspace_root: Path) -> HarnessWorkspace:
    """Derive the standard harness workspace layout from one workspace root."""

    harness_dir = workspace_root / ".buildish-release-harness"
    svn_dir = harness_dir / "svn"
    return HarnessWorkspace(
        root=workspace_root,
        harness_dir=harness_dir,
        scripts_dir=harness_dir / "scripts",
        summaries_dir=harness_dir / "summaries",
        job_summaries_dir=harness_dir / "job-summaries",
        job_statuses_dir=harness_dir / "job-statuses",
        actions_dir=harness_dir / "actions",
        repo_sources_dir=harness_dir / "repo-sources",
        git_origins_dir=harness_dir / "git-origins",
        git_checkouts_dir=harness_dir / "git-checkouts",
        svn_dir=svn_dir,
        svn_repository_dir=svn_dir / "repository",
        svn_working_copy_dir=svn_dir / "working-copy",
        state_file=harness_dir / "shim-state.json",
        job_status_file=harness_dir / "job-statuses.json",
        trace_file=harness_dir / "command-trace.jsonl",
        shims_dir=harness_dir / "shims",
        bash_env_file=harness_dir / "bash-env.sh",
    )


def ensure_workspace_directories(workspace: HarnessWorkspace) -> None:
    """Create the standard directory layout for one harness workspace."""

    for directory in (
        workspace.harness_dir,
        workspace.scripts_dir,
        workspace.summaries_dir,
        workspace.job_summaries_dir,
        workspace.job_statuses_dir,
        workspace.actions_dir,
        workspace.repo_sources_dir,
        workspace.git_origins_dir,
        workspace.git_checkouts_dir,
        workspace.svn_dir,
        workspace.shims_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def run_scenario(
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


def rerun_failed_jobs(scenario: HarnessScenario, workspace_root: Path) -> HarnessRunResult:
    """Rerun the failed jobs and their downstream dependents in an existing workspace."""

    workspace = load_existing_workspace(workspace_root)
    persisted_statuses = _load_job_statuses(workspace)
    selected_job_ids = _rerunnable_job_ids(scenario, persisted_statuses)
    result = _run_jobs(scenario, workspace, selected_job_ids)
    write_job_summaries(
        workspace,
        {job.id: [step.id for step in job.steps] for job in scenario.jobs},
    )
    return result


def _bootstrap_workspace(workspace: HarnessWorkspace, scenario: HarnessScenario) -> None:
    """Materialize the initial workspace state and shim configuration."""

    for file_fixture in scenario.workspace_files:
        _write_workspace_file(workspace.root, file_fixture.path, file_fixture.content, file_fixture.executable)
    for repository in scenario.git_repositories:
        _init_git_repository(workspace.root, repository)
    _write_shim_state(workspace, scenario)
    _write_bash_env_hook(workspace, scenario)
    _write_tool_shims(workspace, scenario)
    workspace.job_status_file.write_text("{}", encoding="utf-8")
    workspace.trace_file.write_text("", encoding="utf-8")


def _write_workspace_file(root: Path, relative_path: str, content: str, executable: bool) -> None:
    """Write one scenario-controlled file into the workspace."""

    destination = root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    if executable:
        destination.chmod(destination.stat().st_mode | 0o111)


def _init_git_repository(root: Path, repository: GitRepositoryFixture) -> None:
    """Initialize one disposable Git repository fixture and create an initial commit."""

    repo_dir = root / repository.path
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", f"--initial-branch={repository.default_branch}", str(repo_dir)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.name", "Buildish Harness"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.email", "buildish-harness@example.invalid"],
        check=True,
        capture_output=True,
        text=True,
    )
    for file_fixture in repository.files:
        _write_workspace_file(repo_dir, file_fixture.path, file_fixture.content, file_fixture.executable)
    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "commit", "-m", repository.commit_message],
        check=True,
        capture_output=True,
        text=True,
    )


def _write_shim_state(workspace: HarnessWorkspace, scenario: HarnessScenario) -> None:
    """Persist the shim behavior configuration for subprocess-facing shims."""

    state = {
        "workspace_root": str(workspace.root),
        "trace_file": str(workspace.trace_file),
        "env_capture": scenario.env_capture,
        "tool_behaviors": scenario.model_dump(mode="json")["tool_behaviors"],
        "counts": {},
    }
    workspace.state_file.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _write_bash_env_hook(workspace: HarnessWorkspace, scenario: HarnessScenario) -> None:
    """Write a `BASH_ENV` hook file that defines function shims for intercepted tools."""

    tools = sorted(set(scenario.tool_behaviors) | {"gh", "docker", "gpg", "java", "javac"})
    lines = [
        "#!/usr/bin/env bash",
        "# Generated by buildish-release-harness.",
        "",
    ]
    for tool in tools:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", tool):
            continue
        lines.extend(
            [
                f"{tool}() {{",
                '  BUILDISH_HARNESS_CALL_SITE="${BASH_SOURCE[1]}:${BASH_LINENO[0]}" command '
                f'{tool} "$@"',
                "}",
                "",
            ]
        )
    workspace.bash_env_file.write_text("\n".join(lines), encoding="utf-8")
    workspace.bash_env_file.chmod(workspace.bash_env_file.stat().st_mode | 0o111)


def _write_tool_shims(workspace: HarnessWorkspace, scenario: HarnessScenario) -> None:
    """Write executable shims for all intercepted tools."""

    tools = sorted(set(scenario.tool_behaviors) | {"docker", "gh", "gpg", "java", "javac", "uv"})
    for tool in tools:
        script_path = workspace.shims_dir / tool
        if tool == "uv":
            script_path.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "set -euo pipefail",
                        'if [[ "${1:-}" == "python" && "${2:-}" == "install" ]]; then',
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
                        f'      exec {json.dumps(sys.executable)} -m apache_buildish_release_tooling.harness.shim_entrypoint buildish-release-tooling "${{filtered_args[@]}}"',
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
                + "\n",
                encoding="utf-8",
            )
        else:
            script_path.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "set -euo pipefail",
                        f"exec {json.dumps(sys.executable)} -m "
                        "apache_buildish_release_tooling.harness.shim_entrypoint "
                        f"{json.dumps(tool)} \"$@\"",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
        script_path.chmod(script_path.stat().st_mode | 0o111)


def _topological_jobs(scenario: HarnessScenario, selected_job_ids: set[str] | None = None) -> list[JobScenario]:
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
    persisted_statuses = _load_job_statuses(workspace)
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
    _write_job_statuses(workspace, current_statuses)
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
        exit_code = _run_step(scenario, workspace, job, step.id, step.run, step.cwd, {**job.env, **step.env}, step.shell)
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
    completed = subprocess.run(  # noqa: S603
        command,
        cwd=str(workspace.root / cwd) if cwd is not None else str(workspace.root),
        env=step_env,
        text=True,
        capture_output=True,
        check=False,
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


def _load_job_statuses(workspace: HarnessWorkspace) -> dict[str, str]:
    """Load persisted job statuses from a workspace."""

    if not workspace.job_status_file.exists():
        return {}
    return json.loads(workspace.job_status_file.read_text(encoding="utf-8"))


def _write_job_statuses(workspace: HarnessWorkspace, statuses: dict[str, str]) -> None:
    """Persist the current job statuses for rerun support."""

    workspace.job_status_file.write_text(json.dumps(statuses, indent=2, sort_keys=True), encoding="utf-8")


def _rerunnable_job_ids(scenario: HarnessScenario, statuses: dict[str, str]) -> list[str]:
    """Return failed jobs and all of their downstream dependents."""

    failed_or_blocked = {job_id for job_id, status in statuses.items() if status in {"failed", "blocked"}}
    if not failed_or_blocked:
        return []
    dependents: dict[str, set[str]] = {job.id: set() for job in scenario.jobs}
    for job in scenario.jobs:
        for need in job.needs:
            dependents.setdefault(need, set()).add(job.id)
    selected = set(failed_or_blocked)
    stack = list(failed_or_blocked)
    while stack:
        current = stack.pop()
        for dependent in dependents.get(current, set()):
            if dependent not in selected:
                selected.add(dependent)
                stack.append(dependent)
    return [job.id for job in _topological_jobs(scenario, selected)]


def summarize_trace(workspace: HarnessWorkspace) -> list[dict[str, Any]]:
    """Load the JSONL command trace file of a workspace."""

    if not workspace.trace_file.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in workspace.trace_file.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def write_job_summaries(
    workspace: HarnessWorkspace,
    step_order_by_job: dict[str, list[str]],
) -> None:
    """Concatenate step summaries into one GitHub-like summary file per job."""

    workspace.job_summaries_dir.mkdir(parents=True, exist_ok=True)
    for job_id, step_ids in step_order_by_job.items():
        rendered_parts: list[str] = []
        for step_id in step_ids:
            summary_path = workspace.summaries_dir / f"{job_id}__{step_id}.md"
            if not summary_path.exists():
                continue
            content = summary_path.read_text(encoding="utf-8").strip()
            if not content:
                continue
            rendered_parts.append(content)
        rendered_summary = "\n\n".join(rendered_parts)
        if rendered_summary:
            rendered_summary += "\n"
        (workspace.job_summaries_dir / f"{job_id}.md").write_text(
            rendered_summary,
            encoding="utf-8",
        )


def remove_workspace(workspace_root: Path) -> None:
    """Delete a disposable harness workspace."""

    shutil.rmtree(workspace_root, ignore_errors=True)
