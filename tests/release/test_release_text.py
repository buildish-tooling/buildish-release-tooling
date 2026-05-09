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
"""Tests for shared release communication text blocks."""

from __future__ import annotations

import unittest

from apache_buildish_release_tooling.release.models import ComponentConfig
from apache_buildish_release_tooling.release.release_text import (
    incubator_disclaimer_section,
    incubator_disclaimer_text,
)


class ReleaseTextTest(unittest.TestCase):
    """Verify policy text rendering from component configuration."""

    @staticmethod
    def _component_config(**overrides: object) -> ComponentConfig:
        payload: dict[str, object] = {
            "component_id": "buildish-example",
            "source_artifact_prefix": "apache-buildish-example",
            "asf_dist_dev_base": "https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            "asf_dist_release_base": "https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
            "asf_keys_url": "https://downloads.apache.org/incubator/buildish/KEYS",
            "moving_tags_enabled": True,
            "latest_tag_enabled": False,
            "secondary_targets": ["github-action"],
            "final_tag_mode": "rc-source-commit",
            "vote_release_name": "Apache Buildish Example",
            "project_status": "incubating",
            "release_summary_include_final_tag_mode": False,
            "release_verification_guide_url": "https://buildish.apache.org/buildish-example/release-verification/",
            "verify_rc_instructions": "verify",
            "prepare_rc_runs_tests": False,
            "release_branch_ci_required": True,
        }
        payload.update(overrides)
        return ComponentConfig.model_validate(payload)

    def test_default_incubator_disclaimer_uses_project_name_and_sponsor(self) -> None:
        component_config = self._component_config()

        disclaimer = incubator_disclaimer_text(component_config)

        self.assertIn("Apache Buildish Example is an effort undergoing incubation", disclaimer)
        self.assertIn("sponsored by Apache Incubator", disclaimer)
        self.assertIn("yet to be fully endorsed by the ASF", disclaimer)

    def test_custom_incubator_disclaimer_overrides_default(self) -> None:
        component_config = self._component_config(
            incubator_disclaimer="Custom approved disclaimer.\n",
        )

        self.assertEqual("Custom approved disclaimer.", incubator_disclaimer_text(component_config))

    def test_empty_incubator_disclaimer_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "incubator_disclaimer"):
            self._component_config(incubator_disclaimer=" \n")

    def test_incubator_disclaimer_section_is_empty_for_top_level_projects(self) -> None:
        component_config = self._component_config(project_status="tlp")

        self.assertEqual("", incubator_disclaimer_section(component_config, heading="Disclaimer:"))


if __name__ == "__main__":
    unittest.main()
