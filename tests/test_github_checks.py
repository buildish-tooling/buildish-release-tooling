# Copyright 2026 The Apache Software Foundation
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

"""Tests for GitHub check-gate policy helpers."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest import mock

from apache_buildish_release_tooling.github_checks import (
    assert_ref_ready,
    resolve_repository_slug,
    total_count,
)


class GitHubChecksTest(unittest.TestCase):
    """Verify Buildish readiness policy for check runs and legacy statuses."""

    def test_total_count_includes_checks_and_statuses(self) -> None:
        self.assertEqual(
            3,
            total_count(
                {
                    "check_runs": [
                        {"name": "ci", "status": "completed", "conclusion": "success"},
                        {"name": "docs", "status": "completed", "conclusion": "skipped"},
                    ]
                },
                {"statuses": [{"context": "legacy-ci", "state": "success"}]},
            ),
        )

    def test_assert_ref_ready_accepts_success_and_skipped(self) -> None:
        self.assertEqual(
            3,
            assert_ref_ready(
                {
                    "check_runs": [
                        {"name": "ci", "status": "completed", "conclusion": "success"},
                        {"name": "docs", "status": "completed", "conclusion": "skipped"},
                    ]
                },
                {"statuses": [{"context": "legacy-ci", "state": "success"}]},
                require_at_least_one_check=True,
            ),
        )

    def test_assert_ref_ready_rejects_invalid_results(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid GitHub check runs"):
            assert_ref_ready(
                {
                    "check_runs": [
                        {"name": "ci", "status": "in_progress", "conclusion": None},
                        {"name": "lint", "status": "completed", "conclusion": "failure"},
                    ]
                },
                {"statuses": [{"context": "legacy-ci", "state": "failure"}]},
                require_at_least_one_check=False,
            )

    def test_zero_checks_policy_is_enforced_when_required(self) -> None:
        self.assertEqual(
            0,
            assert_ref_ready({"check_runs": []}, {"statuses": []}, require_at_least_one_check=False),
        )
        with self.assertRaisesRegex(ValueError, "no GitHub checks were found"):
            assert_ref_ready({"check_runs": []}, {"statuses": []}, require_at_least_one_check=True)

    def test_resolve_repository_slug_reads_origin_url(self) -> None:
        with mock.patch(
            "apache_buildish_release_tooling.github_checks.run_logged_command",
            return_value=subprocess.CompletedProcess(
                [],
                0,
                "https://github.com/apache/buildish-example.git\n",
                "",
            ),
        ):
            self.assertEqual(
                "apache/buildish-example",
                resolve_repository_slug(Path("/workspace/repo")),
            )

    def test_resolve_repository_slug_rejects_non_github_origin(self) -> None:
        with mock.patch(
            "apache_buildish_release_tooling.github_checks.run_logged_command",
            return_value=subprocess.CompletedProcess([], 0, "file:///tmp/repo\n", ""),
        ):
            with self.assertRaisesRegex(ValueError, "unable to resolve GitHub repository slug"):
                resolve_repository_slug(Path("/workspace/repo"))
