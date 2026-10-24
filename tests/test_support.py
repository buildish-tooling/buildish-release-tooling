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

"""Regression tests for shared test fixtures."""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from tests.support import (
    cleanup_sandbox,
    copy_test_tree,
    create_build_test_sandbox,
    git_rev_parse,
    init_git_origin_and_clone,
    run_quiet,
)


class GitFixtureTest(unittest.TestCase):
    def test_git_fixtures_do_not_start_maintenance_before_copying(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        trace_path = sandbox_dir / "git-trace.jsonl"

        with mock.patch.dict(os.environ, {"GIT_TRACE2_EVENT": str(trace_path)}):
            origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
            for index, repo_dir in enumerate((origin_dir, clone_dir)):
                with self.subTest(repository=repo_dir.name):
                    run_quiet(
                        ["git", "-C", str(repo_dir), "commit", "--allow-empty", "-m", "fixture update"],
                        check=True,
                    )
                    copied_dir = copy_test_tree(repo_dir, sandbox_dir / f"copy-{index}")
                    self.assertEqual(
                        git_rev_parse(repo_dir, "HEAD"), git_rev_parse(copied_dir, "HEAD")
                    )

        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
        maintenance_commands = [
            event["argv"]
            for event in events
            if event["event"] == "child_start"
            and any(arg in {"maintenance", "gc"} for arg in event["argv"])
        ]
        self.assertEqual([], maintenance_commands)
