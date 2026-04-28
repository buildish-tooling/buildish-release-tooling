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

"""Tests for the Buildish release harness."""

from __future__ import annotations
import json
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

from apache_buildish_release_tooling.harness.backend import (
    rerun_failed_jobs,
    run_scenario,
)
from apache_buildish_release_tooling.harness.runtime import (
    summarize_trace,
)
from apache_buildish_release_tooling.harness.scenario import load_scenario
from tests.support import cleanup_sandbox, component_root, create_build_test_sandbox, tool_env


class HarnessIntegrationTest(unittest.TestCase):
    """Integration coverage for the first custom backend of the harness."""

    sandbox_dir: Path

    def setUp(self) -> None:
        """Create a disposable sandbox for one harness test."""

        self.sandbox_dir = create_build_test_sandbox()

    def tearDown(self) -> None:
        """Remove the disposable sandbox after each harness test."""

        cleanup_sandbox(self.sandbox_dir)

    def _write_scenario(self, name: str, payload: dict[str, object]) -> Path:
        """Write one temporary scenario YAML file into the sandbox."""

        path = self.sandbox_dir / name
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        return path

    def test_checked_in_example_scenarios_load(self) -> None:
        """The documented example scenarios should stay loadable."""

        scenarios_dir = component_root() / "buildish-release-tooling" / "harness" / "scenarios"
        loaded_names = []
        for scenario_path in sorted(scenarios_dir.glob("*.yaml")):
            loaded_names.append(load_scenario(scenario_path).name)
        self.assertEqual(
            [
                "basic-success",
                "fail-once-rerun",
                "releasey-create-release-branch",
                "releasey-prepare-rc",
                "releasey-release-version",
                "releasey-verify-rc",
            ],
            loaded_names,
        )

    def test_run_scenario_captures_trace_and_summary(self) -> None:
        """A successful scenario should record the shimmed command trace and step summary."""

        scenario_path = self._write_scenario(
            "basic.yaml",
            {
                "name": "basic-success",
                "env_capture": ["SCENARIO_FLAG"],
                "env": {"SCENARIO_FLAG": "enabled"},
                "workspace_files": [
                    {
                        "path": "repo/README.md",
                        "content": "hello\n",
                    }
                ],
                "tool_behaviors": {
                    "gh": [
                        {
                            "match": {"argv_prefix": ["api", "repos/demo"]},
                            "result": {"stdout": "{\"ok\":true}\n"},
                        }
                    ]
                },
                "jobs": [
                    {
                        "id": "prepare",
                        "steps": [
                            {
                                "id": "call-gh",
                                "cwd": "repo",
                                "run": "gh api repos/demo\nprintf 'summary ok\\n' >> \"$GITHUB_STEP_SUMMARY\"\n",
                            }
                        ],
                    }
                ],
            },
        )
        scenario = load_scenario(scenario_path)
        result = run_scenario(scenario, workspace_root=self.sandbox_dir)
        self.assertRegex(
            result.workspace.root.name,
            r"^scenario\.\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}\.",
        )
        self.assertEqual(
            {
                "workspace_root",
                "primary_git_checkout",
                "rewritten_workflows",
                "harness_root",
                "generated_actions",
                "repo_sources",
                "git_origins",
                "self_git_origin",
                "git_checkouts",
                "svn_root",
                "svn_repository",
                "svn_working_copy",
                "step_summaries",
                "job_summaries",
                "job_statuses",
                "command_trace",
            },
            set(result.workspace.inspectable_paths()),
        )
        self.assertTrue(result.workspace.git_origins_dir.is_dir())
        self.assertTrue(result.workspace.git_checkouts_dir.is_dir())
        self.assertTrue(result.workspace.svn_repository_dir.parent.is_dir())
        self.assertTrue(result.workspace.svn_working_copy_dir.parent.is_dir())
        self.assertEqual([], result.failed_job_ids)
        self.assertEqual([], result.blocked_job_ids)
        trace = summarize_trace(result.workspace)
        self.assertEqual(1, len(trace))
        self.assertEqual("gh", trace[0]["tool"])
        self.assertEqual(["api", "repos/demo"], trace[0]["argv"])
        self.assertEqual("enabled", trace[0]["env"]["SCENARIO_FLAG"])
        self.assertIn("BUILDISH_HARNESS_CALL_SITE", trace[0]["env"])
        summary_path = result.workspace.summaries_dir / "prepare__call-gh.md"
        self.assertEqual("summary ok\n", summary_path.read_text(encoding="utf-8"))
        job_summary_path = result.workspace.job_summaries_dir / "prepare.md"
        self.assertEqual("summary ok\n", job_summary_path.read_text(encoding="utf-8"))

    def test_rerun_failed_jobs_reuses_workspace_and_failure_schedule(self) -> None:
        """A fail-once tool behavior should succeed on rerun without rebuilding the workspace."""

        scenario_path = self._write_scenario(
            "rerun.yaml",
            {
                "name": "rerun-failed",
                "tool_behaviors": {
                    "docker": [
                        {
                            "match": {"argv_prefix": ["buildx", "imagetools", "create"]},
                            "result": {"exit_code": 17, "stderr": "temporary outage\n"},
                            "times": 1,
                        },
                        {
                            "match": {"argv_prefix": ["buildx", "imagetools", "create"]},
                            "result": {"stdout": "published\n"},
                        },
                    ]
                },
                "jobs": [
                    {
                        "id": "publish",
                        "steps": [
                            {
                                "id": "publish-image",
                                "run": (
                                    "docker buildx imagetools create "
                                    "--tag docker.io/example/app:1 "
                                    "docker.io/example/app:1\n"
                                ),
                            }
                        ],
                    },
                    {
                        "id": "finalize",
                        "needs": ["publish"],
                        "steps": [
                            {
                                "id": "write-summary",
                                "run": "printf 'finalized\\n' >> \"$GITHUB_STEP_SUMMARY\"\n",
                            }
                        ],
                    },
                ],
            },
        )
        scenario = load_scenario(scenario_path)
        first_result = run_scenario(scenario, workspace_root=self.sandbox_dir)
        self.assertEqual(["publish"], first_result.failed_job_ids)
        self.assertEqual(["finalize"], first_result.blocked_job_ids)
        rerun_result = rerun_failed_jobs(scenario, first_result.workspace.root)
        self.assertEqual([], rerun_result.failed_job_ids)
        self.assertEqual([], rerun_result.blocked_job_ids)
        self.assertEqual("success", rerun_result.job_statuses["publish"])
        self.assertEqual("success", rerun_result.job_statuses["finalize"])
        trace = summarize_trace(rerun_result.workspace)
        docker_invocations = [entry for entry in trace if entry["tool"] == "docker"]
        self.assertEqual(2, len(docker_invocations))
        self.assertEqual(17, docker_invocations[0]["exit_code"])
        self.assertEqual(0, docker_invocations[1]["exit_code"])
        summary_path = rerun_result.workspace.summaries_dir / "finalize__write-summary.md"
        self.assertEqual("finalized\n", summary_path.read_text(encoding="utf-8"))
        job_summary_path = rerun_result.workspace.job_summaries_dir / "finalize.md"
        self.assertEqual("finalized\n", job_summary_path.read_text(encoding="utf-8"))

    def test_nested_bash_invocation_inherits_bash_env_function_shims(self) -> None:
        """A nested non-interactive Bash call should still record the function-shim call-site."""

        scenario_path = self._write_scenario(
            "nested.yaml",
            {
                "name": "nested-bash",
                "git_repositories": [
                    {
                        "path": "repo",
                        "files": [{"path": "README.md", "content": "root\n"}],
                    }
                ],
                "tool_behaviors": {
                    "gh": [
                        {
                            "match": {"argv_prefix": ["api", "nested/call"]},
                            "result": {"stdout": "nested ok\n"},
                        }
                    ]
                },
                "jobs": [
                    {
                        "id": "inspect",
                        "steps": [
                            {
                                "id": "nested",
                                "cwd": "repo",
                                "run": "git rev-parse --verify HEAD >/dev/null\nbash -c 'gh api nested/call'\n",
                            }
                        ],
                    }
                ],
            },
        )
        scenario = load_scenario(scenario_path)
        result = run_scenario(scenario, workspace_root=self.sandbox_dir)
        self.assertEqual([], result.failed_job_ids)
        trace = summarize_trace(result.workspace)
        self.assertEqual(1, len(trace))
        self.assertEqual("gh", trace[0]["tool"])
        self.assertIn("BUILDISH_HARNESS_CALL_SITE", trace[0]["env"])

    def test_buildish_release_tooling_shim_appends_stdout_to_step_summary(self) -> None:
        """Mocked `buildish-release-tooling` invocations should populate the current step summary."""

        state_path = self.sandbox_dir / "shim-state.json"
        trace_path = self.sandbox_dir / "trace.jsonl"
        summaries_dir = self.sandbox_dir / "summaries"
        summary_path = summaries_dir / "prepare__verify-source-ref-checks.md"
        state_path.write_text(
            json.dumps(
                {
                    "workspace_root": str(self.sandbox_dir),
                    "trace_file": str(trace_path),
                    "tool_behaviors": {
                        "buildish-release-tooling": [
                            {
                                "match": {"argv": ["verify-source-ref-checks", "1.2.3"]},
                                "result": {"stdout": "checks passed\n"},
                            }
                        ]
                    },
                    "counts": {},
                    "env_capture": [],
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "apache_buildish_release_tooling.harness.shim_entrypoint",
                "buildish-release-tooling",
                "verify-source-ref-checks",
                "1.2.3",
            ],
            cwd=str(self.sandbox_dir),
            env=tool_env(
                {
                    "BUILDISH_HARNESS_STATE_FILE": str(state_path),
                    "BUILDISH_HARNESS_SUMMARIES_DIR": str(summaries_dir),
                    "BUILDISH_HARNESS_JOB_ID": "prepare",
                    "BUILDISH_HARNESS_STEP_ID": "verify-source-ref-checks",
                }
            ),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, completed.returncode)
        self.assertEqual("checks passed\n", completed.stdout)
        self.assertEqual("", completed.stderr)
        summary_text = summary_path.read_text(encoding="utf-8")
        self.assertIn("Verify GitHub checks for source ref 1.2.3", summary_text)
        self.assertIn("checks passed", summary_text)

    def test_scripted_gh_shim_does_not_block_on_open_stdin(self) -> None:
        """Scripted `gh` responses should not wait for stdin EOF when no builtin payload is needed."""

        state_path = self.sandbox_dir / "shim-state.json"
        trace_path = self.sandbox_dir / "trace.jsonl"
        state_path.write_text(
            json.dumps(
                {
                    "workspace_root": str(self.sandbox_dir),
                    "trace_file": str(trace_path),
                    "tool_behaviors": {
                        "gh": [
                            {
                                "match": {"argv": ["api", "repos/demo"]},
                                "result": {"stdout": "{\"ok\":true}\n"},
                            }
                        ]
                    },
                    "counts": {},
                    "env_capture": [],
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        shim_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "apache_buildish_release_tooling.harness.shim_entrypoint",
                "gh",
                "api",
                "repos/demo",
            ],
            cwd=str(self.sandbox_dir),
            env=tool_env({"BUILDISH_HARNESS_STATE_FILE": str(state_path)}),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            exit_code = shim_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            shim_process.kill()
            shim_process.communicate(timeout=5)
            self.fail("scripted gh shim blocked while waiting for stdin EOF")

        stdout, stderr = shim_process.communicate(timeout=1)
        self.assertEqual(0, exit_code)
        self.assertEqual("{\"ok\":true}\n", stdout)
        self.assertEqual("", stderr)
        trace = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(1, len(trace))
        self.assertEqual("gh", trace[0]["tool"])
        self.assertEqual(["api", "repos/demo"], trace[0]["argv"])

    def test_uv_shim_preserves_summary_capture_through_bash_shim(self) -> None:
        """The `bash` shim must not truncate summaries when the `uv` shim runs beneath it."""

        scenario_path = self._write_scenario(
            "uv-summary.yaml",
            {
                "name": "uv-summary",
                "tool_behaviors": {
                    "buildish-release-tooling": [
                        {
                            "match": {"argv": ["verify-source-ref-checks", "1.2.3"]},
                            "result": {"stdout": "checks passed\n"},
                        }
                    ]
                },
                "jobs": [
                    {
                        "id": "verify",
                        "steps": [
                            {
                                "id": "run-tooling",
                                "run": (
                                    "uv run --project . --frozen buildish-release-tooling "
                                    "verify-source-ref-checks --component-config dummy 1.2.3\n"
                                ),
                            }
                        ],
                    }
                ],
            },
        )
        scenario = load_scenario(scenario_path)
        result = run_scenario(scenario, workspace_root=self.sandbox_dir)

        self.assertEqual([], result.failed_job_ids)
        summary_path = result.workspace.summaries_dir / "verify__run-tooling.md"
        summary_text = summary_path.read_text(encoding="utf-8")
        self.assertIn("Verify GitHub checks for source ref 1.2.3", summary_text)
        self.assertIn("checks passed", summary_text)
        job_summary_path = result.workspace.job_summaries_dir / "verify.md"
        self.assertIn("checks passed", job_summary_path.read_text(encoding="utf-8"))
