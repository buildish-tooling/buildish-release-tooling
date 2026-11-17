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

"""Exercise generated-content commands from an installed local development wheel."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import unittest
from pathlib import Path

from tests.release.materialization_support import generated_action_commit
from tests.support import init_git_origin_and_clone, set_github_origin_url


class InstalledMaterializationTest(unittest.TestCase):
    def test_installed_wheel_binds_and_imports_without_an_undeclared_source_checkout(
        self,
    ) -> None:
        root = Path(__file__).resolve().parents[1]
        uv = shutil.which("uv")
        if uv is None:
            self.skipTest("uv is required for wheel installation checks")
        with tempfile.TemporaryDirectory(dir=root / "build") as temporary:
            sandbox = Path(temporary)
            env = {
                **os.environ,
                "UV_PYTHON_DOWNLOADS": "never",
                "GITHUB_STEP_SUMMARY": str(sandbox / "summary.md"),
                "GITHUB_OUTPUT": str(sandbox / "outputs"),
            }
            env.pop("PYTHONPATH", None)

            def run(
                argv: list[str],
                *,
                cwd: Path = sandbox,
                extra_env: dict[str, str] | None = None,
            ) -> subprocess.CompletedProcess[str]:
                result = subprocess.run(
                    argv,
                    cwd=cwd,
                    env={**env, **(extra_env or {})},
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                return result

            source_copy = sandbox / "build-source"
            shutil.copytree(
                root,
                source_copy,
                ignore=shutil.ignore_patterns(
                    ".git",
                    ".agents",
                    "build",
                    "dist",
                    ".venv",
                    "*.egg-info",
                    "__pycache__",
                    ".pytest_cache",
                    ".mypy_cache",
                    ".ruff_cache",
                ),
            )
            run(
                [
                    uv,
                    "build",
                    "--wheel",
                    "--no-build-logs",
                    "--no-create-gitignore",
                    "--out-dir",
                    str(sandbox / "wheels"),
                    str(source_copy),
                ]
            )
            wheel = next((sandbox / "wheels").glob("*.whl"))
            venv = sandbox / "installed"
            # Install only our wheel. Reuse installed dependency files through an explicit
            # disposable path entry; do not process the parent environment's editable .pth files.
            run(
                [
                    uv,
                    "venv",
                    "--python",
                    sys.executable,
                    str(venv),
                ]
            )
            python = venv / "bin/python"
            run(
                [
                    uv,
                    "pip",
                    "install",
                    "--no-cache",
                    "--python",
                    str(python),
                    "--no-index",
                    "--no-deps",
                    str(wheel),
                ]
            )
            site_packages = run(
                [
                    str(python),
                    "-I",
                    "-c",
                    "import sysconfig; print(sysconfig.get_paths()['purelib'])",
                ]
            ).stdout.strip()
            (Path(site_packages) / "test-runtime-dependencies.pth").write_text(
                sysconfig.get_paths()["purelib"] + "\n"
            )
            origin = run(
                [
                    str(python),
                    "-I",
                    "-c",
                    "import buildish_release_tooling.release.materialized_content as module; print(module.__file__)",
                ]
            ).stdout.strip()
            self.assertTrue(Path(origin).is_relative_to(venv), origin)
            origin_dir, producer = init_git_origin_and_clone(sandbox / "git")
            set_github_origin_url(producer, "example/materialized")
            config = sandbox / "config.json"
            config.write_text(
                json.dumps(
                    {
                        "component": {"id": "example", "display_name": "Example"},
                        "source": {
                            "selection": "explicit-ref",
                            "snapshot": {"mode": "none"},
                        },
                        "lifecycle": {"mode": "direct"},
                        "publication": {
                            "authoritative": {
                                "kind": "github-release",
                                "repository": "example/materialized",
                            }
                        },
                        "tags": {
                            "final_mode": "detached-materialization-commit",
                            "materialized_paths": ["dist"],
                        },
                    }
                )
            )

            def cli(action: str, *args: str, cwd: Path = producer) -> Path:
                output = sandbox / f"{action}.json"
                run(
                    [
                        str(venv / "bin/buildish-release-tooling"),
                        action,
                        "--component-config",
                        str(config),
                        *args,
                    ],
                    cwd=cwd,
                    extra_env={"MANIFEST_PATH": str(output)},
                )
                return output

            state = cli("resolve-direct-release", "1.2.3", "main")
            source = json.loads(state.read_text())["source"]["commit_sha"]
            commit = generated_action_commit(producer, source)
            bundle = sandbox / "materialized.bundle"
            bound = cli(
                "bind-materialization",
                "--release-state",
                str(state),
                "--materialized-commit",
                commit,
                "--bundle-output",
                str(bundle),
            )
            consumer = sandbox / "trusted"
            run(
                [
                    "git",
                    "clone",
                    "--depth=1",
                    "--no-tags",
                    origin_dir.as_uri(),
                    str(consumer),
                ]
            )
            bundle_digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
            imported = cli(
                "import-materialization",
                "--release-state",
                str(bound),
                "--source-state",
                str(state),
                "--bundle",
                str(bundle),
                "--bundle-sha256",
                bundle_digest,
                cwd=consumer,
            )
            payload = json.loads(imported.read_text())
            self.assertEqual(source, payload["source"]["commit_sha"])
            self.assertEqual(commit, payload["final_tag"]["target_commit"])
            self.assertEqual(commit, payload["materialization"]["commit_sha"])
            self.assertEqual(
                source, run(["git", "rev-parse", "HEAD"], cwd=consumer).stdout.strip()
            )
            self.assertFalse((consumer / "dist").exists())
