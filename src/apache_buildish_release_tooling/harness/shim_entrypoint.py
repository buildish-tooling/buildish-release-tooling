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

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from apache_buildish_release_tooling.harness.models import (
    FileWriteAction,
    HarnessCommandTraceEntry,
    HarnessShimState,
    InvocationMatch,
    ToolBehaviorResult,
)
from apache_buildish_release_tooling.harness.process import run_harness_command
from apache_buildish_release_tooling.harness.runtime import resolve_workspace_relative_path
from apache_buildish_release_tooling.harness.shim_builtins import handle_builtin_tool
from apache_buildish_release_tooling.harness.shim_summary import append_step_summary, summary_text
from apache_buildish_release_tooling.shared.parsing import (
    DEFAULT_CONFIG_PARSE_MAX_BYTES,
    read_pydantic_json_file_bounded,
)


def main() -> None:
    """Dispatch one intercepted tool invocation according to the persisted scenario state."""

    if len(sys.argv) < 2:
        raise SystemExit("usage: shim_entrypoint.py <tool-name> [args...]")
    tool_name = sys.argv[1]
    argv = sys.argv[2:]
    state_path = Path(os.environ["BUILDISH_HARNESS_STATE_FILE"])
    state = read_pydantic_json_file_bounded(
        HarnessShimState,
        state_path,
        max_bytes=DEFAULT_CONFIG_PARSE_MAX_BYTES,
    )
    behavior_index, result = _resolve_behavior(state, tool_name, argv)
    if result is None:
        builtin_result = handle_builtin_tool(tool_name, argv, state)
        if builtin_result is not None:
            state_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
            _record_invocation(
                state=state,
                tool_name=tool_name,
                argv=argv,
                exit_code=builtin_result.exit_code,
                stdout=builtin_result.stdout,
                stderr=builtin_result.stderr,
                delegated=False,
            )
            if builtin_stdout := builtin_result.stdout:
                sys.stdout.write(builtin_stdout)
            if builtin_stderr := builtin_result.stderr:
                sys.stderr.write(builtin_stderr)
            raise SystemExit(builtin_result.exit_code)
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
    state_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    if result.delegate_to_real_tool:
        completed = _delegate_to_real_tool(tool_name, argv)
        append_step_summary(summary_text(tool_name, result, completed.stdout, command_argv=sys.argv[2:]))
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
    _perform_file_writes(state, result.writes)
    stdout = result.stdout
    stderr = result.stderr
    exit_code = result.exit_code
    append_step_summary(summary_text(tool_name, result, stdout, command_argv=sys.argv[2:]))
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


def _resolve_behavior(
    state: HarnessShimState,
    tool_name: str,
    argv: list[str],
) -> tuple[int, ToolBehaviorResult | None]:
    """Return the first matching scripted behavior that still has remaining uses."""

    behaviors = list(state.tool_behaviors.get(tool_name, []))
    counts = state.counts
    cwd = str(Path.cwd())
    env = os.environ
    for index, behavior in enumerate(behaviors):
        key = _count_key(tool_name, index)
        times = behavior.times
        if times is not None and counts.get(key, 0) >= times:
            continue
        if _matches(behavior.match, argv, cwd, env, state.workspace_root):
            return index, behavior.result
    return -1, None


def _matches(
    match: InvocationMatch,
    argv: list[str],
    cwd: str,
    env: Mapping[str, str],
    workspace_root: str,
) -> bool:
    """Return whether the configured matcher accepts the current invocation."""

    expected_argv = match.argv
    if expected_argv is not None and list(expected_argv) != argv:
        return False
    expected_prefix = match.argv_prefix
    if expected_prefix is not None and argv[: len(expected_prefix)] != list(expected_prefix):
        return False
    expected_contains = list(match.argv_contains)
    for fragment in expected_contains:
        if not any(fragment in argument for argument in argv):
            return False
    expected_cwd = match.cwd
    if expected_cwd is not None:
        expected_path = Path(workspace_root) / str(expected_cwd)
        if Path(cwd) != expected_path:
            return False
    expected_env = dict(match.env_contains)
    for key, expected_value in expected_env.items():
        if env.get(key) != expected_value:
            return False
    return True


def _increment_behavior_count(state: HarnessShimState, tool_name: str, behavior_index: int) -> None:
    """Increment the persisted call count for one scripted behavior."""

    key = _count_key(tool_name, behavior_index)
    state.counts[key] = state.counts.get(key, 0) + 1


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
    return run_harness_command(
        [resolved, *argv],
        env=child_env,
        cwd=str(Path.cwd()),
        text=True,
        capture_output=True,
        check=False,
    )


def _perform_file_writes(state: HarnessShimState, writes: list[FileWriteAction]) -> None:
    """Create or replace all files scripted by one shim response."""

    workspace_root = Path(state.workspace_root)
    for write in writes:
        raw_path = os.path.expandvars(write.path)
        destination = resolve_workspace_relative_path(workspace_root, raw_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(write.content, encoding="utf-8")
        if write.executable:
            destination.chmod(destination.stat().st_mode | 0o111)


def _record_invocation(
    *,
    state: HarnessShimState,
    tool_name: str,
    argv: list[str],
    exit_code: int,
    stdout: str,
    stderr: str,
    delegated: bool,
) -> None:
    """Append one normalized command-trace entry to the JSONL trace file."""

    env_capture = list(state.env_capture)
    env_snapshot = {key: os.environ[key] for key in env_capture if key in os.environ}
    call_site = os.environ.get("BUILDISH_HARNESS_CALL_SITE")
    if call_site is not None:
        env_snapshot["BUILDISH_HARNESS_CALL_SITE"] = call_site
    entry = HarnessCommandTraceEntry(
        tool=tool_name,
        argv=argv,
        cwd=str(Path.cwd()),
        env=env_snapshot,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        delegated=delegated,
    )
    trace_file = Path(state.trace_file)
    with trace_file.open("a", encoding="utf-8") as handle:
        handle.write(entry.model_dump_json())
        handle.write("\n")


if __name__ == "__main__":
    main()
