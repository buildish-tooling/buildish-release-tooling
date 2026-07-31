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

"""Workflow rewrite tests for the `act` execution backend of the Buildish release harness."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

from buildish_release_tooling.harness.backends.act import (
    _dump_workflow_yaml,
    _render_rewritten_workflow_yaml,
    _render_uv_shim_script,
)
from buildish_release_tooling.harness.backends.act.workflow import (
    _rewrite_workflow,
)
from buildish_release_tooling.harness.backends.act.workflow_helpers import _step_identifier
from buildish_release_tooling.harness.backends.act.workflow_yaml import _load_job_definitions
from buildish_release_tooling.harness import runtime
from buildish_release_tooling.harness.config import (
    ResolvedReleaseHarnessConfig,
    ResolvedRepositoryBinding,
)
from buildish_release_tooling.harness.models import WorkflowScenario
from tests.support import (
    cleanup_sandbox,
    cli_env,
    component_root,
    create_build_test_sandbox,
)


class ActWorkflowRewriteUnitTest(unittest.TestCase):
    """Focused tests for the workflow YAML rewrite renderer."""

    sandbox_dir: Path

    def setUp(self) -> None:
        """Create a disposable sandbox for direct uv-shim tests."""

        self.sandbox_dir = create_build_test_sandbox()

    def tearDown(self) -> None:
        """Remove the disposable sandbox after each workflow-renderer test."""

        cleanup_sandbox(self.sandbox_dir)

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

    def test_rewrite_workflow_renders_stable_generated_yaml(self) -> None:
        """A representative workflow rewrite should keep a stable generated YAML shape."""

        workflow_path = self.sandbox_dir / "workflow.yml"
        workflow_path.write_text(
            yaml.safe_dump(
                {
                    "name": "Example",
                    "on": {"workflow_dispatch": {}},
                    "jobs": {
                        "example": {
                            "steps": [
                                {"uses": "actions/checkout@v4"},
                                {"name": "Example step", "run": "printf 'hello\\n'\n"},
                            ]
                        }
                    },
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        workspace = runtime.workspace_paths(self.sandbox_dir / "workspace")
        runtime.ensure_workspace_directories(workspace)
        rewritten_path = _rewrite_workflow(
            workspace=workspace,
            workflow_path=workflow_path,
            scenario_env={"SCENARIO_FLAG": "enabled"},
            bindings=ResolvedReleaseHarnessConfig(
                config_path=self.sandbox_dir / "release-harness.yaml",
                local_override_path=self.sandbox_dir / "release-harness.local.yaml",
                local_override_present=False,
                self_repository=ResolvedRepositoryBinding(
                    repository_id="apache/demo",
                    local_checkout_mode="when_repository_omitted",
                    local_path=self.sandbox_dir / "demo",
                ),
                repository_overrides={},
            ),
            real_cli_commands=set(),
            generated_gpg_fixture=False,
        )

        self.assertEqual(
            (
                "# WARNING: This is not the original workflow file.\n"
                "# This file was generated by buildish-release-harness for local test execution.\n"
                f"# Original workflow source: {workflow_path}\n"
                "# Verbatim original copy in this directory: workflow.original.yml\n"
                "name: Example\n"
                "on:\n"
                "  workflow_dispatch: {}\n"
                "jobs:\n"
                "  example:\n"
                "    steps:\n"
                "    - name: Harness bootstrap environment\n"
                "      shell: bash\n"
                "      run: |\n"
                '        mkdir -p "$GITHUB_WORKSPACE/.buildish-release-harness/job-statuses"\n'
                "        {\n"
                '          printf \'PATH=%s/.buildish-release-harness/shims:%s\\n\' "$GITHUB_WORKSPACE" "$PATH"\n'
                "          printf 'BUILDISH_HARNESS_STATE_FILE=%s/.buildish-release-harness/shim-state.json\\n' \"$GITHUB_WORKSPACE\"\n"
                "          printf 'BUILDISH_HARNESS_REAL_PATH=%s\\n' \"$PATH\"\n"
                "          printf 'BUILDISH_HARNESS_BASH_ENV_FILE=%s/.buildish-release-harness/bash-env.sh\\n' \"$GITHUB_WORKSPACE\"\n"
                "          printf 'BUILDISH_HARNESS_SUMMARIES_DIR=%s/.buildish-release-harness/summaries\\n' \"$GITHUB_WORKSPACE\"\n"
                "          printf 'BUILDISH_HARNESS_TOOLING_SOURCE_DIR=%s/.buildish-release-harness/repo-sources/apache__buildish-release-tooling\\n' \"$GITHUB_WORKSPACE\"\n"
                "          printf 'BUILDISH_ALLOW_NON_PRODUCTION_RELEASE_TARGETS=true\\n'\n"
                '          if [[ -n "${PYTHONPATH:-}" ]]; then\n'
                '            printf \'PYTHONPATH=%s/.buildish-release-harness/repo-sources/apache__buildish-release-tooling/src:%s\\n\' "$GITHUB_WORKSPACE" "$PYTHONPATH"\n'
                "          else\n"
                "            printf 'PYTHONPATH=%s/.buildish-release-harness/repo-sources/apache__buildish-release-tooling/src\\n' \"$GITHUB_WORKSPACE\"\n"
                "          fi\n"
                '        } >> "$GITHUB_ENV"\n'
                '        gpg_key_file="$GITHUB_WORKSPACE/.buildish-release-harness/gpg-fixture/private.asc"\n'
                '        if [[ -f "$gpg_key_file" ]]; then\n'
                "          {\n"
                "            printf 'BUILDISH_GPG_PRIVATE_KEY<<__BUILDISH_HARNESS_GPG_KEY__\\n'\n"
                '            cat "$gpg_key_file"\n'
                "            printf '__BUILDISH_HARNESS_GPG_KEY__\\n'\n"
                '          } >> "$GITHUB_ENV"\n'
                "        fi\n"
                "    - uses: ./.buildish-release-harness/actions/local-checkout\n"
                "      with:\n"
                "        source_path: .buildish-release-harness/repo-sources/apache__demo\n"
                "        path: .\n"
                "        ref: ''\n"
                "        mode: local-git-clone\n"
                "    - name: Example step\n"
                "      run: |\n"
                "        printf 'hello\\n'\n"
                "      env:\n"
                "        BUILDISH_HARNESS_JOB_ID: example\n"
                "        BUILDISH_HARNESS_STEP_ID: example-step\n"
                "    - name: Harness record job status\n"
                "      if: ${{ always() }}\n"
                "      shell: bash\n"
                "      env:\n"
                "        BUILDISH_HARNESS_JOB_STATUS: ${{ job.status }}\n"
                "      run: |\n"
                '        printf \'%s\\n\' "$BUILDISH_HARNESS_JOB_STATUS" > "$GITHUB_WORKSPACE/.buildish-release-harness/job-statuses/example.status"\n'
                "env:\n"
                "  SCENARIO_FLAG: enabled\n"
            ),
            rewritten_path.read_text(encoding="utf-8"),
        )

    def test_workflow_job_and_step_identifiers_must_be_path_safe(self) -> None:
        workflow_path = self.sandbox_dir / "workflow.yml"
        workflow_path.write_text(
            yaml.safe_dump(
                {
                    "name": "Example",
                    "on": {"workflow_dispatch": {}},
                    "jobs": {"../job": {"steps": []}},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "workflow job id"):
            _load_job_definitions(workflow_path)

        with self.assertRaisesRegex(ValueError, "workflow step id"):
            _step_identifier({"id": "../step", "run": "true"}, 1)

    def test_render_uv_shim_script_routes_selected_commands_to_real_cli(self) -> None:
        """The generated uv shim should route configured commands to the real CLI module."""

        script = _render_uv_shim_script(["create-release-branch", "verify-rc"])

        self.assertIn('case "$command_name" in', script)
        self.assertIn("create-release-branch|verify-rc)", script)
        self.assertIn(
            'if [[ "$command_name" == "--test-target-mode" ]]; then',
            script,
        )
        self.assertIn(
            'exec python3 -m buildish_release_tooling.release "$@"', script
        )
        self.assertIn(
            'exec python3 -m buildish_release_tooling.harness.shim_entrypoint buildish-release-tooling "${filtered_args[@]}"',
            script,
        )

    def test_generated_uv_shim_can_execute_create_release_branch_for_real(self) -> None:
        """The act uv shim should be able to invoke the real CLI entrypoint."""

        workflow = WorkflowScenario(
            path=str(self._workflow_path()),
            harness_config=str(
                component_root()
                / "buildish-release-tooling"
                / "harness"
                / "release-harness.yaml"
            ),
            real_cli_commands=["create-release-branch"],
        )
        workspace = runtime.workspace_paths(self.sandbox_dir / "workspace")
        runtime.ensure_workspace_directories(workspace)
        release_config = (
            component_root() / "buildish-release-tooling" / "release-config.yaml"
        )
        self._initialize_git_repository(workspace.root)
        (workspace.root / "buildish-release-tooling").mkdir(parents=True, exist_ok=True)
        (
            workspace.root / "buildish-release-tooling" / "release-config.yaml"
        ).write_text(
            release_config.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        uv_path = workspace.shims_dir / "uv"
        python_path = workspace.shims_dir / "python3"
        uv_path.write_text(
            _render_uv_shim_script(workflow.real_cli_commands),
            encoding="utf-8",
        )
        uv_path.chmod(0o755)
        python_path.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f'exec {json.dumps(os.fspath(Path(sys.executable)))} "$@"\n',
            encoding="utf-8",
        )
        python_path.chmod(0o755)

        env = cli_env(
            workspace.root / "manifest.json",
            extra_env={"PYTHONPATH": str(component_root() / "src")},
            prepend_dirs=(workspace.shims_dir,),
        )
        completed = subprocess.run(  # noqa: S603
            [
                str(uv_path),
                "run",
                "--project",
                str(component_root()),
                "--frozen",
                "buildish-release-tooling",
                "create-release-branch",
                "--test-target-mode",
                "--component-config",
                str(
                    workspace.root / "buildish-release-tooling" / "release-config.yaml"
                ),
                "--apply",
                "9.x",
                "main",
            ],
            cwd=str(workspace.root),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        branches = subprocess.run(  # noqa: S603
            ["git", "-C", str(workspace.root), "branch", "--list", "release/9.x"],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("release/9.x", branches.stdout)
        summary = (workspace.root / "manifest.summary.md").read_text(encoding="utf-8")
        self.assertIn("Create release branch", summary)
        self.assertIn("release/9.x <- main", summary)

    def _workflow_path(self) -> Path:
        """Return one checked-in workflow path used only to satisfy the scenario model."""

        return (
            component_root()
            / ".github"
            / "workflows"
            / "releasey-10-create-release-branch.yml"
        )

    def _initialize_git_repository(self, path: Path) -> None:
        """Create a disposable repository with a single `main` commit."""

        path.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init", "-b", "main", str(path)],
            check=True,
            text=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(path), "config", "user.name", "Buildish Harness"],
            check=True,
            text=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(path), "config", "user.email", "harness@example.test"],
            check=True,
            text=True,
            capture_output=True,
        )
        (path / "README.md").write_text("hello\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(path), "add", "README.md"],
            check=True,
            text=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(path), "commit", "-m", "initial"],
            check=True,
            text=True,
            capture_output=True,
        )
