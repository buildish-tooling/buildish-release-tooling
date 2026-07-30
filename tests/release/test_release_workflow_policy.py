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
"""Policy checks for checked-in release workflows."""

from __future__ import annotations

import unittest
from pathlib import Path


class ReleaseWorkflowPolicyTest(unittest.TestCase):
    """Policy checks for release workflow controls."""

    def test_release_mutation_workflows_share_non_canceling_version_concurrency(
        self,
    ) -> None:
        """Prepare RC and Release Version must not race for the same repository/version."""

        repo_root = Path(__file__).resolve().parents[2]
        expected_block = "\n".join(
            [
                "concurrency:",
                "  group: buildish-release-${{ github.repository }}-${{ inputs.version }}",
                "  cancel-in-progress: false",
            ]
        )
        for workflow_name in [
            "releasey-20-prepare-rc.yml",
            "releasey-30-release-version.yml",
        ]:
            workflow_text = (
                repo_root / ".github" / "workflows" / workflow_name
            ).read_text(encoding="utf-8")
            self.assertIn(expected_block, workflow_text)


if __name__ == "__main__":
    unittest.main()
