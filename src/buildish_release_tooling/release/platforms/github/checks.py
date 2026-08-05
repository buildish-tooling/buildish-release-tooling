# Copyright 2026 The Buildish Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""GitHub check-gate helpers."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from urllib.parse import quote

from pydantic import Field, ValidationError

from buildish_release_tooling.release.external_json import parse_json_object
from buildish_release_tooling.release.platforms.github.models import ExternalGitHubReadModel
from buildish_release_tooling.release.process import run_logged_command


class _GitHubAppRead(ExternalGitHubReadModel):
    slug: str | None = Field(
        default=None,
        description="GitHub App slug that created a check run.",
    )


class _CheckSuiteRead(ExternalGitHubReadModel):
    id: int | None = Field(
        default=None,
        description="GitHub check-suite identifier associated with a check run.",
    )


class _CheckRunRead(ExternalGitHubReadModel):
    name: str | None = Field(
        default=None,
        description="GitHub check-run name associated with the reported CI result.",
    )
    status: str | None = Field(
        default=None,
        description="GitHub check-run status string, such as queued, in_progress, or completed.",
    )
    conclusion: str | None = Field(
        default=None,
        description="GitHub check-run conclusion string returned once the check run has completed.",
    )
    app: _GitHubAppRead | None = Field(
        default=None,
        description="GitHub App that created this check run.",
    )
    check_suite: _CheckSuiteRead | None = Field(
        default=None,
        description="Check suite containing this check run.",
    )


class _StatusRead(ExternalGitHubReadModel):
    context: str | None = Field(
        default=None,
        description="Legacy GitHub status-context name associated with the reported state.",
    )
    state: str | None = Field(
        default=None,
        description="Legacy GitHub status state, such as success, failure, error, or pending.",
    )


class _CheckRunsPayloadRead(ExternalGitHubReadModel):
    check_runs: list[_CheckRunRead] | None = Field(
        default=None,
        description="GitHub check-run entries returned for the requested commit.",
    )


class _StatusesPayloadRead(ExternalGitHubReadModel):
    statuses: list[_StatusRead] | None = Field(
        default=None,
        description="Legacy GitHub commit-status entries returned for the requested commit.",
    )


class _WorkflowRunRead(ExternalGitHubReadModel):
    check_suite_id: int | None = Field(
        default=None,
        description="Check-suite identifier associated with a workflow run.",
    )
    path: str | None = Field(
        default=None,
        description="Repository-relative workflow path and ref reported by GitHub.",
    )
    event: str | None = Field(
        default=None,
        description="GitHub event that triggered the workflow run.",
    )
    head_branch: str | None = Field(
        default=None,
        description="Head branch associated with the GitHub Actions workflow run.",
    )


class _WorkflowRunsPayloadRead(ExternalGitHubReadModel):
    workflow_runs: list[_WorkflowRunRead] | None = Field(
        default=None,
        description="GitHub Actions runs associated with the requested source commit.",
    )


def _parsed_check_runs_payload(
    payload: Mapping[str, object],
) -> _CheckRunsPayloadRead | None:
    try:
        return _CheckRunsPayloadRead.model_validate(payload)
    except ValidationError:
        return None


def _parsed_statuses_payload(
    payload: Mapping[str, object],
) -> _StatusesPayloadRead | None:
    try:
        return _StatusesPayloadRead.model_validate(payload)
    except ValidationError:
        return None


def _parsed_workflow_runs_payload(
    payload: Mapping[str, object],
) -> _WorkflowRunsPayloadRead | None:
    try:
        return _WorkflowRunsPayloadRead.model_validate(payload)
    except ValidationError:
        return None


def _check_runs(payload: Mapping[str, object]) -> list[_CheckRunRead]:
    parsed = _parsed_check_runs_payload(payload)
    return list(parsed.check_runs or []) if parsed is not None else []


def _statuses(payload: Mapping[str, object]) -> list[_StatusRead]:
    parsed = _parsed_statuses_payload(payload)
    return list(parsed.statuses or []) if parsed is not None else []


def _workflow_runs(payload: Mapping[str, object]) -> list[_WorkflowRunRead]:
    parsed = _parsed_workflow_runs_payload(payload)
    return list(parsed.workflow_runs or []) if parsed is not None else []


def _json_object_output(stdout: str, *, source: str) -> dict[str, object]:
    return parse_json_object(stdout, source=source)


def resolve_repository_slug(repo_path: Path) -> str:
    """Resolve the `owner/repo` slug for a GitHub-hosted repository."""

    completed = run_logged_command(
        ["git", "-C", str(repo_path), "config", "--get", "remote.origin.url"],
        cwd=repo_path,
        capture_output=True,
        check=False,
    )
    origin_url = completed.stdout.strip()
    if origin_url.startswith("git@github.com:"):
        return origin_url.removeprefix("git@github.com:").removesuffix(".git")
    if origin_url.startswith("https://github.com/"):
        return origin_url.removeprefix("https://github.com/").removesuffix(".git")
    raise ValueError("unable to resolve GitHub repository slug")


def fetch_check_runs_json(repository_slug: str, ref: str) -> dict[str, object]:
    """Fetch GitHub check-run data for a commit."""

    completed = run_logged_command(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github+json",
            f"repos/{repository_slug}/commits/{ref}/check-runs?per_page=100",
        ]
    )
    return _json_object_output(completed.stdout, source="GitHub check-runs API")


def fetch_statuses_json(repository_slug: str, ref: str) -> dict[str, object]:
    """Fetch legacy commit status-context data for a commit."""

    completed = run_logged_command(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github+json",
            f"repos/{repository_slug}/commits/{ref}/status",
        ]
    )
    return _json_object_output(completed.stdout, source="GitHub statuses API")


