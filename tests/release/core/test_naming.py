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

"""Tests for provider-neutral release naming and candidate resolution."""

from __future__ import annotations

import unittest
from typing import cast

from buildish_release_tooling.release.config import ReleaseConfig
from buildish_release_tooling.release.core.naming import (
    render_release_name_template,
)
from buildish_release_tooling.release.git_repo import GitRepository
from buildish_release_tooling.release.prepare_rc_state import resolve_prepare_rc_state


class ReleaseNamingTest(unittest.TestCase):
    """Verify template-driven names and candidate resolution validation."""

    @staticmethod
    def _component_config() -> ReleaseConfig:
        return ReleaseConfig.model_validate(
            {
                "component": {
                    "id": "example-project",
                    "display_name": "Apache Example Project",
                },
                "source": {
                    "selection": "release-branch",
                    "snapshot": {
                        "mode": "built-asset",
                        "filename_template": "apache-example-project-{version}-incubating-src.tar.gz",
                        "archive_root_template": "apache-example-project-{version}-incubating-src",
                    },
                    "checks": {"platform": "github", "required": ["component-ci"]},
                },
                "lifecycle": {"mode": "candidate"},
                "candidate": {"start_number": 1},
                "publication": {
                    "authoritative": {"kind": "asf-dist-svn"},
                    "secondary": [{"kind": "github-action"}],
                },
                "tags": {
                    "final_mode": "exact-source-commit",
                    "moving": ["major", "minor"],
                },
                "vote_materials": {
                    "profile": "asf",
                    "release_name": "Apache Example Project",
                    "verification_guide_url": "https://example.apache.org/release-verification/",
                    "instructions": "verify",
                },
                "policy_profiles": {
                    "asf": {
                        "dist_dev_base": "https://dist.apache.org/repos/dist/dev/incubator/example/example-project",
                        "dist_release_base": "https://dist.apache.org/repos/dist/release/incubator/example/example-project",
                        "keys_url": "https://downloads.apache.org/incubator/example/KEYS",
                    }
                },
            }
        )

    def test_generic_source_artifact_name_has_no_implicit_incubating_marker(self) -> None:
        self.assertEqual(
            "example-project-1.2.3-src.tar.gz",
            render_release_name_template(
                "{component}-{version}-src.tar.gz",
                component="example-project",
                version="1.2.3",
                field_name="source artifact filename",
            ),
        )

    def test_foundation_policy_can_select_incubating_marker_explicitly(self) -> None:
        self.assertEqual(
            "apache-example-project-1.2.3-incubating-src",
            render_release_name_template(
                "apache-{component}-{version}-incubating-src",
                component="example-project",
                version="1.2.3",
                field_name="source artifact archive root",
            ),
        )

    def test_rendered_name_must_not_escape_as_a_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "simple file name"):
            render_release_name_template(
                "../{component}-{version}.tar.gz",
                component="example-project",
                version="1.2.3",
                field_name="source artifact filename",
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
