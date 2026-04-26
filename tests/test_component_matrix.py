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

"""Component-matrix integration tests for checked-in component policy fixtures."""

from __future__ import annotations

import shutil
import subprocess
import unittest
from dataclasses import dataclass
from pathlib import Path

from apache_buildish_release_tooling.asf_svn import AsfSvnClient

from tests.support import (
    cli_env,
    cleanup_sandbox,
    command_available,
    create_build_test_sandbox,
    create_fake_gh_launcher,
    dispatcher_env,
    fetch_git_origin_refs,
    fixture_component_config_path,
    fixture_component_dispatcher_path,
    git_create_annotated_tag,
    git_create_branch,
    git_rev_parse,
    init_git_origin_and_clone,
    init_svn_repo_and_checkout,
    read_json,
    run_cli,
    set_github_origin_url,
    tool_env,
    write_fixture_component_config,
)


@dataclass(frozen=True)
class ComponentCase:
    """Expected release behavior for one draft Buildish component."""

    component_id: str
    version: str
    release_line: str
    prepare_rc_tags: tuple[str, ...]
    expected_prepare_rc_number: str
    expected_prepare_rc_tag: str
    expected_final_tag_mode: str
    release_version_tags: tuple[str, ...]
    expected_selected_rc_tag: str
    published_release_versions: tuple[str, ...]
    expected_archive_versions: str
    expected_moving_tags: str


COMPONENT_CASES = (
    ComponentCase(
        component_id="buildish-mammoth-cache",
        version="1.2.3",
        release_line="1.2.x",
        prepare_rc_tags=("v1.2.3-rc0", "v1.2.3-rc2"),
        expected_prepare_rc_number="3",
        expected_prepare_rc_tag="v1.2.3-rc3",
        expected_final_tag_mode="detached-materialization-commit",
        release_version_tags=("v1.2.3-rc0", "v1.2.3-rc2"),
        expected_selected_rc_tag="v1.2.3-rc2",
        published_release_versions=("1.1.9", "1.2.1", "1.2.2", "2.0.0"),
        expected_archive_versions="1.2.1,1.2.2",
        expected_moving_tags="v1 v1.2",
    ),
    ComponentCase(
        component_id="buildish-no-gradle-wrapper-jar",
        version="1.2.3",
        release_line="1.2.x",
        prepare_rc_tags=("v1.2.3-rc0",),
        expected_prepare_rc_number="1",
        expected_prepare_rc_tag="v1.2.3-rc1",
        expected_final_tag_mode="rc-source-commit",
        release_version_tags=("v1.2.3-rc0",),
        expected_selected_rc_tag="v1.2.3-rc0",
        published_release_versions=("1.2.1", "1.2.2", "1.3.0"),
        expected_archive_versions="1.2.1,1.2.2",
        expected_moving_tags="",
    ),
    ComponentCase(
        component_id="buildish-site-pipeline",
        version="1.2.3",
        release_line="1.2.x",
        prepare_rc_tags=(),
        expected_prepare_rc_number="0",
        expected_prepare_rc_tag="v1.2.3-rc0",
        expected_final_tag_mode="rc-source-commit",
        release_version_tags=("v1.2.3-rc1",),
        expected_selected_rc_tag="v1.2.3-rc1",
        published_release_versions=("1.2.1", "1.2.2", "1.3.0"),
        expected_archive_versions="1.2.1,1.2.2",
        expected_moving_tags="1 1.2",
    ),
)


