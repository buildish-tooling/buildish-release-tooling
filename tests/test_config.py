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

"""Tests for component configuration loading."""

from __future__ import annotations

import unittest

from apache_buildish_release_tooling.release.config import load_component_config

from tests.support import cleanup_sandbox, create_build_test_sandbox, fixture_component_config_path


class LoadComponentConfigTest(unittest.TestCase):
    """Verify that YAML configuration loading behaves as expected."""

    def test_load_component_config_from_yaml(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "component_id: buildish-example",
                    "source_artifact_prefix: apache-buildish-example",
                    "asf_dist_dev_base: https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
                    "asf_dist_release_base: https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
                    "moving_tags_enabled: true",
                    "latest_tag_enabled: false",
                    "secondary_targets:",
                    "  - github-action",
                    "final_tag_mode: rc-source-commit",
                    "vote_release_name: Apache Buildish Example",
                    "release_verification_guide_url: https://buildish.apache.org/buildish-example/release-verification/",
                    "verify_rc_instructions: |",
                    "  verify",
                    "prepare_rc_runs_tests: false",
                    "release_branch_ci_required: true",
                    "atr:",
                    "  enabled: true",
                    "  base_url: https://release-test.apache.org",
                    "  committee: buildish",
                    "  product_line: buildish-example",
                    "  strict_checking: false",
                ]
            ),
            encoding="utf-8",
        )
        loaded = load_component_config(str(config_path))
        self.assertEqual("buildish-example", loaded.component_id)
        self.assertEqual(["github-action"], loaded.secondary_targets)
        self.assertEqual(
            "https://buildish.apache.org/buildish-example/release-verification/",
            loaded.release_verification_guide_url,
        )
        self.assertIsNotNone(loaded.atr)
        self.assertEqual("buildish-example", loaded.atr.product_line if loaded.atr is not None else None)

    def test_load_component_config_requires_explicit_yaml_path(self) -> None:
        with self.assertRaises(TypeError):
            load_component_config(None)  # type: ignore[arg-type]

    def test_load_component_config_rejects_incomplete_enabled_atr_config(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "component_id: buildish-example",
                    "source_artifact_prefix: apache-buildish-example",
                    "asf_dist_dev_base: https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
                    "asf_dist_release_base: https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
                    "moving_tags_enabled: true",
                    "latest_tag_enabled: false",
                    "secondary_targets:",
                    "  - github-action",
                    "final_tag_mode: rc-source-commit",
                    "vote_release_name: Apache Buildish Example",
                    "release_verification_guide_url: https://buildish.apache.org/buildish-example/release-verification/",
                    "verify_rc_instructions: verify",
                    "prepare_rc_runs_tests: false",
                    "release_branch_ci_required: true",
                    "atr:",
                    "  enabled: true",
                    "  base_url: https://release-test.apache.org",
                    "  committee: buildish",
                ]
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "product_line"):
            load_component_config(str(config_path))

    def test_load_checked_in_component_configs(self) -> None:
        expected_targets = {
            "buildish-mammoth-cache": ["github-action", "github-release"],
            "buildish-no-gradle-wrapper-jar": ["github-release-assets"],
            "buildish-site-pipeline": ["pypi", "dockerhub"],
        }
        expected_final_tag_modes = {
            "buildish-mammoth-cache": "detached-materialization-commit",
            "buildish-no-gradle-wrapper-jar": "rc-source-commit",
            "buildish-site-pipeline": "rc-source-commit",
        }

        for component_id, secondary_targets in expected_targets.items():
            with self.subTest(component=component_id):
                loaded = load_component_config(str(fixture_component_config_path(component_id)))
                self.assertEqual(component_id, loaded.component_id)
                self.assertEqual(secondary_targets, loaded.secondary_targets)
                self.assertEqual(expected_final_tag_modes[component_id], loaded.final_tag_mode)
                self.assertTrue(loaded.release_branch_ci_required)
