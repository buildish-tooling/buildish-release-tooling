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
"""RC vote-manifest publication verification tests."""

from __future__ import annotations

import unittest

from apache_buildish_release_tooling.release.models import (
    CommandContext,
    ComponentConfig,
)
from apache_buildish_release_tooling.release.rc_vote_verification import (
    verified_mirrored_rc_vote_manifest,
)


class RcVotePublicationVerificationTest(unittest.TestCase):
    """Tests for publication-time RC vote-manifest verification."""

    def test_verified_mirrored_rc_vote_manifest_rejects_missing_sha512_asset(
        self,
    ) -> None:
        context = CommandContext(
            component_config=ComponentConfig(
                component_id="buildish-example",
                source_artifact_prefix="apache-buildish-example",
                asf_dist_dev_base="https://dist.apache.org/repos/dist/dev/buildish-example",
                asf_dist_release_base="https://dist.apache.org/repos/dist/release/buildish-example",
                asf_keys_url="https://dist.apache.org/repos/dist/release/KEYS",
                moving_tags_enabled=True,
                latest_tag_enabled=False,
                secondary_targets=[],
                final_tag_mode="rc-source-commit",
                vote_release_name="Apache Buildish Example",
                release_verification_guide_url="https://example.invalid/verify",
                verify_rc_instructions="verify",
                prepare_rc_runs_tests=True,
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "draft GitHub Release is missing mirrored asset: rc-vote-manifest.json.sha512",
        ):
            verified_mirrored_rc_vote_manifest(
                context,
                repository_slug="apache/buildish-example",
                release_payload={
                    "assets": [
                        {"id": 201, "name": "rc-vote-manifest.json"},
                        {"id": 202, "name": "rc-vote-manifest.json.asc"},
                    ]
                },
                allow_non_production_release_targets=False,
            )


if __name__ == "__main__":
    unittest.main()
