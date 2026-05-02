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

"""Shared runtime infrastructure for Buildish release-harness backends."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from dataclasses import dataclass
from pathlib import Path

from apache_buildish_release_tooling.harness.models import (
    GitRepositoryFixture,
    HarnessCommandTraceEntry,
    HarnessJobStatus,
    HarnessJobStatusesFile,
    HarnessScenario,
)


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
    job_statuses: dict[str, HarnessJobStatus]


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


def write_workspace_file(root: Path, relative_path: str, content: str, executable: bool) -> None:
    """Write one scenario-controlled file into the workspace."""

    destination = root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    if executable:
        destination.chmod(destination.stat().st_mode | 0o111)


def init_git_repository(root: Path, repository: GitRepositoryFixture) -> None:
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
        write_workspace_file(
            repo_dir,
            file_fixture.path,
            file_fixture.content,
            file_fixture.executable,
        )
    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "commit", "-m", repository.commit_message],
        check=True,
        capture_output=True,
        text=True,
    )


def write_shim_state(workspace: HarnessWorkspace, scenario: HarnessScenario) -> None:
    """Persist the shim behavior configuration for subprocess-facing shims."""

    state = {
        "workspace_root": str(workspace.root),
        "trace_file": str(workspace.trace_file),
        "env_capture": scenario.env_capture,
        "tool_behaviors": scenario.model_dump(mode="json")["tool_behaviors"],
        "counts": {},
    }
    workspace.state_file.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def write_bash_env_hook(workspace: HarnessWorkspace, scenario: HarnessScenario) -> None:
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


def load_job_statuses(workspace: HarnessWorkspace) -> dict[str, HarnessJobStatus]:
    """Load persisted job statuses from a workspace."""

    if not workspace.job_status_file.exists():
        return {}
    payload = HarnessJobStatusesFile.model_validate_json(
        workspace.job_status_file.read_text(encoding="utf-8")
    )
    return dict(payload.root)


def write_job_statuses(workspace: HarnessWorkspace, statuses: dict[str, HarnessJobStatus]) -> None:
    """Persist the current job statuses for rerun support."""

    payload = HarnessJobStatusesFile.model_validate(statuses)
    workspace.job_status_file.write_text(
        payload.model_dump_json(indent=2),
        encoding="utf-8",
    )


def summarize_trace(workspace: HarnessWorkspace) -> list[HarnessCommandTraceEntry]:
    """Load the JSONL command trace file of a workspace."""

    if not workspace.trace_file.exists():
        return []
    entries: list[HarnessCommandTraceEntry] = []
    for line in workspace.trace_file.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(HarnessCommandTraceEntry.model_validate_json(line))
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
