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

"""Unit tests for host-direct reproducibility rebuild helpers."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from buildish_release_tooling.release.command_logging import command_log_sink
from buildish_release_tooling.release.models import (
    ComponentConfig,
    VerifyRcBuildConfig,
    VerifyRcBuildOverrideConfig,
    VerifyRcOverrideConfig,
)
from buildish_release_tooling.release.verification.rebuild import (
    build_host_direct_environment,
    collect_profile_output_paths,
    decide_reproducibility_mode,
    resolve_effective_rebuild_profile,
    resolve_rebuild_profile,
    run_host_direct_profile,
    validate_rebuild_profile_overrides,
)


class VerificationRebuildTest(unittest.TestCase):
    """Coverage for reproducibility profile resolution and host-direct rebuild execution."""

    @staticmethod
    def _component_config_with_rebuild_profiles() -> ComponentConfig:
        return ComponentConfig.model_validate(
            {
                "component_id": "buildish-example",
                "source_artifact_prefix": "apache-buildish-example",
                "asf_dist_dev_base": "https://dist.apache.org/repos/dist/dev/incubator/buildish",
                "asf_dist_release_base": "https://downloads.apache.org/incubator/buildish",
                "asf_keys_url": "https://downloads.apache.org/incubator/buildish/KEYS",
                "moving_tags_enabled": True,
                "latest_tag_enabled": False,
                "secondary_targets": ["github-action"],
                "final_tag_mode": "rc-source-commit",
                "vote_release_name": "Buildish Example",
                "release_verification_guide_url": "https://example.invalid/release-verification",
                "verify_rc_instructions": "verify",
                "prepare_rc_runs_tests": False,
                "release_branch_ci_required": True,
                "verify_rc": {
                    "profiles": {
                        "bootstrap-zip": {
                            "kind": "generic-file",
                            "build": {
                                "command": ["./buildish-release-tooling/rebuild-bootstrap.sh"],
                                "working_dir": "subdir",
                                "env": {
                                    "CANONICAL_FLAG": "1",
                                    "SHARED_FLAG": "canonical",
                                },
                                "output_globs": ["dist/*.zip"],
                            },
                            "comparison": {
                                "mode": "exact-bytes",
                            },
                        },
                        "pypi-wheel": {
                            "kind": "python-distribution",
                            "build": {
                                "command": ["./buildish-release-tooling/rebuild-wheel.sh"],
                                "working_dir": "python-package",
                                "env": {"PYTHONHASHSEED": "0"},
                                "output_globs": ["python-package/dist/*.whl"],
                            },
                            "comparison": {
                                "mode": "exact-bytes",
                            },
                        },
                    }
                },
            }
        )

    def test_resolve_rebuild_profile_requires_matching_kind(self) -> None:
        component_config = ComponentConfig.model_validate(
            {
                "component_id": "buildish-example",
                "source_artifact_prefix": "apache-buildish-example",
                "asf_dist_dev_base": "https://dist.apache.org/repos/dist/dev/incubator/buildish",
                "asf_dist_release_base": "https://downloads.apache.org/incubator/buildish",
                "asf_keys_url": "https://downloads.apache.org/incubator/buildish/KEYS",
                "moving_tags_enabled": True,
                "latest_tag_enabled": False,
                "secondary_targets": ["github-action"],
                "final_tag_mode": "rc-source-commit",
                "vote_release_name": "Buildish Example",
                "release_verification_guide_url": "https://example.invalid/release-verification",
                "verify_rc_instructions": "verify",
                "prepare_rc_runs_tests": False,
                "release_branch_ci_required": True,
                "verify_rc": {
                    "profiles": {
                        "bootstrap-zip": {
                            "kind": "generic-file",
                            "build": {
                                "command": ["sh", "-c", "true"],
                                "output_globs": ["dist/*.zip"],
                            },
                            "comparison": {
                                "mode": "exact-bytes",
                            },
                        }
                    }
                },
            }
        )

        profile = resolve_rebuild_profile(
            component_config,
            "bootstrap-zip",
            expected_kinds=("generic-file", "generic-file-with-openpgp"),
        )
        self.assertEqual("generic-file", profile.kind)
        with self.assertRaisesRegex(ValueError, "incompatible kind"):
            resolve_rebuild_profile(
                component_config,
                "bootstrap-zip",
                expected_kinds=("python-distribution",),
            )

    def test_resolve_effective_rebuild_profile_merges_local_override(self) -> None:
        component_config = self._component_config_with_rebuild_profiles()
        profile_overrides = VerifyRcOverrideConfig.model_validate(
            {
                "profile_overrides": {
                    "bootstrap-zip": {
                        "build": {
                            "command": ["./buildish-release-tooling/rebuild-bootstrap-local.sh"],
                            "working_dir": ".",
                            "env": {"LOCAL_FLAG": "1"},
                            "output_globs": ["override-dist/*.zip"],
                        }
                    }
                }
            }
        )

        resolved = resolve_effective_rebuild_profile(
            component_config,
            "bootstrap-zip",
            expected_kinds=("generic-file",),
            profile_overrides=profile_overrides,
        )

        self.assertEqual("local-override", resolved.recipe_source)
        self.assertEqual(
            (
                "build.command",
                "build.working_dir",
                "build.env.LOCAL_FLAG",
                "build.output_globs",
            ),
            resolved.override_fields,
        )
        self.assertEqual(
            ["./buildish-release-tooling/rebuild-bootstrap-local.sh"],
            resolved.profile.build.command,
        )
        self.assertEqual(".", resolved.profile.build.working_dir)
        self.assertEqual("1", resolved.profile.build.env["CANONICAL_FLAG"])
        self.assertEqual("canonical", resolved.profile.build.env["SHARED_FLAG"])
        self.assertEqual("1", resolved.profile.build.env["LOCAL_FLAG"])
        self.assertEqual(["override-dist/*.zip"], resolved.profile.build.output_globs)

    def test_verify_rc_build_config_rejects_paths_that_escape_project_root(self) -> None:
        with self.assertRaisesRegex(ValueError, "working_dir must not escape"):
            VerifyRcBuildConfig.model_validate(
                {
                    "command": ["./buildish-release-tooling/rebuild.sh"],
                    "working_dir": "../outside",
                    "output_globs": ["dist/*.zip"],
                }
            )

        with self.assertRaisesRegex(ValueError, "output_globs must not escape"):
            VerifyRcBuildConfig.model_validate(
                {
                    "command": ["./buildish-release-tooling/rebuild.sh"],
                    "output_globs": ["../dist/*.zip"],
                }
            )

    def test_verify_rc_build_override_rejects_paths_that_escape_project_root(self) -> None:
        with self.assertRaisesRegex(ValueError, "working_dir must not escape"):
            VerifyRcBuildOverrideConfig.model_validate(
                {
                    "working_dir": "../outside",
                }
            )

        with self.assertRaisesRegex(ValueError, "output_globs must not escape"):
            VerifyRcBuildOverrideConfig.model_validate(
                {
                    "output_globs": ["../dist/*.zip"],
                }
            )

    def test_resolve_effective_rebuild_profile_inherits_omitted_fields_and_overrides_env_keys(self) -> None:
        component_config = self._component_config_with_rebuild_profiles()
        profile_overrides = VerifyRcOverrideConfig.model_validate(
            {
                "profile_overrides": {
                    "bootstrap-zip": {
                        "build": {
                            "env": {
                                "LOCAL_FLAG": "1",
                                "SHARED_FLAG": "local",
                            }
                        }
                    }
                }
            }
        )

        resolved = resolve_effective_rebuild_profile(
            component_config,
            "bootstrap-zip",
            expected_kinds=("generic-file",),
            profile_overrides=profile_overrides,
        )

        self.assertEqual("local-override", resolved.recipe_source)
        self.assertEqual(
            (
                "build.env.LOCAL_FLAG",
                "build.env.SHARED_FLAG",
            ),
            resolved.override_fields,
        )
        self.assertEqual(
            ["./buildish-release-tooling/rebuild-bootstrap.sh"],
            resolved.profile.build.command,
        )
        self.assertEqual("subdir", resolved.profile.build.working_dir)
        self.assertEqual(["dist/*.zip"], resolved.profile.build.output_globs)
        self.assertEqual("1", resolved.profile.build.env["CANONICAL_FLAG"])
        self.assertEqual("1", resolved.profile.build.env["LOCAL_FLAG"])
        self.assertEqual("local", resolved.profile.build.env["SHARED_FLAG"])

    def test_resolve_effective_rebuild_profile_multiple_profile_overrides_are_independent(self) -> None:
        component_config = self._component_config_with_rebuild_profiles()
        profile_overrides = VerifyRcOverrideConfig.model_validate(
            {
                "profile_overrides": {
                    "bootstrap-zip": {
                        "build": {
                            "command": ["./buildish-release-tooling/rebuild-bootstrap-local.sh"],
                        }
                    },
                    "pypi-wheel": {
                        "build": {
                            "working_dir": "override-python-package",
                            "output_globs": ["override-python-package/dist/*.whl"],
                        }
                    },
                }
            }
        )

        bootstrap_resolved = resolve_effective_rebuild_profile(
            component_config,
            "bootstrap-zip",
            expected_kinds=("generic-file",),
            profile_overrides=profile_overrides,
        )
        wheel_resolved = resolve_effective_rebuild_profile(
            component_config,
            "pypi-wheel",
            expected_kinds=("python-distribution",),
            profile_overrides=profile_overrides,
        )

        self.assertEqual(("build.command",), bootstrap_resolved.override_fields)
        self.assertEqual(
            ["./buildish-release-tooling/rebuild-bootstrap-local.sh"],
            bootstrap_resolved.profile.build.command,
        )
        self.assertEqual("subdir", bootstrap_resolved.profile.build.working_dir)
        self.assertEqual(
            (
                "build.working_dir",
                "build.output_globs",
            ),
            wheel_resolved.override_fields,
        )
        self.assertEqual(
            ["./buildish-release-tooling/rebuild-wheel.sh"],
            wheel_resolved.profile.build.command,
        )
        self.assertEqual("override-python-package", wheel_resolved.profile.build.working_dir)
        self.assertEqual(
            ["override-python-package/dist/*.whl"],
            wheel_resolved.profile.build.output_globs,
        )

    def test_validate_rebuild_profile_overrides_rejects_unknown_profile_id(self) -> None:
        component_config = ComponentConfig.model_validate(
            {
                "component_id": "buildish-example",
                "source_artifact_prefix": "apache-buildish-example",
                "asf_dist_dev_base": "https://dist.apache.org/repos/dist/dev/incubator/buildish",
                "asf_dist_release_base": "https://downloads.apache.org/incubator/buildish",
                "asf_keys_url": "https://downloads.apache.org/incubator/buildish/KEYS",
                "moving_tags_enabled": True,
                "latest_tag_enabled": False,
                "secondary_targets": ["github-action"],
                "final_tag_mode": "rc-source-commit",
                "vote_release_name": "Buildish Example",
                "release_verification_guide_url": "https://example.invalid/release-verification",
                "verify_rc_instructions": "verify",
                "prepare_rc_runs_tests": False,
                "release_branch_ci_required": True,
                "verify_rc": {
                    "profiles": {
                        "bootstrap-zip": {
                            "kind": "generic-file",
                            "build": {
                                "command": ["sh", "-c", "true"],
                                "output_globs": ["dist/*.zip"],
                            },
                            "comparison": {"mode": "exact-bytes"},
                        }
                    }
                },
            }
        )
        profile_overrides = VerifyRcOverrideConfig.model_validate(
            {
                "profile_overrides": {
                    "missing-profile": {
                        "build": {
                            "command": ["sh", "-c", "true"],
                        }
                    }
                }
            }
        )

        with self.assertRaisesRegex(ValueError, "unknown verify_rc profile_id"):
            validate_rebuild_profile_overrides(component_config, profile_overrides)

    def test_build_host_direct_environment_keeps_home_and_scrubs_sensitive_process_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            work_dir = Path(tmp_dir) / "work"
            project_root.mkdir()
            work_dir.mkdir()
            with patch.dict(
                os.environ,
                {
                    "PATH": "/usr/bin",
                    "HOME": "/home/tester",
                    "GITHUB_TOKEN": "secret-gh-token",
                    "AWS_SECRET_ACCESS_KEY": "secret-aws-key",
                    "JAVA_HOME": "/opt/java",
                },
                clear=True,
            ):
                environment, injected_environment_keys = build_host_direct_environment(
                    project_root=project_root,
                    work_dir=work_dir,
                    source_date_epoch=1714032000,
                    extra_env={"CUSTOM_BUILD_FLAG": "1"},
                )

            self.assertEqual("/home/tester", environment["HOME"])
            self.assertEqual("/opt/java", environment["JAVA_HOME"])
            self.assertEqual("1", environment["CUSTOM_BUILD_FLAG"])
            self.assertEqual(str(project_root), environment["BUILDISH_PROJECT_ROOT"])
            self.assertEqual(str(work_dir), environment["BUILDISH_WORK_DIR"])
            self.assertEqual("1714032000", environment["SOURCE_DATE_EPOCH"])
            self.assertEqual("1714032000", environment["BUILDISH_SOURCE_DATE_EPOCH"])
            self.assertEqual(str(work_dir / "tmp"), environment["TMPDIR"])
            self.assertNotIn("GITHUB_TOKEN", environment)
            self.assertNotIn("AWS_SECRET_ACCESS_KEY", environment)
            self.assertEqual(
                (
                    "BUILDISH_PROJECT_ROOT",
                    "BUILDISH_SOURCE_DATE_EPOCH",
                    "BUILDISH_WORK_DIR",
                    "CUSTOM_BUILD_FLAG",
                    "SOURCE_DATE_EPOCH",
                    "TMPDIR",
                ),
                injected_environment_keys,
            )

    def test_decide_reproducibility_mode_prompts_only_for_auto_interactive_candidates(self) -> None:
        declined = decide_reproducibility_mode(
            requested_mode="auto",
            has_build_candidates=True,
            is_interactive=True,
            confirm_callback=lambda: False,
        )
        self.assertEqual("integrity-only", declined.effective_mode)
        self.assertTrue(declined.prompt_used)
        self.assertFalse(cast(bool, declined.prompt_confirmed))
        self.assertFalse(declined.build_checks_allowed)

        confirmed = decide_reproducibility_mode(
            requested_mode="auto",
            has_build_candidates=True,
            is_interactive=True,
            confirm_callback=lambda: True,
        )
        self.assertEqual("full", confirmed.effective_mode)
        self.assertTrue(confirmed.prompt_used)
        self.assertTrue(cast(bool, confirmed.prompt_confirmed))
        self.assertTrue(confirmed.build_checks_allowed)

        non_interactive = decide_reproducibility_mode(
            requested_mode="auto",
            has_build_candidates=True,
            is_interactive=False,
        )
        self.assertEqual("integrity-only", non_interactive.effective_mode)
        self.assertFalse(non_interactive.prompt_used)
        self.assertIn("not interactive", cast(str, non_interactive.build_checks_skipped_reason))

    def test_run_host_direct_profile_uses_relative_working_dir_and_root_relative_output_globs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            project_root = temp_root / "project"
            script_dir = project_root / "subdir"
            work_dir = temp_root / "work"
            script_dir.mkdir(parents=True)
            work_dir.mkdir()

            component_config = ComponentConfig.model_validate(
                {
                    "component_id": "buildish-example",
                    "source_artifact_prefix": "apache-buildish-example",
                    "asf_dist_dev_base": "https://dist.apache.org/repos/dist/dev/incubator/buildish",
                    "asf_dist_release_base": "https://downloads.apache.org/incubator/buildish",
                    "asf_keys_url": "https://downloads.apache.org/incubator/buildish/KEYS",
                    "moving_tags_enabled": True,
                    "latest_tag_enabled": False,
                    "secondary_targets": ["github-action"],
                    "final_tag_mode": "rc-source-commit",
                    "vote_release_name": "Buildish Example",
                    "release_verification_guide_url": "https://example.invalid/release-verification",
                    "verify_rc_instructions": "verify",
                    "prepare_rc_runs_tests": False,
                    "release_branch_ci_required": True,
                    "verify_rc": {
                        "profiles": {
                            "bootstrap-zip": {
                                "kind": "generic-file",
                                "build": {
                                    "command": [
                                        "sh",
                                        "-c",
                                        "mkdir -p build && printf '%s\\n' \"$BUILDISH_PROJECT_ROOT\" > build/result.txt && env | sort > build/env.txt",
                                    ],
                                    "working_dir": "subdir",
                                    "env": {"CUSTOM_BUILD_FLAG": "1"},
                                    "output_globs": ["subdir/build/*.txt"],
                                },
                                "comparison": {
                                    "mode": "exact-bytes",
                                },
                            }
                        }
                    },
                }
            )
            self.assertIsNotNone(component_config.verify_rc)
            verify_rc = cast(Any, component_config.verify_rc)
            profile = verify_rc.profiles["bootstrap-zip"]

            with patch.dict(
                os.environ,
                {
                    "PATH": os.environ.get("PATH", ""),
                    "HOME": os.environ.get("HOME", str(temp_root)),
                    "GITHUB_TOKEN": "should-not-leak",
                },
                clear=True,
            ):
                with command_log_sink(io.StringIO(), echo_to_stderr=False):
                    result = run_host_direct_profile(
                        profile_id="bootstrap-zip",
                        profile=profile,
                        project_root=project_root,
                        work_dir=work_dir,
                        source_date_epoch=1714032000,
                    )

            self.assertEqual(project_root / "subdir", result.cwd)
            self.assertEqual(
                (
                    (project_root / "subdir" / "build" / "env.txt").resolve(),
                    (project_root / "subdir" / "build" / "result.txt").resolve(),
                ),
                result.output_paths,
            )
            self.assertEqual("1", result.environment["CUSTOM_BUILD_FLAG"])
            self.assertIn("SOURCE_DATE_EPOCH=1714032000", (project_root / "subdir" / "build" / "env.txt").read_text(encoding="utf-8"))
            self.assertIn(
                f"BUILDISH_PROJECT_ROOT={project_root}",
                (project_root / "subdir" / "build" / "env.txt").read_text(encoding="utf-8"),
            )
            self.assertNotIn(
                "GITHUB_TOKEN=should-not-leak",
                (project_root / "subdir" / "build" / "env.txt").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                f"{project_root}\n",
                (project_root / "subdir" / "build" / "result.txt").read_text(encoding="utf-8"),
            )

    def test_collect_profile_output_paths_ignores_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            (project_root / "dist").mkdir()
            (project_root / "dist" / "artifact.zip").write_text("zip bytes\n", encoding="utf-8")
            self.assertEqual(
                ((project_root / "dist" / "artifact.zip").resolve(),),
                collect_profile_output_paths(project_root, ("dist/*",)),
            )

    def test_collect_profile_output_paths_rejects_symlinked_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            (project_root / "dist").mkdir()
            outside_artifact = project_root / "outside.zip"
            outside_artifact.write_text("zip bytes\n", encoding="utf-8")
            symlink_path = project_root / "dist" / "artifact.zip"
            try:
                symlink_path.symlink_to(outside_artifact)
            except OSError as exc:
                self.skipTest(f"symlink creation is not supported: {exc}")

            with self.assertRaisesRegex(ValueError, "symlink"):
                collect_profile_output_paths(project_root, ("dist/*",))

    def test_collect_profile_output_paths_rejects_files_under_symlinked_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            project_root = temp_root / "project"
            outside_dir = temp_root / "outside"
            project_root.mkdir()
            outside_dir.mkdir()
            (outside_dir / "artifact.zip").write_text("zip bytes\n", encoding="utf-8")
            try:
                (project_root / "dist").symlink_to(outside_dir, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symlink creation is not supported: {exc}")

            with self.assertRaisesRegex(ValueError, "escape"):
                collect_profile_output_paths(project_root, ("dist/*",))


if __name__ == "__main__":
    unittest.main()
