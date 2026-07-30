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

"""Tests for pure prepare-RC naming helpers."""

from __future__ import annotations

import unittest
from typing import cast

from buildish_release_tooling.release.models import ComponentConfig
from buildish_release_tooling.release.prepare_rc_state import (
    prepare_rc_source_artifact_name,
    prepare_rc_source_artifact_prefix_path,
    prepare_rc_source_artifact_root_name,
    resolve_prepare_rc_state,
)
from buildish_release_tooling.release.git_repo import GitRepository


class PrepareRcStateTest(unittest.TestCase):
    """Verify source-artifact naming helpers used by RC workflows."""

    @staticmethod
    def _component_config() -> ComponentConfig:
        return ComponentConfig.model_validate(
            {
                "component_id": "buildish-example",
                "source_artifact_prefix": "apache-buildish-example",
                "asf_dist_dev_base": "https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
                "asf_dist_release_base": "https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
                "asf_keys_url": "https://downloads.apache.org/incubator/buildish/KEYS",
                "moving_tags_enabled": True,
                "latest_tag_enabled": False,
                "secondary_targets": ["github-action"],
                "final_tag_mode": "rc-source-commit",
                "vote_release_name": "Buildish Example",
                "release_verification_guide_url": "https://buildish.org/buildish-example/release-verification/",
                "verify_rc_instructions": "verify",
                "prepare_rc_runs_tests": False,
                "release_branch_ci_required": True,
            }
        )

    def test_prepare_rc_source_artifact_name(self) -> None:
        self.assertEqual(
            "apache-buildish-example-1.2.3-incubating-src.tar.gz",
            prepare_rc_source_artifact_name("apache-buildish-example", "1.2.3"),
        )

    def test_prepare_rc_source_artifact_root_name(self) -> None:
        self.assertEqual(
            "apache-buildish-example-1.2.3-incubating-src",
            prepare_rc_source_artifact_root_name("apache-buildish-example-1.2.3-incubating-src.tar.gz"),
        )

    def test_prepare_rc_source_artifact_prefix_path(self) -> None:
        self.assertEqual(
            "apache-buildish-example-1.2.3-incubating-src/",
            prepare_rc_source_artifact_prefix_path("apache-buildish-example-1.2.3-incubating-src.tar.gz"),
        )

    def test_resolve_prepare_rc_state_rejects_invalid_version_even_with_explicit_source_sha(self) -> None:
        class DummyRepo:
            def resolve_release_branch_for_version(self, version: str) -> str:
                raise AssertionError("version validation should fail before branch resolution")

            def resolve_commit(self, ref: str) -> str:
                raise AssertionError("version validation should fail before commit resolution")

        with self.assertRaisesRegex(ValueError, "invalid version"):
            resolve_prepare_rc_state(
                cast(GitRepository, DummyRepo()),
                self._component_config(),
                "/../../../../tmp/poc",
                "0123456789abcdef0123456789abcdef01234567",
            )
