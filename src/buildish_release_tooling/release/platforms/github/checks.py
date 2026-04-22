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

from pydantic import Field, ValidationError

from buildish_release_tooling.release.external_json import parse_json_object
from buildish_release_tooling.release.platforms.github.models import ExternalGitHubReadModel
from buildish_release_tooling.release.process import run_logged_command


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


def _check_runs(payload: Mapping[str, object]) -> list[_CheckRunRead]:
    parsed = _parsed_check_runs_payload(payload)
    return list(parsed.check_runs or []) if parsed is not None else []


def _statuses(payload: Mapping[str, object]) -> list[_StatusRead]:
    parsed = _parsed_statuses_payload(payload)
    return list(parsed.statuses or []) if parsed is not None else []


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


def _required_check_runs(
    check_runs_payload: Mapping[str, object], required_checks: set[str]
) -> list[_CheckRunRead]:
    return [
        check_run
        for check_run in _check_runs(check_runs_payload)
        if check_run.name in required_checks
    ]


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
) -> int:
    """Require exact named GitHub checks while ignoring unrelated observations."""

    if _parsed_check_runs_payload(check_runs_payload) is None:
        raise ValueError("invalid GitHub check-runs payload")
    if _parsed_statuses_payload(statuses_payload) is None:
        raise ValueError("invalid GitHub statuses payload")
    required_names = set(required_checks)
    matching_check_runs = _required_check_runs(check_runs_payload, required_names)
    matching_statuses = _required_statuses(statuses_payload, required_names)
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
