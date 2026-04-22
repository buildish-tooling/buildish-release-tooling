# Copyright 2026 The Buildish Authors
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

"""Backend interface for the Buildish release harness."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from buildish_release_tooling.harness.models import HarnessBackendName, HarnessScenario
from buildish_release_tooling.harness.runtime import HarnessRunResult


class Backend(ABC):
    """Execution backend contract for harness scenarios."""

    name: HarnessBackendName

    @abstractmethod
    def run_scenario(
        self,
        scenario: HarnessScenario,
        *,
        workspace_root: Path | None = None,
        seed_from: Path | None = None,
    ) -> HarnessRunResult:
        """Run one scenario in a fresh workspace."""

    @abstractmethod
    def rerun_failed_jobs(self, scenario: HarnessScenario, workspace_root: Path) -> HarnessRunResult:
        """Rerun failed jobs for one scenario in an existing workspace."""
