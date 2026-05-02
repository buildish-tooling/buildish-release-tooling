# Copyright 2026 The Apache Software Foundation
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

import json
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from apache_buildish_release_tooling.release.process import run_logged_command


class _ExternalGithubReadModel(BaseModel):
    """Tolerant GitHub API subset reader used by check-gate helpers."""

    model_config = ConfigDict(extra="allow")


class _CheckRunRead(_ExternalGithubReadModel):
    name: str | None = None
    status: str | None = None
    conclusion: str | None = None


class _StatusRead(_ExternalGithubReadModel):
    context: str | None = None
    state: str | None = None


class _CheckRunsPayloadRead(_ExternalGithubReadModel):
    check_runs: list[_CheckRunRead] | None = None


class _StatusesPayloadRead(_ExternalGithubReadModel):
    statuses: list[_StatusRead] | None = None


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
    payload = json.loads(stdout)
    if not isinstance(payload, dict):
        raise ValueError(f"{source} did not return a JSON object payload")
    return payload


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


def _invalid_check_runs_report(check_runs_payload: Mapping[str, object]) -> list[str]:
    reports: list[str] = []
    for check_run in _check_runs(check_runs_payload):
        status = check_run.status
        conclusion = check_run.conclusion
        if status != "completed" or conclusion not in {"success", "skipped"}:
            reports.append(
                f"{check_run.name}\tstatus={status}\tconclusion={conclusion or 'null'}"
            )
    return reports


def _invalid_statuses_report(status_payload: Mapping[str, object]) -> list[str]:
    reports: list[str] = []
    for status in _statuses(status_payload):
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
    require_at_least_one_check: bool,
) -> int:
    """Enforce the Buildish source-ref readiness policy for GitHub checks."""

    if _parsed_check_runs_payload(check_runs_payload) is None:
        raise ValueError("invalid GitHub check-runs payload")
    if _parsed_statuses_payload(statuses_payload) is None:
        raise ValueError("invalid GitHub statuses payload")
    invalid_check_runs = _invalid_check_runs_report(check_runs_payload)
    invalid_statuses = _invalid_statuses_report(statuses_payload)
    checks_total = total_count(check_runs_payload, statuses_payload)
    if require_at_least_one_check and checks_total == 0:
        raise ValueError(
            "no GitHub checks were found for the source ref, but release-branch CI is required"
        )
    if invalid_check_runs:
        invalid_report = "\n".join(invalid_check_runs)
        raise ValueError(f"invalid GitHub check runs:\n{invalid_report}")
    if invalid_statuses:
        invalid_report = "\n".join(invalid_statuses)
        raise ValueError(f"invalid GitHub status contexts:\n{invalid_report}")
    return checks_total
