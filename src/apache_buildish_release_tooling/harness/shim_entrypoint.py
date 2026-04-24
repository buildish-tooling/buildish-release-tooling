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

"""Generic command shim entrypoint for the Buildish release harness."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def main() -> None:
    """Dispatch one intercepted tool invocation according to the persisted scenario state."""

    if len(sys.argv) < 2:
        raise SystemExit("usage: shim_entrypoint.py <tool-name> [args...]")
    tool_name = sys.argv[1]
    argv = sys.argv[2:]
    state_path = Path(os.environ["BUILDISH_HARNESS_STATE_FILE"])
    state = json.loads(state_path.read_text(encoding="utf-8"))
    behavior_index, result = _resolve_behavior(state, tool_name, argv)
    stdin_text = sys.stdin.read() if tool_name == "gh" else ""
    if result is None:
        builtin_result = _handle_builtin_tool(tool_name, argv, stdin_text, state)
        if builtin_result is not None:
            state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
            _record_invocation(
                state=state,
                tool_name=tool_name,
                argv=argv,
                exit_code=int(builtin_result.get("exit_code", 0)),
                stdout=str(builtin_result.get("stdout", "")),
                stderr=str(builtin_result.get("stderr", "")),
                delegated=False,
            )
            if builtin_stdout := str(builtin_result.get("stdout", "")):
                sys.stdout.write(builtin_stdout)
            if builtin_stderr := str(builtin_result.get("stderr", "")):
                sys.stderr.write(builtin_stderr)
            raise SystemExit(int(builtin_result.get("exit_code", 0)))
        stderr = f"buildish-release-harness: no scripted behavior for {tool_name} {' '.join(argv)}\n"
        _record_invocation(
            state=state,
            tool_name=tool_name,
            argv=argv,
            exit_code=127,
            stdout="",
            stderr=stderr,
            delegated=False,
        )
        sys.stderr.write(stderr)
        raise SystemExit(127)
    _increment_behavior_count(state, tool_name, behavior_index)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    if result.get("delegate_to_real_tool", False):
        completed = _delegate_to_real_tool(tool_name, argv)
        _append_step_summary(_summary_text(tool_name, result, completed.stdout))
        _record_invocation(
            state=state,
            tool_name=tool_name,
            argv=argv,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            delegated=True,
        )
        if completed.stdout:
            sys.stdout.write(completed.stdout)
        if completed.stderr:
            sys.stderr.write(completed.stderr)
        raise SystemExit(completed.returncode)
    _perform_file_writes(state, result.get("writes", []))
    stdout = str(result.get("stdout", ""))
    stderr = str(result.get("stderr", ""))
    exit_code = int(result.get("exit_code", 0))
    _append_step_summary(_summary_text(tool_name, result, stdout))
    _record_invocation(
        state=state,
        tool_name=tool_name,
        argv=argv,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        delegated=False,
    )
    if stdout:
        sys.stdout.write(stdout)
    if stderr:
        sys.stderr.write(stderr)
    raise SystemExit(exit_code)


def _summary_text(tool_name: str, result: dict[str, Any], stdout: str) -> str:
    """Return the summary fragment that should be appended for one shim invocation."""

    parts: list[str] = []
    explicit_summary = str(result.get("summary", ""))
    if explicit_summary:
        parts.append(explicit_summary)
    append_stdout = bool(result.get("append_stdout_to_summary", False))
    if tool_name == "buildish-release-tooling" and not explicit_summary:
        parts.append(
            _buildish_release_tooling_summary(
                command_argv=sys.argv[2:],
                stdout=stdout,
                stderr=str(result.get("stderr", "")),
                exit_code=int(result.get("exit_code", 0)),
            )
        )
    elif append_stdout:
        parts.append(stdout)
    return "".join(parts)


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
        parts.append(f"### Error details\n\n```text\n{stderr or 'Command returned a non-zero exit code.'}\n```\n\n")
    return "".join(parts)


def _buildish_release_tooling_heading(command_name: str, arguments: list[str]) -> str:
    """Return a user-facing heading for one mocked release-tooling command."""

    version = _first_version_argument(arguments)
    if command_name == "cleanup-dev-svn-rcs" and version is not None:
        return f"Cleanup ASF SVN dev/dist for version {version}"
    if command_name == "verify-source-ref-checks" and version is not None:
        return f"Verify GitHub checks for source ref {version}"
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
    if command_name == "verify-rc" and version is not None:
        return f"Emit RC verification guidance for version {version}"
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


def _append_step_summary(content: str) -> None:
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


def _resolve_behavior(state: dict[str, Any], tool_name: str, argv: list[str]) -> tuple[int, dict[str, Any] | None]:
    """Return the first matching scripted behavior that still has remaining uses."""

    behaviors = list(state.get("tool_behaviors", {}).get(tool_name, []))
    counts: dict[str, int] = state.setdefault("counts", {})
    cwd = str(Path.cwd())
    env = os.environ
    for index, behavior in enumerate(behaviors):
        key = _count_key(tool_name, index)
        times = behavior.get("times")
        if times is not None and counts.get(key, 0) >= int(times):
            continue
        if _matches(behavior.get("match", {}), argv, cwd, env, str(state["workspace_root"])):
            return index, dict(behavior.get("result", {}))
    return -1, None


def _matches(
    match: dict[str, Any],
    argv: list[str],
    cwd: str,
    env: Mapping[str, str],
    workspace_root: str,
) -> bool:
    """Return whether the configured matcher accepts the current invocation."""

    expected_argv = match.get("argv")
    if expected_argv is not None and list(expected_argv) != argv:
        return False
    expected_prefix = match.get("argv_prefix")
    if expected_prefix is not None and argv[: len(expected_prefix)] != list(expected_prefix):
        return False
    expected_contains = list(match.get("argv_contains", []))
    for fragment in expected_contains:
        if not any(fragment in argument for argument in argv):
            return False
    expected_cwd = match.get("cwd")
    if expected_cwd is not None:
        expected_path = Path(workspace_root) / str(expected_cwd)
        if Path(cwd) != expected_path:
            return False
    expected_env = dict(match.get("env_contains", {}))
    for key, expected_value in expected_env.items():
        if env.get(key) != expected_value:
            return False
    return True


def _increment_behavior_count(state: dict[str, Any], tool_name: str, behavior_index: int) -> None:
    """Increment the persisted call count for one scripted behavior."""

    counts: dict[str, int] = state.setdefault("counts", {})
    key = _count_key(tool_name, behavior_index)
    counts[key] = counts.get(key, 0) + 1


def _handle_builtin_tool(
    tool_name: str,
    argv: list[str],
    stdin_text: str,
    state: dict[str, Any],
) -> dict[str, Any] | None:
    """Handle built-in shim side effects for tools that need local mutable-state emulation."""

    if tool_name == "gh":
        return _handle_builtin_gh(argv, stdin_text, state)
    return None


def _handle_builtin_gh(
    argv: list[str],
    stdin_text: str,
    state: dict[str, Any],
) -> dict[str, Any] | None:
    """Handle the small GitHub CLI subset that must mutate local Git state in harness runs."""

    parsed = _parse_gh_api_request(argv)
    if parsed is None:
        return None
    method, endpoint = parsed
    if method == "POST" and endpoint.endswith("/git/tags"):
        payload = json.loads(stdin_text or "{}")
        fake_sha = _store_builtin_gh_tag_object(state, payload)
        return {"stdout": json.dumps({"sha": fake_sha})}
    if method == "POST" and endpoint.endswith("/git/refs"):
        payload = json.loads(stdin_text or "{}")
        _apply_builtin_gh_tag_ref(state, endpoint, payload, force=False)
        return {"stdout": json.dumps({"ref": payload.get("ref", "")})}
    if method == "PATCH" and "/git/refs/tags/" in endpoint:
        payload = json.loads(stdin_text or "{}")
        _apply_builtin_gh_tag_ref(state, endpoint, payload, force=True)
        return {"stdout": json.dumps({"ref": f"refs/tags/{endpoint.rsplit('/', 1)[-1]}"})}
    return None


def _parse_gh_api_request(argv: list[str]) -> tuple[str, str] | None:
    """Parse a subset of `gh api` arguments into `(method, endpoint)`."""

    if not argv or argv[0] != "api":
        return None
    method = "GET"
    endpoint = ""
    index = 1
    while index < len(argv):
        argument = argv[index]
        if argument == "-X" and index + 1 < len(argv):
            method = argv[index + 1]
            index += 2
            continue
        if argument == "-H" and index + 1 < len(argv):
            index += 2
            continue
        if argument == "--input" and index + 1 < len(argv):
            index += 2
            continue
        if argument.startswith("repos/"):
            endpoint = argument
        index += 1
    if not endpoint:
        return None
    return method, endpoint


def _store_builtin_gh_tag_object(state: dict[str, Any], payload: dict[str, Any]) -> str:
    """Persist one synthetic GitHub tag object payload in shim state."""

    tag_objects: dict[str, dict[str, Any]] = state.setdefault("gh_tag_objects", {})
    fake_sha = f"harness-tag-object-{len(tag_objects) + 1}"
    tag_objects[fake_sha] = payload
    return fake_sha


def _apply_builtin_gh_tag_ref(
    state: dict[str, Any],
    endpoint: str,
    payload: dict[str, Any],
    *,
    force: bool,
) -> None:
    """Create or update a local annotated Git tag from a synthetic GitHub ref mutation."""

    ref_name = str(payload.get("ref") or f"refs/tags/{endpoint.rsplit('/', 1)[-1]}")
    tag_name = ref_name.removeprefix("refs/tags/")
    target_sha = str(payload.get("sha", ""))
    tag_objects = state.setdefault("gh_tag_objects", {})
    tag_payload = dict(tag_objects.get(target_sha) or {})
    target_commit = str(tag_payload.get("object") or "")
    if not tag_name or not target_commit:
        raise SystemExit("buildish-release-harness: builtin gh tag ref mutation is missing tag metadata")
    message = str(tag_payload.get("message") or tag_name)
    for repository in _builtin_gh_mutated_repositories(state):
        command = ["git", "-C", str(repository), "tag"]
        if force:
            command.append("-f")
        command.extend(["-a", tag_name, "-m", message, target_commit])
        subprocess.run(command, check=True, capture_output=True, text=True)


def _builtin_gh_mutated_repositories(state: dict[str, Any]) -> list[Path]:
    """Return the local repositories that should reflect synthetic GitHub tag mutations."""

    workspace_root = Path(str(state["workspace_root"]))
    origin_root = workspace_root / ".buildish-release-harness" / "git-origins" / "self"
    return [workspace_root, origin_root]


def _count_key(tool_name: str, behavior_index: int) -> str:
    """Return the state key used for one behavior's invocation count."""

    return f"{tool_name}:{behavior_index}"


