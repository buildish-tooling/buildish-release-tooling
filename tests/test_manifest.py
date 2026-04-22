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

from apache_buildish_release_tooling.manifest import write_manifest

from tests.support import cleanup_sandbox, create_build_test_sandbox


class ManifestTest(unittest.TestCase):
    """Verify that workflow manifests are written as flat JSON objects."""

    def test_write_manifest(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        manifest_path = sandbox_dir / "release.json"
        write_manifest(
            manifest_path,
            {
                "component": "buildish-mammoth-cache",
                "version": "1.2.3",
                "rc_tag": "v1.2.3-rc0",
            },
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("buildish-mammoth-cache", manifest["component"])
        self.assertEqual("1.2.3", manifest["version"])
        self.assertEqual("v1.2.3-rc0", manifest["rc_tag"])
