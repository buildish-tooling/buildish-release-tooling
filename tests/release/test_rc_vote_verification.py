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
"""RC vote-manifest publication verification tests."""

from __future__ import annotations

import unittest

from buildish_release_tooling.release.config import CommandContext, ReleaseConfig
from buildish_release_tooling.release.rc_vote_verification import (
    verified_mirrored_rc_vote_manifest,
)


class RcVotePublicationVerificationTest(unittest.TestCase):
    """Tests for publication-time RC vote-manifest verification."""

    def test_verified_mirrored_rc_vote_manifest_rejects_missing_sha512_asset(
        self,
    ) -> None:
        context = CommandContext(
            release_config=ReleaseConfig.model_validate(
                {
                    "component": {
                        "id": "buildish-example",
                        "display_name": "Buildish Example",
                    },
                    "source": {
                        "selection": "release-branch",
                        "snapshot": {
                            "mode": "built-asset",
                            "filename_template": "buildish-example-{version}-src.tar.gz",
                            "archive_root_template": "buildish-example-{version}-src",
                        },
                        "checks": {
                            "run_selected_ref_tests": True,
                            "require_release_branch_ci": False,
                        },
                    },
                    "lifecycle": {"mode": "candidate"},
                    "candidate": {},
                    "publication": {
                        "authoritative": {"kind": "asf-dist-svn"},
                    },
                    "vote_materials": {
                        "profile": "asf",
                        "release_name": "Buildish Example",
                        "verification_guide_url": "https://example.invalid/verify",
                        "instructions": "verify",
                    },
                    "policy_profiles": {
                        "asf": {
                            "dist_dev_base": "https://dist.apache.org/repos/dist/dev/buildish-example",
                            "dist_release_base": "https://dist.apache.org/repos/dist/release/buildish-example",
                            "keys_url": "https://dist.apache.org/repos/dist/release/KEYS",
                        }
                    },
                }
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "draft GitHub Release is missing mirrored asset: rc-vote-manifest.json.sha512",
        ):
            verified_mirrored_rc_vote_manifest(
                context,
                repository_slug="buildish-tooling/buildish-example",
                release_payload={
                    "assets": [
                        {"id": 201, "name": "rc-vote-manifest.json"},
                        {"id": 202, "name": "rc-vote-manifest.json.asc"},
                    ]
                },
                test_target_mode=False,
            )


if __name__ == "__main__":
    unittest.main()
