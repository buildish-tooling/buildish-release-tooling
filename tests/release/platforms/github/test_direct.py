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
                logical_name="buildish-example-1.2.3.zip",
                digests={"sha256": hashlib.sha256(artifact_bytes).hexdigest()},
                size_bytes=len(artifact_bytes),
            )
        )
    return DirectReleaseState(
        release=ReleaseIdentity(
            component=ComponentIdentity(
                id="buildish-example",
                display_name="Buildish Example",
            ),
            version="1.2.3",
        ),
        source=SourceRevision(
            repository="https://github.com/buildish-tooling/buildish-example.git",
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
        "name": "Buildish Example 1.2.3",
        "body": render_direct_final_release_body(state),
        "draft": draft,
        "prerelease": False,
        "html_url": (
            "https://github.com/buildish-tooling/buildish-example/"
            "releases/tag/v1.2.3"
        ),
        "assets": assets or [],
    }


class DirectGitHubReleaseTest(unittest.TestCase):
    """Verify exact local and remote asset identity checks."""

    def test_release_without_assets_is_exact(self) -> None:
        state = _state()

        publication = validate_final_release(
            state,
            "buildish-tooling/buildish-example",
            _release_payload(state),
            expected_body=render_direct_final_release_body(state),
        )

        self.assertEqual([], publication.assets)
        self.assertTrue(publication.draft)

    def test_local_and_remote_asset_bytes_must_match_state(self) -> None:
        artifact_bytes = b"release asset\n"
        state = _state(artifact_bytes=artifact_bytes)
        digest = hashlib.sha256(artifact_bytes).hexdigest()
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "buildish-example-1.2.3.zip"
            asset_path.write_bytes(artifact_bytes)
            self.assertEqual(
                [asset_path],
                validate_local_release_assets(state, [asset_path]),
            )

        publication = validate_final_release(
            state,
            "buildish-tooling/buildish-example",
            _release_payload(
                state,
                assets=[
                    {
                        "id": 101,
                        "name": "buildish-example-1.2.3.zip",
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
            ["buildish-example-1.2.3.zip"],
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
                    "name": "buildish-example-1.2.3.zip",
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
                "buildish-tooling/buildish-example",
                payload,
                expected_body=render_direct_final_release_body(state),
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
                "buildish-tooling/buildish-example",
                payload,
                expected_body=render_direct_final_release_body(state),
            )


if __name__ == "__main__":
    unittest.main()
