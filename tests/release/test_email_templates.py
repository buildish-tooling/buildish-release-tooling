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

"""Unit tests for ASF-style email template rendering."""

from __future__ import annotations

import unittest

from apache_buildish_release_tooling.release.email_templates import (
    render_announce_email,
    render_incubator_rc_vote_email,
    render_project_rc_vote_email,
    render_project_vote_result_email,
)
from apache_buildish_release_tooling.release.models import ComponentConfig, PrepareRcState


class EmailTemplatesTest(unittest.TestCase):
    """Verify the built-in email templates render the expected ASF-style content."""

    @staticmethod
    def _component_config(*, incubator_vote_enabled: bool) -> ComponentConfig:
        """Return a reusable component config for template tests."""

        return ComponentConfig.model_validate(
            {
                "component_id": "buildish-example",
                "source_artifact_prefix": "apache-buildish-example",
                "asf_dist_dev_base": "https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
                "asf_dist_release_base": "https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
                "moving_tags_enabled": True,
                "latest_tag_enabled": False,
                "secondary_targets": ["github-action", "github-release"],
                "final_tag_mode": "detached-materialization-commit",
                "vote_release_name": "Apache Buildish Example",
                "incubator_vote_enabled": incubator_vote_enabled,
                "release_summary_include_final_tag_mode": False,
                "release_verification_guide_url": "https://buildish.apache.org/buildish-example/release-verification/",
                "verify_rc_instructions": "verify",
                "prepare_rc_runs_tests": False,
                "release_branch_ci_required": True,
            }
        )

    @staticmethod
    def _prepare_rc_state() -> PrepareRcState:
        """Return a reusable resolved RC state for template tests."""

        return PrepareRcState.model_validate(
            {
                "resolved_release_branch": "release/1.2.x",
                "resolved_source_ref": "0123456789abcdef0123456789abcdef01234567",
                "rc_number": 2,
                "rc_tag": "v1.2.3-rc2",
                "final_tag": "v1.2.3",
                "source_artifact_name": "apache-buildish-example-1.2.3-incubating-src.tar.gz",
                "source_artifact_root_name": "apache-buildish-example-1.2.3-incubating-src",
                "source_artifact_prefix_path": "apache-buildish-example-1.2.3-incubating-src/",
                "staging_url": "https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example/1.2.3-rc2/",
            }
        )

    @staticmethod
    def _manifest_payload() -> dict[str, object]:
        """Return a reusable RC vote-manifest payload for template tests."""

        return {
            "trust_roots": {
                "asf_keys": {
                    "uri": "https://downloads.apache.org/incubator/buildish/KEYS",
                }
            },
            "vote_materials": {
                "source_artifacts": [
                    {
                        "filename": "apache-buildish-example-1.2.3-incubating-src.tar.gz",
                        "uri": "https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example/1.2.3-rc2/apache-buildish-example-1.2.3-incubating-src.tar.gz",
                        "checksums": {
                            "sha512": {
                                "value": "abc123",
                                "uri": "https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example/1.2.3-rc2/apache-buildish-example-1.2.3-incubating-src.tar.gz.sha512",
                            }
                        },
                        "signatures": [
                            {
                                "uri": "https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example/1.2.3-rc2/apache-buildish-example-1.2.3-incubating-src.tar.gz.asc",
                            }
                        ],
                    }
                ],
                "secondary_artifacts": [
                    {
                        "filename": "buildish-example.zip",
                        "uri": "https://github.com/apache/buildish-example/releases/download/v1.2.3/buildish-example.zip",
                        "checksums": {
                            "sha512": {
                                "value": "def456",
                                "uri": "https://github.com/apache/buildish-example/releases/download/v1.2.3/buildish-example.zip.sha512",
                            }
                        },
                        "signatures": [],
                    }
                ],
            },
            "verification": {
                "authoritative_manifest": {
                    "uri": "https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example/1.2.3-rc2/rc-vote-manifest.json",
                    "checksum_uris": {
                        "sha512": "https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example/1.2.3-rc2/rc-vote-manifest.json.sha512",
                    },
                    "signatures": [
                        {
                            "uri": "https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example/1.2.3-rc2/rc-vote-manifest.json.asc",
                        }
                    ],
                }
            },
        }

    def test_render_project_rc_vote_email_includes_rc_inventory_and_verification_guide(self) -> None:
        component_config = self._component_config(incubator_vote_enabled=True)
        state = self._prepare_rc_state()
        rendered = render_project_rc_vote_email(
            component_config=component_config,
            state=state,
            rc_tag_target_commit="89abcdef0123456789abcdef0123456789abcdef",
            manifest_payload=self._manifest_payload(),
            draft_release_url="https://github.com/apache/buildish-example/releases/tag/v1.2.3",
        )
        self.assertEqual(
            "[VOTE] Release Apache Buildish Example 1.2.3-incubating (RC2)",
            rendered.subject,
        )
        self.assertIn("I propose that we release the following RC", rendered.body)
        self.assertIn("Git tag: v1.2.3-rc2", rendered.body)
        self.assertIn("Source commit SHA: 0123456789abcdef0123456789abcdef01234567", rendered.body)
        self.assertIn("https://downloads.apache.org/incubator/buildish/KEYS", rendered.body)
        self.assertIn("https://buildish.apache.org/buildish-example/release-verification/", rendered.body)
        self.assertIn("buildish-example.zip", rendered.body)

    def test_render_incubator_rc_vote_email_uses_thread_placeholders(self) -> None:
        rendered = render_incubator_rc_vote_email(
            component_config=self._component_config(incubator_vote_enabled=True),
            state=self._prepare_rc_state(),
            manifest_payload=self._manifest_payload(),
        )
        self.assertEqual(
            "[VOTE] Release Apache Buildish Example 1.2.3-incubating (RC2)",
            rendered.subject,
        )
        self.assertIn("<TODO: add the project vote thread URL>", rendered.body)
        self.assertIn("<TODO: add the project vote result thread URL>", rendered.body)
        self.assertIn("Only IPMC members have binding votes", rendered.body)

    def test_render_project_vote_result_email_emits_human_fill_placeholders(self) -> None:
        rendered = render_project_vote_result_email(
            component_config=self._component_config(incubator_vote_enabled=False),
            version="1.2.3",
            rc_number=2,
        )
        self.assertEqual(
            "[RESULT][VOTE] Release Apache Buildish Example 1.2.3 (RC2)",
            rendered.subject,
        )
        self.assertIn("<TODO: binding count>", rendered.body)
        self.assertIn("We will proceed with publishing the approved artifacts", rendered.body)

    def test_render_announce_email_uses_human_fill_placeholder(self) -> None:
        rendered = render_announce_email(
            component_config=self._component_config(incubator_vote_enabled=False),
            version="1.2.3",
        )
        self.assertEqual("[ANNOUNCE] Apache Buildish Example 1.2.3", rendered.subject)
        self.assertIn("The Apache Buildish Example team is pleased to announce", rendered.body)
        self.assertIn("<TODO: add release-specific announcement content>", rendered.body)
