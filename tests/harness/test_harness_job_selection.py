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

"""Unit tests for shared harness job-selection helpers."""

from __future__ import annotations

import unittest

from buildish_release_tooling.harness.job_selection import rerunnable_job_ids


class HarnessJobSelectionTest(unittest.TestCase):
    """Focused coverage for shared rerun job selection logic."""

    def test_rerunnable_job_ids_selects_failed_jobs_and_downstream_dependents(self) -> None:
        """Failed jobs should pull in all transitive dependents in dependency order."""

        self.assertEqual(
            ["publish", "announce", "finalize"],
            rerunnable_job_ids(
                ["prepare", "publish", "announce", "finalize"],
                {
                    "prepare": [],
                    "publish": ["prepare"],
                    "announce": ["publish"],
                    "finalize": ["announce"],
                },
                {"prepare": "success", "publish": "failed"},
            ),
        )

    def test_rerunnable_job_ids_returns_empty_when_no_jobs_failed(self) -> None:
        """Successful job graphs should not select any rerun targets."""

        self.assertEqual(
            [],
            rerunnable_job_ids(
                ["prepare", "publish"],
                {
                    "prepare": [],
                    "publish": ["prepare"],
                },
                {"prepare": "success", "publish": "success"},
            ),
        )
