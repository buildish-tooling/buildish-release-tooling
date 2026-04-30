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

"""Tests for RC vote-manifest helpers."""

from __future__ import annotations

import hashlib
import unittest
from typing import Any, cast
from unittest import mock

from apache_buildish_release_tooling.release.models import ComponentConfig, PrepareRcState
from apache_buildish_release_tooling.release.rc_vote_manifest import (
    build_rc_vote_manifest,
    derive_asf_keys_uri,
    trust_root_metadata,
)

from tests.support import cleanup_sandbox, create_build_test_sandbox


class RcVoteManifestTest(unittest.TestCase):
    """Verify RC vote-manifest construction and trust-root derivation."""

    def test_derive_asf_keys_uri_translates_release_dist_to_downloads(self) -> None:
        self.assertEqual(
            "https://downloads.apache.org/incubator/buildish/KEYS",
            derive_asf_keys_uri(
                "https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example"
            ),
        )

    def test_trust_root_metadata_reads_local_file_uri(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        keys_path = sandbox_dir / "KEYS"
        keys_payload = b"test-key\n"
        keys_path.write_bytes(keys_payload)
        metadata = trust_root_metadata(keys_path.as_uri())
        asf_keys = cast(dict[str, Any], metadata["asf_keys"])
        self.assertEqual(f"{keys_path.as_uri()}", asf_keys["uri"])
        self.assertEqual(len(keys_payload), asf_keys["known_length_bytes"])
        self.assertEqual(
            hashlib.sha512(keys_payload).hexdigest(),
            asf_keys["known_prefix_sha512"],
        )

    def test_build_rc_vote_manifest_emits_expected_shape(self) -> None:
        component_config = ComponentConfig.model_validate(
            {
                "component_id": "buildish-example",
                "source_artifact_prefix": "apache-buildish-example",
                "asf_dist_dev_base": "https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
                "asf_dist_release_base": "https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
                "asf_keys_url": "https://downloads.apache.org/incubator/buildish/KEYS",
                "moving_tags_enabled": True,
                "latest_tag_enabled": False,
                "secondary_targets": ["github-action"],
                "final_tag_mode": "detached-materialization-commit",
                "vote_release_name": "Apache Buildish Example",
                "release_verification_guide_url": "https://buildish.apache.org/buildish-example/release-verification/",
                "verify_rc_instructions": "verify",
                "prepare_rc_runs_tests": False,
                "release_branch_ci_required": True,
                "verify_rc": {
                    "source": {
                        "reproducibility": {
                            "profile_id": "source-release",
                            "mode": "exact-bytes",
                        }
                    },
                    "profiles": {
                        "source-release": {
                            "kind": "source-artifact",
                            "build": {
                                "command": ["./buildish-release-tooling/rebuild-source.sh"],
                                "output_globs": ["target/apache-example-*.tar.gz"],
                            },
                            "comparison": {
                                "mode": "exact-bytes",
                            },
                        }
                    },
                },
            }
        )
        state = PrepareRcState.model_validate(
            {
                "resolved_release_branch": "release/1.2.x",
                "resolved_source_ref": "0123456789abcdef0123456789abcdef01234567",
                "source_date_epoch": 1714032000,
                "rc_number": 2,
                "rc_tag": "v1.2.3-rc2",
                "final_tag": "v1.2.3",
                "source_artifact_name": "apache-buildish-example-1.2.3-incubating-src.tar.gz",
                "source_artifact_root_name": "apache-buildish-example-1.2.3-incubating-src",
                "source_artifact_prefix_path": "apache-buildish-example-1.2.3-incubating-src/",
                "staging_url": "https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example/1.2.3-rc2/",
            }
        )
        with (
            mock.patch(
                "apache_buildish_release_tooling.release.rc_vote_manifest.tooling_provenance",
                return_value={
                    "repository": "apache/buildish-release-tooling",
                    "repository_url": "https://github.com/apache/buildish-release-tooling",
                    "git_commit_sha": "fedcba9876543210fedcba9876543210fedcba98",
                    "git_ref": "refs/heads/main",
                },
            ),
            mock.patch(
                "apache_buildish_release_tooling.release.rc_vote_manifest.github_workflow_provenance",
                return_value={
                    "repository": "apache/buildish-example",
                    "workflow": "Releasey Prepare RC",
                    "workflow_ref": "apache/buildish-example/.github/workflows/releasey-20-prepare-rc.yml@refs/heads/main",
                    "run_id": 42,
                    "run_attempt": 1,
                    "run_url": "https://github.com/apache/buildish-example/actions/runs/42",
                },
            ),
            mock.patch(
                "apache_buildish_release_tooling.release.rc_vote_manifest.trust_root_metadata",
                return_value={
                    "asf_keys": {
                        "uri": "https://downloads.apache.org/incubator/buildish/KEYS",
                        "known_length_bytes": 9,
                        "known_prefix_sha512": "a" * 128,
                    }
                },
            ),
            mock.patch(
                "apache_buildish_release_tooling.release.rc_vote_manifest.created_at_utc",
                return_value="2026-04-23T10:15:30Z",
            ),
        ):
            manifest = build_rc_vote_manifest(
                component_config=component_config,
                state=state,
                repository_slug="apache/buildish-example",
                source_repository_url="https://github.com/apache/buildish-example",
                draft_release_tag="v1.2.3-rc2",
                draft_release_url="https://github.com/apache/buildish-example/releases/tag/v1.2.3-rc2",
                rc_tag_target_commit="89abcdef0123456789abcdef0123456789abcdef",
                source_artifact_sha512="b" * 128,
                secondary_artifacts=[
                    {
                        "artifact_id": "bootstrap-zip",
                        "kind": "generic-file",
                        "role": "bootstrap-convenience-archive",
                        "filename": "buildish-example-bootstrap.zip",
                        "uri": "https://github.com/apache/buildish-example/releases/download/v1.2.3/buildish-example-bootstrap.zip",
                        "artifact_origin": "source-commit",
                        "git_commit_sha": "0123456789abcdef0123456789abcdef01234567",
                        "reproducibility": {
                            "profile_id": "bootstrap-zip",
                        },
                        "checksums": {
                            "sha512": {
                                "value": "c" * 128,
                                "uri": "https://github.com/apache/buildish-example/releases/download/v1.2.3/buildish-example-bootstrap.zip.sha512",
                            }
                        },
                        "signatures": [],
                    }
                ],
            )
        self.assertEqual("rc-vote", manifest.manifest_type)
        self.assertEqual("1.2.x", manifest.release_line)
        self.assertEqual(
            "89abcdef0123456789abcdef0123456789abcdef",
            manifest.materialized_commit_sha,
        )
        self.assertEqual(
            "https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example/1.2.3-rc2/apache-buildish-example-1.2.3-incubating-src.tar.gz",
            manifest.vote_materials.source_artifacts[0].uri,
        )
        source_reproducibility = manifest.vote_materials.source_artifacts[0].reproducibility
        self.assertIsNotNone(source_reproducibility)
        self.assertEqual(
            "source-release",
            cast(Any, source_reproducibility).profile_id,
        )
        self.assertEqual(
            "https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example/1.2.3-rc2/rc-vote-manifest.json",
            manifest.verification.authoritative_manifest.uri,
        )
        self.assertEqual(
            "https://github.com/apache/buildish-example/releases/tag/v1.2.3-rc2",
            manifest.draft_github_release.url,
        )
        self.assertEqual(
            "https://github.com/apache/buildish-example",
            manifest.source_repository_url,
        )
        self.assertEqual(1714032000, manifest.source_date_epoch)
        self.assertEqual("v1.2.3-rc2", manifest.draft_github_release.tag)
        secondary_artifact = cast(Any, manifest.vote_materials.secondary_artifacts[0])
        self.assertEqual(
            "bootstrap-zip",
            cast(Any, secondary_artifact.reproducibility).profile_id,
        )
        self.assertEqual(
            "https://github.com/apache/buildish-example/releases/download/v1.2.3/buildish-example-bootstrap.zip",
            secondary_artifact.uri,
        )
