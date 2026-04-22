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
from pathlib import Path

from apache_buildish_release_tooling.process import run_logged_command


def _check_runs(payload: dict[str, object]) -> list[dict[str, object]]:
    raw_check_runs = payload.get("check_runs")
    if not isinstance(raw_check_runs, list):
        return []
    return [check_run for check_run in raw_check_runs if isinstance(check_run, dict)]


def _statuses(payload: dict[str, object]) -> list[dict[str, object]]:
    raw_statuses = payload.get("statuses")
    if not isinstance(raw_statuses, list):
        return []
    return [status for status in raw_statuses if isinstance(status, dict)]


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
    return json.loads(completed.stdout)


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
    return json.loads(completed.stdout)


def _invalid_check_runs_report(check_runs_payload: dict[str, object]) -> list[str]:
    reports: list[str] = []
    for check_run in _check_runs(check_runs_payload):
        status = check_run.get("status")
        conclusion = check_run.get("conclusion")
        if status != "completed" or conclusion not in {"success", "skipped"}:
            reports.append(
                f"{check_run.get('name')}\tstatus={status}\tconclusion={conclusion or 'null'}"
            )
    return reports


def _invalid_statuses_report(status_payload: dict[str, object]) -> list[str]:
    reports: list[str] = []
    for status in _statuses(status_payload):
        if status.get("state") != "success":
            reports.append(f"{status.get('context')}\tstate={status.get('state')}")
    return reports


def total_count(check_runs_payload: dict[str, object], statuses_payload: dict[str, object]) -> int:
    """Count check runs and legacy status contexts in two API payloads."""

    check_run_count = len(_check_runs(check_runs_payload))
    status_count = len(_statuses(statuses_payload))
    return check_run_count + status_count


def assert_ref_ready(
    check_runs_payload: dict[str, object],
    statuses_payload: dict[str, object],
    require_at_least_one_check: bool,
) -> int:
    """Enforce the Buildish source-ref readiness policy for GitHub checks."""

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
