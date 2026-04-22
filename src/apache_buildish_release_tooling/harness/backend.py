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

from pathlib import Path

from apache_buildish_release_tooling.harness import act_backend, runtime
from apache_buildish_release_tooling.harness.models import HarnessBackendName, HarnessScenario

HarnessRunResult = runtime.HarnessRunResult
HarnessWorkspace = runtime.HarnessWorkspace


def run_scenario(
    scenario: HarnessScenario,
    *,
    workspace_root: Path | None = None,
) -> HarnessRunResult:
    """Run a harness scenario through the selected execution backend."""

    if scenario.backend == "custom":
        return runtime.run_scenario(scenario, workspace_root=workspace_root)
    return act_backend.run_scenario(scenario, workspace_root=workspace_root)


def rerun_failed_jobs(scenario: HarnessScenario, workspace_root: Path) -> HarnessRunResult:
    """Rerun failed jobs for a scenario through the selected execution backend."""

    if scenario.backend == "custom":
        return runtime.rerun_failed_jobs(scenario, workspace_root)
    return act_backend.rerun_failed_jobs(scenario, workspace_root)


def supported_backends() -> tuple[HarnessBackendName, ...]:
    """Return the list of backend names exposed by the harness CLI."""

    return ("custom", "act")
