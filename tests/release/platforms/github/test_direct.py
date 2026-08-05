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

"""Unit tests for exact direct GitHub final-release validation."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from buildish_release_tooling.release.core.models import (
    ArtifactReference,
    ComponentIdentity,
    ReleaseIdentity,
    SourceRevision,
    TagIdentity,
)
from buildish_release_tooling.release.core.state import DirectReleaseState
from buildish_release_tooling.release.platforms.github.direct import (
    missing_final_release_assets,
    validate_final_release,
    validate_local_release_assets,
)
from buildish_release_tooling.release.platforms.github.text import (
    render_direct_final_release_body,
)


def _state(*, artifact_bytes: bytes | None = None) -> DirectReleaseState:
    commit = "0123456789abcdef0123456789abcdef01234567"
    artifacts = []
    if artifact_bytes is not None:
        artifacts.append(
            ArtifactReference(
                kind="generic-file",
                logical_name="example-project-1.2.3.zip",
                digests={"sha256": hashlib.sha256(artifact_bytes).hexdigest()},
                size_bytes=len(artifact_bytes),
            )
        )
    return DirectReleaseState(
        release=ReleaseIdentity(
            component=ComponentIdentity(
                id="example-project",
                display_name="Apache Example Project",
            ),
            version="1.2.3",
        ),
        source=SourceRevision(
            repository="https://github.com/apache/example-project.git",
            commit_sha=commit,
            source_ref="main",
        ),
        final_tag=TagIdentity(
            name="v1.2.3",
            target_commit=commit,
            purpose="final",
        ),
        artifacts=artifacts,
    )


def _release_payload(
    state: DirectReleaseState,
    *,
    draft: bool = True,
    assets: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "id": 42,
        "tag_name": state.final_tag.name,
        "name": "Apache Example Project 1.2.3",
        "body": render_direct_final_release_body(state),
        "draft": draft,
        "prerelease": False,
        "html_url": ("https://github.com/apache/example-project/releases/tag/v1.2.3"),
        "created_at": "2026-08-05T09:00:00Z",
        "published_at": None if draft else "2026-08-05T09:05:00Z",
        "assets": assets or [],
    }


class DirectGitHubReleaseTest(unittest.TestCase):
    """Verify exact local and remote asset identity checks."""

    def test_release_without_assets_is_exact(self) -> None:
        state = _state()

        publication = validate_final_release(
            state,
            "apache/example-project",
            _release_payload(state),
            expected_body=render_direct_final_release_body(state),
        )

        self.assertEqual([], publication.assets)
        self.assertTrue(publication.draft)
        self.assertIsNone(publication.published_at)

    def test_published_release_requires_publication_timestamp(self) -> None:
        state = _state()
        payload = _release_payload(state, draft=False)
        payload.pop("published_at")

        with self.assertRaisesRegex(ValueError, "publication timestamp"):
            validate_final_release(
                state,
                "apache/example-project",
                payload,
                expected_body=render_direct_final_release_body(state),
            )

    def test_local_and_remote_asset_bytes_must_match_state(self) -> None:
        artifact_bytes = b"release asset\n"
        state = _state(artifact_bytes=artifact_bytes)
        digest = hashlib.sha256(artifact_bytes).hexdigest()
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "example-project-1.2.3.zip"
            asset_path.write_bytes(artifact_bytes)
            self.assertEqual(
                [asset_path],
                validate_local_release_assets(state, [asset_path]),
            )

        publication = validate_final_release(
            state,
            "apache/example-project",
            _release_payload(
                state,
                assets=[
                    {
                        "id": 101,
                        "name": "example-project-1.2.3.zip",
                        "size": len(artifact_bytes),
                        "digest": f"sha256:{digest}",
                    }
                ],
            ),
            expected_body=render_direct_final_release_body(state),
        )

        self.assertEqual(f"sha256:{digest}", publication.assets[0].digest)

    def test_missing_assets_are_reported_but_drift_is_rejected(self) -> None:
        artifact_bytes = b"release asset\n"
        state = _state(artifact_bytes=artifact_bytes)
        body = render_direct_final_release_body(state)
        self.assertEqual(
            ["example-project-1.2.3.zip"],
            missing_final_release_assets(
                state,
                _release_payload(state),
                expected_body=body,
            ),
        )

        drifted = _release_payload(
            state,
            assets=[
                {
                    "id": 101,
                    "name": "example-project-1.2.3.zip",
                    "size": len(artifact_bytes) + 1,
                    "digest": f"sha256:{hashlib.sha256(artifact_bytes).hexdigest()}",
                }
            ],
        )
        with self.assertRaisesRegex(ValueError, "asset size mismatch"):
            missing_final_release_assets(state, drifted, expected_body=body)

    def test_unexpected_remote_asset_is_rejected(self) -> None:
        state = _state()
        payload = _release_payload(
            state,
            assets=[
                {
                    "id": 101,
                    "name": "unexpected.txt",
                    "size": 1,
                    "digest": f"sha256:{'a' * 64}",
                }
            ],
        )

        with self.assertRaisesRegex(ValueError, "unexpected=\\['unexpected.txt'\\]"):
            validate_final_release(
                state,
                "apache/example-project",
                payload,
                expected_body=render_direct_final_release_body(state),
            )

    def test_reserved_orphan_evidence_is_tolerated_only_for_recovery(self) -> None:
        state = _state()
        evidence_name = (
            "buildish-verification-evidence--example.whl.publish-attestations.json"
        )
        payload = _release_payload(
            state,
            assets=[
                {
                    "id": 101,
                    "name": evidence_name,
                    "size": 1,
                    "digest": f"sha256:{'a' * 64}",
                }
            ],
        )

        with self.assertRaisesRegex(ValueError, "unexpected"):
            validate_final_release(
                state,
                "apache/example-project",
                payload,
                expected_body=render_direct_final_release_body(state),
            )
        publication = validate_final_release(
            state,
            "apache/example-project",
            payload,
            expected_body=render_direct_final_release_body(state),
            recoverable_orphan_assets={evidence_name},
        )
        self.assertEqual([], publication.assets)
        self.assertEqual(
            [],
            missing_final_release_assets(
                state,
                payload,
                expected_body=render_direct_final_release_body(state),
                recoverable_orphan_assets={evidence_name},
            ),
        )

        unrelated = _release_payload(
            state,
            assets=[
                {
                    "id": 102,
                    "name": "buildish-verification-evidence--unrelated.json",
                    "size": 1,
                    "digest": f"sha256:{'b' * 64}",
                }
            ],
        )
        with self.assertRaisesRegex(ValueError, "unexpected"):
            validate_final_release(
                state,
                "apache/example-project",
                unrelated,
                expected_body=render_direct_final_release_body(state),
                recoverable_orphan_assets={evidence_name},
            )

        ordinary_state = state.model_copy(
            update={
                "artifacts": [
                    ArtifactReference(
                        kind="generic-file",
                        logical_name=evidence_name,
                        digests={"sha256": "c" * 64},
                        size_bytes=2,
                    )
                ]
            }
        )
        ordinary_payload = _release_payload(
            ordinary_state,
            assets=[
                {
                    "id": 103,
                    "name": evidence_name,
                    "size": 1,
                    "digest": f"sha256:{'a' * 64}",
                }
            ],
        )
        with self.assertRaisesRegex(ValueError, "asset size mismatch"):
            validate_final_release(
                ordinary_state,
                "apache/example-project",
                ordinary_payload,
                expected_body=render_direct_final_release_body(ordinary_state),
                recoverable_orphan_assets={evidence_name},
            )

    def test_malformed_remote_asset_metadata_is_rejected(self) -> None:
        state = _state()
        payload = _release_payload(
            state,
            assets=[{"id": "not-an-integer", "name": "unexpected.txt"}],
        )

        with self.assertRaisesRegex(ValueError, "malformed asset metadata"):
            validate_final_release(
                state,
                "apache/example-project",
                payload,
                expected_body=render_direct_final_release_body(state),
            )


if __name__ == "__main__":
    unittest.main()
