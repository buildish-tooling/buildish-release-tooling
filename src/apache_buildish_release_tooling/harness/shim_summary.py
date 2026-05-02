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

"""Summary rendering helpers for the harness shim entrypoint."""

from __future__ import annotations

import os
from pathlib import Path

from apache_buildish_release_tooling.harness.models import ToolBehaviorResult


def summary_text(tool_name: str, result: ToolBehaviorResult, stdout: str, *, command_argv: list[str]) -> str:
    """Return the summary fragment that should be appended for one shim invocation."""

    parts: list[str] = []
    explicit_summary = result.summary
    if explicit_summary:
        parts.append(explicit_summary)
    append_stdout = result.append_stdout_to_summary
    if tool_name == "buildish-release-tooling" and not explicit_summary:
        parts.append(
            _buildish_release_tooling_summary(
                command_argv=command_argv,
                stdout=stdout,
                stderr=result.stderr,
                exit_code=result.exit_code,
            )
        )
    elif append_stdout:
        parts.append(stdout)
    return "".join(parts)


def append_step_summary(content: str) -> None:
    """Append one summary fragment to the current step summary file when configured."""

    if not content:
        return
    destinations = _summary_destinations()
    if not destinations:
        return
    for destination in destinations:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("a", encoding="utf-8") as handle:
            handle.write(content)


def _buildish_release_tooling_summary(
    *,
    command_argv: list[str],
    stdout: str,
    stderr: str,
    exit_code: int,
) -> str:
    """Render a human-facing Markdown summary for one mocked release-tooling invocation."""

    command_name = command_argv[0] if command_argv else "buildish-release-tooling"
    heading = _buildish_release_tooling_heading(command_name, command_argv[1:])
    rows = [
        ("Command", f"`{command_name}`"),
        (
            "Arguments",
            " ".join(f"`{argument}`" for argument in command_argv[1:]) if command_argv[1:] else "<none>",
        ),
        ("Exit code", str(exit_code)),
    ]
    parts = [
        f"## {heading}\n\n",
        "### Technical details\n\n",
        "| Field | Value |\n",
        "| --- | --- |\n",
    ]
    for field, value in rows:
        parts.append(f"| {field} | {value} |\n")
    parts.append("\n")
    if stdout:
        parts.append(f"### Outcome\n\n```text\n{stdout}\n```\n\n")
    else:
        parts.append("### Outcome\n\n```text\nCompleted successfully.\n```\n\n")
    if exit_code != 0 or stderr:
        parts.append(
            f"### Error details\n\n```text\n{stderr or 'Command returned a non-zero exit code.'}\n```\n\n"
        )
    return "".join(parts)


def _buildish_release_tooling_heading(command_name: str, arguments: list[str]) -> str:
    """Return a user-facing heading for one mocked release-tooling command."""

    version = _first_version_argument(arguments)
    if command_name == "cleanup-dev-svn-rcs" and version is not None:
        return f"Cleanup ASF SVN dev/dist for version {version}"
    if command_name == "verify-source-ref-checks" and version is not None:
        return f"Verify GitHub checks for source ref {version}"
    if command_name == "materialize-rc-git-content" and version is not None:
        return f"Materialize RC Git content for version {version}"
    if command_name == "finalize-rc-vote-materials" and version is not None:
        return f"Finalize RC vote materials for version {version}"
    if command_name == "publish-source-release-svn" and version is not None:
        return f"Publish source release to ASF SVN for version {version}"
    if command_name == "prune-older-line-releases" and version is not None:
        return f"Prune older same-line releases for version {version}"
    if command_name == "create-final-tag" and version is not None:
        return f"Create final tag for version {version}"
    if command_name == "create-rc-materialization-tag" and version is not None:
        return f"Create RC materialization tag for version {version}"
    if command_name == "sync-draft-github-release" and version is not None:
        return f"Synchronize draft GitHub Release for version {version}"
    if command_name == "release-version" and version is not None:
        return f"Resolve release-version state for {version}"
    if command_name == "verify-rc":
        return "Verify RC"
    if command_name == "create-release-branch":
        return "Create release branch"
    return command_name.replace("-", " ").capitalize()


def _first_version_argument(arguments: list[str]) -> str | None:
    """Return the first simple semantic-version argument from one argv tail."""

    for argument in arguments:
        if argument.startswith("-"):
            continue
        if argument.count(".") == 2 and all(piece.isdigit() for piece in argument.split(".")):
            return argument
    return None


def _summary_destinations() -> list[Path]:
    """Return the summary files that should receive the current step's summary content."""

    destinations: list[Path] = []
    summaries_dir = os.environ.get("BUILDISH_HARNESS_SUMMARIES_DIR")
    job_id = os.environ.get("BUILDISH_HARNESS_JOB_ID")
    step_id = os.environ.get("BUILDISH_HARNESS_STEP_ID")
    if summaries_dir and job_id and step_id:
        destinations.append(Path(summaries_dir) / f"{job_id}__{step_id}.md")
    if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
        summary_destination = Path(summary_path)
        if summary_destination not in destinations:
            destinations.append(summary_destination)
    return destinations
