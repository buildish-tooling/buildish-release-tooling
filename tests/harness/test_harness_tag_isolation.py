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

"""Fresh provider scenarios must isolate inherited tags only in disposable copies."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from buildish_release_tooling.harness.backends.act import fixtures
from buildish_release_tooling.harness.backends.act.fixtures_git import (
    exclude_workflow_repository_tags,
    stage_repository_sources,
)
from buildish_release_tooling.harness.config import load_release_harness_config
from buildish_release_tooling.harness.models import HarnessScenario
from tests.support import component_root


class HarnessTagIsolationTest(unittest.TestCase):
    def test_fresh_tags_are_isolated_and_seeded_promotion_retains_new_tags(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()

            def git(repo: Path, *args: str) -> str:
                return subprocess.run(
                    [
                        "git",
                        "-C",
                        str(repo),
                        "-c",
                        "user.name=Fixture",
                        "-c",
                        "user.email=fixture@example.invalid",
                        "-c",
                        "commit.gpgsign=false",
                        "-c",
                        "tag.gpgsign=false",
                        "-c",
                        "core.hooksPath=/dev/null",
                        *args,
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()

            git(source, "init", "-b", "main")
            (source / "README").write_text("source\n", encoding="utf-8")
            git(source, "add", "README")
            git(source, "commit", "-m", "source")
            inherited = {"v9.0.0", "v9.0.0-rc1", "unrelated"}
            for tag in inherited:
                git(source, "tag", tag)
            config_path = (
                component_root()
                / "buildish-release-tooling/harness/release-harness.yaml"
            )
            bindings = load_release_harness_config(config_path)
            bindings = replace(bindings, self_repository=replace(bindings.self_repository, local_path=source))
            scenario = HarnessScenario.model_validate(
                {
                    "name": "fresh",
                    "backend": "act",
                    "workflow": {
                        "path": ".github/workflows/release.yml",
                        "harness_config": str(config_path),
                        "repository_fixture": {"excluded_tag_patterns": ["v*"]},
                    },
                }
            )
            workspace = fixtures._create_workspace(
                source, root / "runs", seed_workspace=None
            )
            stage_repository_sources(workspace, bindings, seed_workspace=None)
            exclude_workflow_repository_tags(workspace, scenario, bindings)
            slug = bindings.self_repository.repository_id.replace("/", "__")
            copies = [
                workspace.root,
                workspace.git_origins_dir / "self",
                workspace.repo_sources_dir / slug,
            ]
            for copy in copies:
                self.assertEqual("unrelated", git(copy, "tag", "--list"))
            self.assertEqual(inherited, set(git(source, "tag", "--list").splitlines()))
            # A subsequent seeded scenario keeps refs produced by the candidate.
            git(workspace.root, "tag", "v9.0.0-rc2")
            git(workspace.git_origins_dir / "self", "tag", "v9.0.0-rc2")
            promotion = fixtures._create_workspace(
                source, root / "runs", seed_workspace=workspace
            )
            stage_repository_sources(promotion, bindings, seed_workspace=workspace)
            if scenario.workflow is None:
                self.fail("missing workflow fixture")
            scenario.workflow.repository_fixture.excluded_tag_patterns = []
            exclude_workflow_repository_tags(promotion, scenario, bindings)
            for copy in [
                promotion.root,
                promotion.git_origins_dir / "self",
                promotion.repo_sources_dir / slug,
            ]:
                self.assertEqual(
                    {"unrelated", "v9.0.0-rc2"},
                    set(git(copy, "tag", "--list").splitlines()),
                )
            self.assertEqual(inherited, set(git(source, "tag", "--list").splitlines()))
