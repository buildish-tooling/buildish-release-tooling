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

"""Tests for the `act` execution backend of the Buildish release harness."""

from __future__ import annotations

import json
import os
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

import yaml

from apache_buildish_release_tooling.harness.act_backend import (
    _dump_workflow_yaml,
    _render_rewritten_workflow_yaml,
    _resolve_act_command,
)
from apache_buildish_release_tooling.harness.backend import rerun_failed_jobs, run_scenario
from apache_buildish_release_tooling.harness.cli import main as harness_main
from apache_buildish_release_tooling.harness.errors import HarnessExternalToolError
from apache_buildish_release_tooling.harness.scenario import load_scenario
from tests.support import (
    cleanup_sandbox,
    component_root,
    create_build_test_sandbox,
    create_fake_act_launcher,
    env_with_prepend_path,
)


class ActHarnessIntegrationTest(unittest.TestCase):
    """Integration coverage for the `act`-backed workflow harness path."""

    sandbox_dir: Path

    def setUp(self) -> None:
        """Create a disposable sandbox for one `act`-backend test."""

        self.sandbox_dir = create_build_test_sandbox()

    def tearDown(self) -> None:
        """Remove the disposable sandbox after each `act`-backend test."""

        cleanup_sandbox(self.sandbox_dir)

    def _scenario_path(self, filename: str) -> Path:
        """Return the path of one committed `act` scenario fixture."""

        return component_root() / "buildish-release-tooling" / "harness" / "scenarios" / filename

    def test_run_scenario_rewrites_workflow_for_local_composite_actions(self) -> None:
        """The `act` backend should rewrite the checked-in workflow before executing `act`."""

        act_path, state_dir = create_fake_act_launcher(self.sandbox_dir)
        scenario = load_scenario(self._scenario_path("releasey-10-create-release-branch.yaml"))

        with mock.patch.dict(
            os.environ,
            env_with_prepend_path(
                {"FAKE_ACT_STATE_DIR": str(state_dir)},
                prepend_dirs=(act_path,),
            ),
            clear=False,
        ), mock.patch("sys.stderr", StringIO()):
            result = run_scenario(scenario, workspace_root=self.sandbox_dir)

        self.assertEqual(["create-release-branch"], result.selected_job_ids)
        self.assertRegex(
            result.workspace.root.name,
            r"^scenario\.\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}\.",
        )
        self.assertEqual([], result.failed_job_ids)
        self.assertEqual([], result.blocked_job_ids)

        invocation = json.loads((state_dir / "invocation-1.json").read_text(encoding="utf-8"))
        self.assertIn("--bind", invocation["argv"])
        self.assertIn("--rm", invocation["argv"])
        self.assertIn("-P", invocation["argv"])
        self.assertIn("ubuntu-latest=catthehacker/ubuntu:act-latest", invocation["argv"])
        rewritten_workflow_path = Path(invocation["workflow_path"])
        self.assertEqual(
            rewritten_workflow_path.parent,
            result.workspace.root / ".github" / "workflows",
        )
        rewritten_text = rewritten_workflow_path.read_text(encoding="utf-8")
        rewritten_lines = rewritten_text.splitlines()
        self.assertEqual("# WARNING: This is not the original workflow file.", rewritten_lines[0])
        self.assertIn("buildish-release-harness", rewritten_lines[1])
        self.assertIn("Original workflow source:", rewritten_lines[2])
        self.assertIn("Verbatim original copy in this directory:", rewritten_lines[3])
        self.assertIn("name: Releasey Create Release Branch", rewritten_lines)
        self.assertIn("on:", rewritten_lines)
        original_copy_path = rewritten_workflow_path.with_name(
            f"{rewritten_workflow_path.stem}.original{rewritten_workflow_path.suffix}"
        )
        self.assertTrue(original_copy_path.is_file())
        self.assertEqual(
            (
                component_root()
                / ".github"
                / "workflows"
                / "releasey-10-create-release-branch.yml"
            ).read_text(encoding="utf-8"),
            original_copy_path.read_text(encoding="utf-8"),
        )
        payload = yaml.safe_load(rewritten_workflow_path.read_text(encoding="utf-8")) or {}
        steps = payload["jobs"]["create-release-branch"]["steps"]
        self.assertEqual("Harness bootstrap environment", steps[0]["name"])
        self.assertEqual(
            "./.buildish-release-harness/actions/local-checkout",
            steps[1]["uses"],
        )
        self.assertEqual(
            "./.buildish-release-harness/actions/setup-uv-noop",
            steps[2]["uses"],
        )
        self.assertEqual(
            "draft-branch-creation",
            steps[-2]["env"]["BUILDISH_HARNESS_STEP_ID"],
        )
        self.assertEqual("Harness record job status", steps[-1]["name"])
        self.assertIn("run: |", rewritten_text)
        self.assertEqual(
            "bash buildish-release-tooling/release-tooling.sh create-release-branch \\\n"
            "  --apply \\\n"
            "  \"$RELEASE_LINE\" \\\n"
            "  \"$SOURCE_REF\"\n",
            steps[-2]["run"],
        )
        job_summary_path = result.workspace.job_summaries_dir / "create-release-branch.md"
        self.assertTrue(job_summary_path.is_file())
        self.assertEqual("", job_summary_path.read_text(encoding="utf-8"))

    def test_rerun_failed_jobs_reinvokes_act_for_failed_jobs_and_dependents(self) -> None:
        """The `act` backend should select failed jobs and their dependents on rerun."""

        act_path, state_dir = create_fake_act_launcher(self.sandbox_dir)
        scenario = load_scenario(self._scenario_path("releasey-30-release-version.yaml"))

        with mock.patch.dict(
            os.environ,
            env_with_prepend_path(
                {
                    "FAKE_ACT_STATE_DIR": str(state_dir),
                    "FAKE_ACT_FAIL_ONCE_JOB": "create-final-tag",
                },
                prepend_dirs=(act_path,),
            ),
            clear=False,
        ), mock.patch("sys.stderr", StringIO()):
            first_result = run_scenario(scenario, workspace_root=self.sandbox_dir)
            rerun_result = rerun_failed_jobs(scenario, first_result.workspace.root)

        self.assertEqual(["create-final-tag"], first_result.failed_job_ids)
        self.assertEqual(
            ["publish-pypi-convenience-artifacts", "finalize-draft-github-release"],
            first_result.blocked_job_ids,
        )
        self.assertEqual(
            [
                "create-final-tag",
                "publish-pypi-convenience-artifacts",
                "finalize-draft-github-release",
            ],
            rerun_result.selected_job_ids,
        )
        self.assertEqual([], rerun_result.failed_job_ids)
        self.assertEqual([], rerun_result.blocked_job_ids)

        rerun_invocation = json.loads((state_dir / "invocation-2.json").read_text(encoding="utf-8"))
        self.assertEqual(
            [
                "create-final-tag",
                "publish-pypi-convenience-artifacts",
                "finalize-draft-github-release",
            ],
            rerun_invocation["selected_jobs"],
        )

    def test_run_scenario_streams_act_output_to_stderr_and_logs(self) -> None:
        """The backend should tee `act` stdout and stderr into both log files and stderr."""

        act_path, state_dir = create_fake_act_launcher(self.sandbox_dir)
        scenario = load_scenario(self._scenario_path("releasey-10-create-release-branch.yaml"))
        stderr = StringIO()

        with mock.patch.dict(
            os.environ,
            env_with_prepend_path(
                {
                    "FAKE_ACT_STATE_DIR": str(state_dir),
                    "FAKE_ACT_STDOUT_TEXT": "fake act stdout\n",
                    "FAKE_ACT_STDERR_TEXT": "fake act stderr\n",
                },
                prepend_dirs=(act_path,),
            ),
            clear=False,
        ), mock.patch("sys.stderr", stderr):
            result = run_scenario(scenario, workspace_root=self.sandbox_dir)

        stderr_text = stderr.getvalue()
        self.assertIn("fake act stdout", stderr_text)
        self.assertIn("fake act stderr", stderr_text)
        self.assertIn("invoking act for all jobs", stderr_text)
        self.assertEqual(
            "fake act stdout\n",
            (result.workspace.harness_dir / "act-stdout.log").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            "fake act stderr\n",
            (result.workspace.harness_dir / "act-stderr.log").read_text(encoding="utf-8"),
        )

    def test_resolve_act_command_prefers_act_then_gh_act_extension_binary(self) -> None:
        """The backend should prefer `act` and fall back to the installed gh-act binary."""

        with mock.patch("apache_buildish_release_tooling.harness.act_backend.shutil.which") as which_mock:
            which_mock.side_effect = lambda command: "/usr/bin/act" if command == "act" else None
            self.assertEqual(["act"], _resolve_act_command())

        with (
            mock.patch("apache_buildish_release_tooling.harness.act_backend.shutil.which") as which_mock,
            mock.patch(
                "apache_buildish_release_tooling.harness.act_backend._find_gh_act_extension_binary"
            ) as find_extension_mock,
        ):
            which_mock.return_value = None
            find_extension_mock.return_value = Path("/home/test/.local/share/gh/extensions/gh-act/gh-act")
            self.assertEqual(
                ["/home/test/.local/share/gh/extensions/gh-act/gh-act"],
                _resolve_act_command(),
            )

    def test_resolve_act_command_raises_clear_error_when_missing(self) -> None:
        """Missing local workflow runners should produce a direct actionable error."""

        with (
            mock.patch("apache_buildish_release_tooling.harness.act_backend.shutil.which") as which_mock,
            mock.patch(
                "apache_buildish_release_tooling.harness.act_backend._find_gh_act_extension_binary"
            ) as find_extension_mock,
        ):
            which_mock.return_value = None
            find_extension_mock.return_value = None
            with self.assertRaisesRegex(
                HarnessExternalToolError,
                "requires either the 'act' executable on PATH or GitHub CLI with the 'gh act' extension installed",
            ):
                _resolve_act_command()

    def test_cli_returns_nonzero_when_scenario_reports_failed_jobs(self) -> None:
        """The CLI should not exit successfully when the scenario run itself failed."""

        act_path, state_dir = create_fake_act_launcher(self.sandbox_dir)
        scenario_path = self._scenario_path("releasey-30-release-version.yaml")
        stderr = StringIO()

        with (
            mock.patch.dict(
                os.environ,
                env_with_prepend_path(
                    {
                        "FAKE_ACT_STATE_DIR": str(state_dir),
                        "FAKE_ACT_FAIL_ONCE_JOB": "create-final-tag",
                        "FAKE_ACT_STDERR_TEXT": "simulated act stderr\n",
                    },
                    prepend_dirs=(act_path,),
                ),
                clear=False,
            ),
            mock.patch("sys.stderr", stderr),
        ):
            with self.assertRaises(SystemExit) as exc_info:
                harness_main(["run", str(scenario_path), "--workspace-root", str(self.sandbox_dir)])
        self.assertEqual(1, exc_info.exception.code)
        stderr_text = stderr.getvalue()
        self.assertIn("buildish-release-harness: invoking act for all jobs", stderr_text)
        self.assertIn("buildish-release-harness workspace: ", stderr_text)
        self.assertIn("buildish-release-harness detected failed or blocked jobs.", stderr_text)
        self.assertIn("failed jobs: create-final-tag", stderr_text)
        self.assertIn("simulated act stderr", stderr_text)
        self.assertIn(".buildish-release-harness/act-stderr.log", stderr_text)

    def test_cli_emits_progress_messages_for_successful_act_run(self) -> None:
        """Successful `act` runs should still emit progress details to stderr."""

        act_path, state_dir = create_fake_act_launcher(self.sandbox_dir)
        scenario_path = self._scenario_path("releasey-10-create-release-branch.yaml")
        stderr = StringIO()

        with (
            mock.patch.dict(
                os.environ,
                env_with_prepend_path(
                    {
                        "FAKE_ACT_STATE_DIR": str(state_dir),
                    },
                    prepend_dirs=(act_path,),
                ),
                clear=False,
            ),
            mock.patch("sys.stderr", stderr),
        ):
            with self.assertRaises(SystemExit) as exc_info:
                harness_main(["run", str(scenario_path), "--workspace-root", str(self.sandbox_dir)])

        self.assertEqual(0, exc_info.exception.code)
        stderr_text = stderr.getvalue()
        self.assertIn("buildish-release-harness: loading harness config", stderr_text)
        self.assertIn("buildish-release-harness: preparing rewritten workflow", stderr_text)
        self.assertIn("buildish-release-harness: running command:", stderr_text)
        self.assertIn("buildish-release-harness workspace: ", stderr_text)

    def test_cli_reports_missing_act_backend_dependency_cleanly(self) -> None:
        """The CLI should print a direct message instead of a traceback when `act` is unavailable."""

        scenario_path = self._scenario_path("releasey-10-create-release-branch.yaml")
        stderr = StringIO()

        with (
            mock.patch(
                "apache_buildish_release_tooling.harness.act_backend._resolve_act_command",
                side_effect=HarnessExternalToolError("missing act test message"),
            ),
            mock.patch("sys.stderr", stderr),
        ):
            with self.assertRaises(SystemExit) as exc_info:
                harness_main(["run", str(scenario_path), "--workspace-root", str(self.sandbox_dir)])

        self.assertEqual(2, exc_info.exception.code)
        stderr_text = stderr.getvalue()
        self.assertIn("buildish-release-harness: loading harness config", stderr_text)
        self.assertTrue(stderr_text.rstrip().endswith("missing act test message"))


