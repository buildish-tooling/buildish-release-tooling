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

"""Backend dispatch for the Buildish release harness."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from apache_buildish_release_tooling.harness import runtime
from apache_buildish_release_tooling.harness.backends import get_backend
from apache_buildish_release_tooling.harness.models import HarnessScenario

HarnessRunResult = runtime.HarnessRunResult
HarnessWorkspace = runtime.HarnessWorkspace


def run_scenario(
    scenario: HarnessScenario,
    *,
    workspace_root: Path | None = None,
    seed_from: Path | None = None,
) -> HarnessRunResult:
    """Run a harness scenario through the selected execution backend."""

    return get_backend(scenario.backend).run_scenario(
        scenario,
        workspace_root=workspace_root,
        seed_from=seed_from,
    )


def rerun_failed_jobs(scenario: HarnessScenario, workspace_root: Path) -> HarnessRunResult:
    """Rerun failed jobs for a scenario through the selected execution backend."""

    return get_backend(scenario.backend).rerun_failed_jobs(scenario, workspace_root)


def run_scenario_sequence(
    scenarios: Sequence[HarnessScenario],
    *,
    workspace_root: Path | None = None,
) -> list[HarnessRunResult]:
    """Run multiple scenarios in order, seeding each run from the previous workspace."""

    results: list[HarnessRunResult] = []
    seed_from: Path | None = None
    for scenario in scenarios:
        result = run_scenario(
            scenario,
            workspace_root=workspace_root,
            seed_from=seed_from,
        )
        results.append(result)
        if result.failed_job_ids or result.blocked_job_ids:
            break
        seed_from = result.workspace.root
    return results
