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

"""Tests for GitHub check-gate policy helpers."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest import mock

from buildish_release_tooling.release.platforms.github.checks import (
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
                ["ci", "docs", "legacy-ci"],
            ),
        )

    def test_trusted_workflow_rejects_same_name_from_wrong_producer(self) -> None:
        trusted_runs = {
            "workflow_runs": [
                {
                    "check_suite_id": 41,
                    "path": ".github/workflows/ci.yml@main",
                    "event": "push",
                    "head_branch": "main",
                }
            ]
        }
        valid_check = {
            "name": "Required Checks",
            "status": "completed",
            "conclusion": "success",
            "app": {"slug": "github-actions"},
            "check_suite": {"id": 41},
        }
        self.assertEqual(
            1,
            assert_ref_ready(
                {"check_runs": [valid_check]},
                {"statuses": []},
                ["Required Checks"],
                trusted_workflow_path=".github/workflows/ci.yml",
                trusted_event="push",
                trusted_branch="main",
                workflow_runs_payload=trusted_runs,
            ),
        )
        for untrusted_check in (
            {**valid_check, "check_suite": {"id": 99}},
            {**valid_check, "app": {"slug": "other-app"}},
        ):
            with self.subTest(untrusted_check=untrusted_check):
                with self.assertRaisesRegex(
                    ValueError, "required GitHub checks not found"
                ):
                    assert_ref_ready(
                        {"check_runs": [untrusted_check]},
                        {
                            "statuses": [
                                {"context": "Required Checks", "state": "success"}
                            ]
                        },
                        ["Required Checks"],
                        trusted_workflow_path=".github/workflows/ci.yml",
                        trusted_event="push",
                        trusted_branch="main",
                        workflow_runs_payload=trusted_runs,
                    )
        wrong_branch_runs = {
            "workflow_runs": [
                {
                    "check_suite_id": 41,
                    "path": ".github/workflows/ci.yml@release/test",
                    "event": "push",
                    "head_branch": "release/test",
                }
            ]
        }
        with self.assertRaisesRegex(ValueError, "required GitHub checks not found"):
            assert_ref_ready(
                {"check_runs": [valid_check]},
                {"statuses": []},
                ["Required Checks"],
                trusted_workflow_path=".github/workflows/ci.yml",
                trusted_event="push",
                trusted_branch="main",
                workflow_runs_payload=wrong_branch_runs,
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
                ["ci", "lint", "legacy-ci"],
            )

    def test_only_named_checks_are_enforced(self) -> None:
        self.assertEqual(
            0,
            assert_ref_ready(
                {
                    "check_runs": [
                        {
                            "name": "release-workflow",
                            "status": "in_progress",
                            "conclusion": None,
                        }
                    ]
                },
                {"statuses": []},
                [],
            ),
        )
        with self.assertRaisesRegex(ValueError, "required GitHub checks not found: ci"):
            assert_ref_ready({"check_runs": []}, {"statuses": []}, ["ci"])

    def test_total_count_rejects_malformed_payloads(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid GitHub check-runs payload"):
            total_count(
                {"check_runs": "not-a-list"},
                {"statuses": []},
            )
        with self.assertRaisesRegex(ValueError, "invalid GitHub statuses payload"):
            total_count(
                {"check_runs": []},
                {"statuses": "not-a-list"},
            )

    def test_assert_ref_ready_rejects_malformed_payloads(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid GitHub check-runs payload"):
            assert_ref_ready(
                {"check_runs": [{"name": []}]},
                {"statuses": []},
                [],
            )
        with self.assertRaisesRegex(ValueError, "invalid GitHub statuses payload"):
            assert_ref_ready(
                {"check_runs": []},
                {"statuses": [{"context": []}]},
                [],
            )

    def test_resolve_repository_slug_reads_origin_url(self) -> None:
        with mock.patch(
            "buildish_release_tooling.release.platforms.github.checks.run_logged_command",
            return_value=subprocess.CompletedProcess(
                [],
                0,
                "https://github.com/apache/example-project.git\n",
                "",
            ),
        ):
            self.assertEqual(
                "apache/example-project",
                resolve_repository_slug(Path("/workspace/repo")),
            )

    def test_resolve_repository_slug_rejects_non_github_origin(self) -> None:
        with mock.patch(
            "buildish_release_tooling.release.platforms.github.checks.run_logged_command",
            return_value=subprocess.CompletedProcess([], 0, "file:///tmp/repo\n", ""),
        ):
            with self.assertRaisesRegex(ValueError, "unable to resolve GitHub repository slug"):
                resolve_repository_slug(Path("/workspace/repo"))