class ActWorkflowRewriteUnitTest(unittest.TestCase):
    """Focused tests for the workflow YAML rewrite renderer."""

    def test_dump_workflow_yaml_keeps_on_key_and_multiline_run_blocks(self) -> None:
        """The workflow dumper should keep `on:` literal and use block scalars for scripts."""

        rendered = _dump_workflow_yaml(
            {
                "name": "Example",
                "on": {"workflow_dispatch": {}},
                "jobs": {
                    "example": {
                        "steps": [
                            {
                                "name": "Example step",
                                "run": "printf 'hello\\n'\nprintf 'world\\n'\n",
                            }
                        ]
                    }
                },
            }
        )

        self.assertEqual("on:", rendered.splitlines()[1])
        self.assertIn("run: |", rendered)
        payload = yaml.safe_load(rendered)
        self.assertEqual(
            "printf 'hello\\n'\nprintf 'world\\n'\n",
            payload["jobs"]["example"]["steps"][0]["run"],
        )

    def test_render_rewritten_workflow_yaml_adds_prominent_header(self) -> None:
        """The rewritten workflow renderer should prepend a clear harness-generated warning header."""

        rendered = _render_rewritten_workflow_yaml(
            {
                "name": "Example",
                "on": {"workflow_dispatch": {}},
            },
            original_workflow_path=Path("/workspace/original.yml"),
            original_copy_name="example.original.yml",
        )

        lines = rendered.splitlines()
        self.assertEqual("# WARNING: This is not the original workflow file.", lines[0])
        self.assertIn("buildish-release-harness", lines[1])
        self.assertIn("/workspace/original.yml", lines[2])
        self.assertIn("example.original.yml", lines[3])
        self.assertIn("name: Example", lines)
        self.assertIn("on:", lines)