def fetch_workflow_runs_json(repository_slug: str, ref: str) -> dict[str, object]:
    """Fetch GitHub Actions workflow runs associated with one exact commit."""

    completed = run_logged_command(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github+json",
            f"repos/{repository_slug}/actions/runs?head_sha={quote(ref, safe='')}&per_page=100",
        ]
    )
    return _json_object_output(completed.stdout, source="GitHub workflow-runs API")


def _trusted_check_suite_ids(
    workflow_runs_payload: Mapping[str, object],
    *,
    trusted_workflow_path: str,
    trusted_event: str | None,
    trusted_branch: str | None,
) -> set[int]:
    if _parsed_workflow_runs_payload(workflow_runs_payload) is None:
        raise ValueError("invalid GitHub workflow-runs payload")
    trusted_ids: set[int] = set()
    for workflow_run in _workflow_runs(workflow_runs_payload):
        workflow_path = (workflow_run.path or "").partition("@")[0]
        if workflow_path != trusted_workflow_path:
            continue
        if trusted_event is not None and workflow_run.event != trusted_event:
            continue
        if trusted_branch is not None and workflow_run.head_branch != trusted_branch:
            continue
        if workflow_run.check_suite_id is not None:
            trusted_ids.add(workflow_run.check_suite_id)
    return trusted_ids


def _required_check_runs(
    check_runs_payload: Mapping[str, object],
    required_checks: set[str],
    *,
    trusted_check_suite_ids: set[int] | None,
) -> list[_CheckRunRead]:
    matching: list[_CheckRunRead] = []
    for check_run in _check_runs(check_runs_payload):
        if check_run.name not in required_checks:
            continue
        if trusted_check_suite_ids is not None:
            app_slug = check_run.app.slug if check_run.app is not None else None
            suite_id = (
                check_run.check_suite.id if check_run.check_suite is not None else None
            )
            if app_slug != "github-actions" or suite_id not in trusted_check_suite_ids:
                continue
        matching.append(check_run)
    return matching


def _required_statuses(
    status_payload: Mapping[str, object], required_checks: set[str]
) -> list[_StatusRead]:
    return [
        status for status in _statuses(status_payload) if status.context in required_checks
    ]


def _invalid_check_runs_report(check_runs: list[_CheckRunRead]) -> list[str]:
    reports: list[str] = []
    for check_run in check_runs:
        status = check_run.status
        conclusion = check_run.conclusion
        if status != "completed" or conclusion not in {"success", "skipped"}:
            reports.append(
                f"{check_run.name}\tstatus={status}\tconclusion={conclusion or 'null'}"
            )
    return reports


def _invalid_statuses_report(statuses: list[_StatusRead]) -> list[str]:
    reports: list[str] = []
    for status in statuses:
        if status.state != "success":
            reports.append(f"{status.context}\tstate={status.state}")
    return reports


def total_count(check_runs_payload: Mapping[str, object], statuses_payload: Mapping[str, object]) -> int:
    """Count check runs and legacy status contexts in two API payloads."""

    if _parsed_check_runs_payload(check_runs_payload) is None:
        raise ValueError("invalid GitHub check-runs payload")
    if _parsed_statuses_payload(statuses_payload) is None:
        raise ValueError("invalid GitHub statuses payload")
    check_run_count = len(_check_runs(check_runs_payload))
    status_count = len(_statuses(statuses_payload))
    return check_run_count + status_count


def assert_ref_ready(
    check_runs_payload: Mapping[str, object],
    statuses_payload: Mapping[str, object],
    required_checks: list[str],
    *,
    trusted_workflow_path: str | None = None,
    trusted_event: str | None = None,
    trusted_branch: str | None = None,
    workflow_runs_payload: Mapping[str, object] | None = None,
) -> int:
    """Require exact named GitHub checks while ignoring unrelated observations."""

    if _parsed_check_runs_payload(check_runs_payload) is None:
        raise ValueError("invalid GitHub check-runs payload")
    if _parsed_statuses_payload(statuses_payload) is None:
        raise ValueError("invalid GitHub statuses payload")
    trusted_suite_ids: set[int] | None = None
    if trusted_workflow_path is not None:
        if workflow_runs_payload is None:
            raise ValueError(
                "GitHub workflow-runs payload is required for trusted workflow checks"
            )
        trusted_suite_ids = _trusted_check_suite_ids(
            workflow_runs_payload,
            trusted_workflow_path=trusted_workflow_path,
            trusted_event=trusted_event,
            trusted_branch=trusted_branch,
        )
    required_names = set(required_checks)
    matching_check_runs = _required_check_runs(
        check_runs_payload,
        required_names,
        trusted_check_suite_ids=trusted_suite_ids,
    )
    matching_statuses = (
        []
        if trusted_workflow_path is not None
        else _required_statuses(statuses_payload, required_names)
    )
    observed_names = {
        item.name for item in matching_check_runs if item.name is not None
    } | {item.context for item in matching_statuses if item.context is not None}
    missing_names = sorted(required_names - observed_names)
    if missing_names:
        raise ValueError(f"required GitHub checks not found: {', '.join(missing_names)}")
    invalid_check_runs = _invalid_check_runs_report(matching_check_runs)
    invalid_statuses = _invalid_statuses_report(matching_statuses)
    if invalid_check_runs:
        invalid_report = "\n".join(invalid_check_runs)
        raise ValueError(f"invalid GitHub check runs:\n{invalid_report}")
    if invalid_statuses:
        invalid_report = "\n".join(invalid_statuses)
        raise ValueError(f"invalid GitHub status contexts:\n{invalid_report}")
    return len(observed_names)
