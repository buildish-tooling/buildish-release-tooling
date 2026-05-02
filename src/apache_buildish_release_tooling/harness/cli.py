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

"""CLI for the Buildish release harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from apache_buildish_release_tooling.harness.backend import (
    rerun_failed_jobs,
    run_scenario,
    run_scenario_sequence,
)
from apache_buildish_release_tooling.harness.config import load_release_harness_config
from apache_buildish_release_tooling.harness.errors import HarnessExternalToolError
from apache_buildish_release_tooling.harness.models import (
    HarnessRunResultJson,
    HarnessSequenceEntryJson,
    HarnessSequenceRunResultJson,
)
from apache_buildish_release_tooling.harness.runtime import HarnessRunResult, HarnessWorkspace
from apache_buildish_release_tooling.harness.scenario import load_scenario


def build_parser() -> argparse.ArgumentParser:
    """Create the top-level argument parser for the harness CLI."""

    parser = argparse.ArgumentParser(prog="buildish-release-harness")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a harness scenario once in a fresh workspace.")
    run_parser.add_argument("scenario", type=Path, help="Path to the scenario YAML file.")
    run_parser.add_argument(
        "--workspace-root",
        type=Path,
        default=None,
        help="Optional parent directory for the disposable workspace.",
    )
    run_parser.add_argument(
        "--seed-from",
        type=Path,
        default=None,
        help="Optional prior harness workspace whose Git and SVN state should seed this run.",
    )

    sequence_parser = subparsers.add_parser(
        "run-sequence",
        help="Run multiple harness scenarios in order, seeding each run from the previous workspace.",
    )
    sequence_parser.add_argument("scenarios", nargs="+", type=Path, help="Scenario YAML files to run in order.")
    sequence_parser.add_argument(
        "--workspace-root",
        type=Path,
        default=None,
        help="Optional parent directory for the disposable workspaces.",
    )

    rerun_parser = subparsers.add_parser(
        "rerun-failed",
        help="Rerun the failed jobs and their dependents in an existing workspace.",
    )
    rerun_parser.add_argument("scenario", type=Path, help="Path to the scenario YAML file.")
    rerun_parser.add_argument("workspace", type=Path, help="Path to the previously created workspace.")

    config_parser = subparsers.add_parser(
        "resolve-config",
        help="Resolve a committed release-harness.yaml plus its optional local override file.",
    )
    config_parser.add_argument("config", type=Path, help="Path to release-harness.yaml.")

    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse CLI arguments and execute the requested harness command."""

    parser = build_parser()
    args = parser.parse_args(argv)
    exit_code = 0
    try:
        if args.command == "resolve-config":
            payload = load_release_harness_config(args.config).to_json_model().model_dump(mode="json")
        else:
            if args.command == "run-sequence":
                scenarios = [load_scenario(path) for path in args.scenarios]
                results = run_scenario_sequence(scenarios, workspace_root=args.workspace_root)
                payload = HarnessSequenceRunResultJson(
                    sequence=[
                        HarnessSequenceEntryJson(
                            scenario=str(path),
                            workspace=str(result.workspace.root),
                            inspectable_paths=result.workspace.inspectable_paths_model(),
                            selected_job_ids=result.selected_job_ids,
                            failed_job_ids=result.failed_job_ids,
                            blocked_job_ids=result.blocked_job_ids,
                            job_statuses=result.job_statuses,
                        )
                        for path, result in zip(args.scenarios, results, strict=False)
                    ],
                    final_workspace=str(results[-1].workspace.root) if results else "",
                ).model_dump(mode="json")
                for scenario_path, result in zip(args.scenarios, results, strict=False):
                    sys.stderr.write(
                        f"buildish-release-harness scenario: {scenario_path}\n"
                    )
                    _emit_run_diagnostics(result)
                if any(result.failed_job_ids or result.blocked_job_ids for result in results):
                    exit_code = 1
            else:
                scenario = load_scenario(args.scenario)
                if args.command == "run":
                    result = run_scenario(
                        scenario,
                        workspace_root=args.workspace_root,
                        seed_from=args.seed_from,
                    )
                else:
                    result = rerun_failed_jobs(scenario, args.workspace)
                payload = _run_result_payload(result).model_dump(mode="json")
                _emit_run_diagnostics(result)
                if result.failed_job_ids or result.blocked_job_ids:
                    exit_code = 1
    except HarnessExternalToolError as exc:
        sys.stderr.write(f"{exc}\n")
        raise SystemExit(2) from None
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
    sys.stdout.write("\n")
    raise SystemExit(exit_code)


def _emit_run_diagnostics(result: HarnessRunResult) -> None:
    """Emit human-facing stderr diagnostics for one run or rerun."""

    sys.stderr.write(f"buildish-release-harness workspace: {result.workspace.root}\n")
    sys.stderr.write("buildish-release-harness inspectable paths:\n")
    for label, path in result.workspace.inspectable_paths().items():
        if label == "workspace_root":
            continue
        sys.stderr.write(f"  {label}: {path}\n")
    if not result.failed_job_ids and not result.blocked_job_ids:
        return
    sys.stderr.write("buildish-release-harness detected failed or blocked jobs.\n")
    if result.failed_job_ids:
        sys.stderr.write(f"failed jobs: {', '.join(result.failed_job_ids)}\n")
    if result.blocked_job_ids:
        sys.stderr.write(f"blocked jobs: {', '.join(result.blocked_job_ids)}\n")
    _emit_act_stderr_log(result.workspace)


def _run_result_payload(result: HarnessRunResult) -> HarnessRunResultJson:
    """Return the typed CLI JSON payload for one harness run or rerun."""

    return HarnessRunResultJson(
        workspace=str(result.workspace.root),
        inspectable_paths=result.workspace.inspectable_paths_model(),
        selected_job_ids=result.selected_job_ids,
        failed_job_ids=result.failed_job_ids,
        blocked_job_ids=result.blocked_job_ids,
        job_statuses=result.job_statuses,
    )


def _emit_act_stderr_log(workspace: HarnessWorkspace) -> None:
    """Dump the captured `act` stderr log to stderr when it exists and is non-empty."""

    act_stderr_log = workspace.harness_dir / "act-stderr.log"
    if not act_stderr_log.exists():
        return
    content = act_stderr_log.read_text(encoding="utf-8")
    if not content.strip():
        return
    sys.stderr.write(f"--- {act_stderr_log} ---\n")
    sys.stderr.write(content)
    if not content.endswith("\n"):
        sys.stderr.write("\n")
