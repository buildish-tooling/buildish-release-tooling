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

"""Tests for manifest emission."""

from __future__ import annotations

import json
import unittest

from apache_buildish_release_tooling.release.command_manifests import CreateReleaseBranchManifest
from apache_buildish_release_tooling.release.manifest import write_manifest

from tests.support import cleanup_sandbox, create_build_test_sandbox


class ManifestTest(unittest.TestCase):
    """Verify that typed workflow manifests are written as JSON objects."""

    def test_write_manifest(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        manifest_path = sandbox_dir / "release.json"
        write_manifest(
            manifest_path,
            CreateReleaseBranchManifest(
                component="buildish-mammoth-cache",
                release_line="1.2.x",
                release_branch="release/1.2.x",
                source_ref="deadbeef",
            ),
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("buildish-mammoth-cache", manifest["component"])
        self.assertEqual("create-release-branch", manifest["action"])
        self.assertEqual("1.2.x", manifest["release_line"])
        self.assertEqual("release/1.2.x", manifest["release_branch"])
        self.assertEqual("deadbeef", manifest["source_ref"])
