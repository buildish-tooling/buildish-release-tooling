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
"""Shared support for artifact-registration command tests."""

from dataclasses import dataclass

from tests.release.commands.support import (
    Path,
    ReleaseCommandsIntegrationTestSupport,
    cleanup_sandbox,
    create_build_test_sandbox,
)


@dataclass(frozen=True)
class RecordArtifactCommandSandbox:
    """Standard paths used by one record-artifact command test."""

    root: Path
    config_path: Path
    manifest_path: Path
    github_output_path: Path


class ArtifactRegistrationCommandTestBase(ReleaseCommandsIntegrationTestSupport):
    """Shared assertions for artifact-registration command tests."""

    def _create_record_artifact_sandbox(self) -> RecordArtifactCommandSandbox:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        return RecordArtifactCommandSandbox(
            root=sandbox_dir,
            config_path=sandbox_dir / "component.yaml",
            manifest_path=sandbox_dir / "record-artifact.json",
            github_output_path=sandbox_dir / "record-artifact.outputs",
        )

    def _assert_secondary_artifact_entry_shape(
        self,
        payload: dict[str, object],
        *,
        expected_entry_keys: list[str],
    ) -> None:
        self.assertEqual(["secondary_artifacts"], list(payload))
        entries = payload["secondary_artifacts"]
        self.assertIsInstance(entries, list)
        if not isinstance(entries, list) or len(entries) != 1:
            self.fail("expected exactly one secondary artifact entry")
        entry = entries[0]
        self.assertIsInstance(entry, dict)
        if not isinstance(entry, dict):
            self.fail("secondary artifact entry must be a JSON object")
        self.assertEqual(expected_entry_keys, list(entry))
