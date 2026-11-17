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

"""End-to-end generated Action lifecycle through the service-isolated harness."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from buildish_release_tooling.harness.backend import run_scenario
from buildish_release_tooling.harness.models import HarnessScenario

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(
    shutil.which("node"), "Node is required for tagged Action consumer execution"
)
class MaterializedLifecycleHarnessTest(unittest.TestCase):
    def exercise(self, mode: str) -> None:
        driver = (
            ROOT / "buildish-release-tooling/harness/fixtures/materialized-lifecycle.py"
        ).read_text()
        scenario = HarnessScenario.model_validate(
            {
                "name": f"materialized-{mode}",
                "backend": "custom",
                "env": {
                    "MATERIALIZED_LIFECYCLE": mode,
                    "MATERIALIZED_PYTHON": sys.executable,
                    "GIT_CONFIG_COUNT": "2",
                    "GIT_CONFIG_KEY_0": "commit.gpgsign",
                    "GIT_CONFIG_VALUE_0": "false",
                    "GIT_CONFIG_KEY_1": "tag.gpgsign",
                    "GIT_CONFIG_VALUE_1": "false",
                },
                "workspace_files": [{"path": ".fixture/driver.py", "content": driver}],
                "git_repositories": [
                    {
                        "path": ".",
                        "files": [
                            {
                                "path": "README.md",
                                "content": "Reviewed source with no generated Action files.\n",
                            },
                            {
                                "path": ".gitignore",
                                "content": ".fixture/\n.buildish-release-harness/\ndist/\n",
                            },
                        ],
                    }
                ],
                "jobs": [
                    {
                        "id": step,
                        "needs": []
                        if index == 0
                        else [["prepare", "build", "publish"][index - 1]],
                        "steps": [
                            {
                                "id": step,
                                "run": f'"$MATERIALIZED_PYTHON" .fixture/driver.py {step}',
                            }
                        ],
                    }
                    for index, step in enumerate(("prepare", "build", "publish"))
                ],
            }
        )
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as temporary:
            result = run_scenario(scenario, workspace_root=Path(temporary))
            errors = result.workspace.harness_dir / "step-stderr.log"
            detail = errors.read_text()[-14000:] if errors.exists() else str(result.job_statuses)
            self.assertFalse(result.failed_job_ids, detail)
            self.assertFalse(result.blocked_job_ids, result.job_statuses)
            payload = json.loads(
                (result.workspace.root / ".fixture/result.json").read_text()
            )
            self.assertNotEqual(payload["source"], payload["materialized"])
            self.assertEqual(mode, payload["mode"])
            self.assertEqual(64, len(payload["sealed_digest"]))

    def test_materialized_direct_release(self) -> None:
        self.exercise("direct")

    def test_materialized_candidate_and_exact_promotion(self) -> None:
        self.exercise("candidate")