class ComponentMatrixIntegrationTest(unittest.TestCase):
    """Verify checked-in component-policy fixtures through the shared tooling."""

    @staticmethod
    def _bash_executable() -> str:
        """Return the absolute bash executable used for wrapper smoke tests."""

        return shutil.which("bash") or "/bin/bash"

    def _prepare_clone(
        self,
        case: ComponentCase,
        *,
        tags: tuple[str, ...],
    ) -> tuple[Path, Path]:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        for tag_name in tags:
            git_create_annotated_tag(origin_dir, tag_name)
        fetch_git_origin_refs(clone_dir)
        return sandbox_dir, clone_dir

    def test_prepare_rc_matches_fixture_component_policy(self) -> None:
        for case in COMPONENT_CASES:
            with self.subTest(component=case.component_id):
                sandbox_dir, clone_dir = self._prepare_clone(case, tags=case.prepare_rc_tags)
                manifest_path = sandbox_dir / f"{case.component_id}-prepare-rc.json"
                expected_commit = git_rev_parse(
                    clone_dir,
                    "refs/remotes/origin/release/1.2.x^{commit}",
                )
                completed = run_cli(
                    [
                        "prepare-rc",
                        "--component-config",
                        str(fixture_component_config_path(case.component_id)),
                        case.version,
                    ],
                    cwd=clone_dir,
                    env=cli_env(manifest_path),
                )
                self.assertEqual(0, completed.returncode, msg=completed.stderr)
                manifest = read_json(manifest_path)
                self.assertEqual(case.component_id, manifest["component"])
                self.assertEqual(expected_commit, manifest["resolved_source_ref"])
                self.assertEqual("release/1.2.x", manifest["resolved_release_branch"])
                self.assertEqual(case.expected_prepare_rc_number, manifest["rc_number"])
                self.assertEqual(case.expected_prepare_rc_tag, manifest["rc_tag"])
                self.assertEqual(case.expected_final_tag_mode, manifest["final_tag_mode"])

    def test_release_version_matches_fixture_component_policy(self) -> None:
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        for case in COMPONENT_CASES:
            with self.subTest(component=case.component_id):
                sandbox_dir, clone_dir = self._prepare_clone(case, tags=case.release_version_tags)
                _repo_dir, repo_url, _working_copy_dir = init_svn_repo_and_checkout(sandbox_dir)
                config_path = write_fixture_component_config(
                    case.component_id,
                    sandbox_dir / f"{case.component_id}-release-config.yaml",
                    asf_dist_dev_base=f"{repo_url}/dist/dev/incubator/buildish/{case.component_id}",
                    asf_dist_release_base=f"{repo_url}/dist/release/incubator/buildish/{case.component_id}",
                )
                client = AsfSvnClient()
                release_base_url = f"{repo_url}/dist/release/incubator/buildish/{case.component_id}"
                set_github_origin_url(clone_dir, f"apache/{case.component_id}")
                client.mkdir_url(release_base_url, f"create {case.component_id} release base")
                for published_version in case.published_release_versions:
                    client.mkdir_url(
                        f"{release_base_url}/{published_version}",
                        f"create {published_version}",
                    )
                selected_rc_commit = git_rev_parse(clone_dir, f"{case.expected_selected_rc_tag}^{{commit}}")
                gh_path, gh_state_dir = create_fake_gh_launcher(
                    sandbox_dir,
                    list_response=[
                        {
                            "id": 42,
                            "draft": True,
                            "tag_name": case.expected_selected_rc_tag,
                            "name": f"{case.component_id} {case.version}",
                            "body": "\n".join(
                                [
                                    f"RC tag: {case.expected_selected_rc_tag}",
                                    f"Resolved source ref: {selected_rc_commit}",
                                ]
                            ),
                        }
                    ],
                )
                manifest_path = sandbox_dir / f"{case.component_id}-release-version.json"
                completed = run_cli(
                    [
                        "release-version",
                        "--component-config",
                        str(config_path),
                        "--allow-non-production-release-targets",
                        case.version,
                    ],
                    cwd=clone_dir,
                    env=cli_env(
                        manifest_path,
                        extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                        prepend_dirs=(gh_path.parent,),
                    ),
                )
                self.assertEqual(0, completed.returncode, msg=completed.stderr)
                manifest = read_json(manifest_path)
                self.assertEqual(case.component_id, manifest["component"])
                self.assertEqual(case.release_line, manifest["release_line"])
                self.assertEqual(case.expected_selected_rc_tag, manifest["selected_rc_tag"])
                self.assertEqual(case.expected_archive_versions, manifest["archive_versions"])
                self.assertEqual(case.expected_moving_tags, manifest["moving_tags"])
                self.assertEqual(case.expected_final_tag_mode, manifest["final_tag_mode"])

    def test_component_dispatchers_smoke_test_fixture_component_configs(self) -> None:
        for case in COMPONENT_CASES:
            with self.subTest(component=case.component_id):
                sandbox_dir, clone_dir = self._prepare_clone(case, tags=case.prepare_rc_tags)
                manifest_path = sandbox_dir / f"{case.component_id}-dispatcher.json"
                completed = subprocess.run(
                    [
                        self._bash_executable(),
                        str(fixture_component_dispatcher_path(case.component_id)),
                        "prepare-rc",
                        case.version,
                    ],
                    cwd=str(clone_dir),
                    env=dispatcher_env(
                        sandbox_dir,
                        cli_env(manifest_path),
                    ),
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(0, completed.returncode, msg=completed.stderr)
                manifest = read_json(manifest_path)
                self.assertEqual(case.component_id, manifest["component"])
                self.assertEqual(case.expected_final_tag_mode, manifest["final_tag_mode"])

    def test_dispatcher_rejects_unsupported_command(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        completed = subprocess.run(
            [
                self._bash_executable(),
                str(fixture_component_dispatcher_path("buildish-mammoth-cache")),
                "unsupported-command",
            ],
            cwd=str(fixture_component_dispatcher_path("buildish-mammoth-cache").parent),
            env=dispatcher_env(sandbox_dir, tool_env()),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("unsupported-command", completed.stderr)
        self.assertIn("invalid choice", completed.stderr)