def _delegate_to_real_tool(tool_name: str, argv: list[str]) -> subprocess.CompletedProcess[str]:
    """Run the real tool outside the shim directory when delegation is requested."""

    real_path = os.environ.get("BUILDISH_HARNESS_REAL_PATH", "")
    resolved = shutil.which(tool_name, path=real_path)
    if resolved is None:
        return subprocess.CompletedProcess([tool_name, *argv], 127, "", f"real tool not found: {tool_name}\n")
    child_env = dict(os.environ)
    child_env["PATH"] = real_path
    return subprocess.run(  # noqa: S603
        [resolved, *argv],
        env=child_env,
        cwd=str(Path.cwd()),
        text=True,
        capture_output=True,
        check=False,
    )


def _perform_file_writes(state: dict[str, Any], writes: list[dict[str, Any]]) -> None:
    """Create or replace all files scripted by one shim response."""

    workspace_root = Path(str(state["workspace_root"]))
    for write in writes:
        raw_path = os.path.expandvars(str(write["path"]))
        destination = Path(raw_path) if Path(raw_path).is_absolute() else (workspace_root / raw_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(str(write.get("content", "")), encoding="utf-8")
        if bool(write.get("executable", False)):
            destination.chmod(destination.stat().st_mode | 0o111)


def _record_invocation(
    *,
    state: dict[str, Any],
    tool_name: str,
    argv: list[str],
    exit_code: int,
    stdout: str,
    stderr: str,
    delegated: bool,
) -> None:
    """Append one normalized command-trace entry to the JSONL trace file."""

    env_capture = list(state.get("env_capture", []))
    env_snapshot = {key: os.environ[key] for key in env_capture if key in os.environ}
    call_site = os.environ.get("BUILDISH_HARNESS_CALL_SITE")
    if call_site is not None:
        env_snapshot["BUILDISH_HARNESS_CALL_SITE"] = call_site
    entry = {
        "tool": tool_name,
        "argv": argv,
        "cwd": str(Path.cwd()),
        "env": env_snapshot,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "delegated": delegated,
    }
    trace_file = Path(str(state["trace_file"]))
    with trace_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True))
        handle.write("\n")


if __name__ == "__main__":
    main()
