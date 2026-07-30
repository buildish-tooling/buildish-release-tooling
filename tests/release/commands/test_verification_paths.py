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

"""Tests for verify-rc output path naming helpers."""

from __future__ import annotations

import unittest

from buildish_release_tooling.release.commands.verification import _report_base_name


class VerificationPathTest(unittest.TestCase):
    """Verify default report names cannot include path separators."""

    def test_report_base_name_sanitizes_manifest_identifiers(self) -> None:
        self.assertEqual(
            "verify-rc-report-component-escape-v1.2.3-rc0",
            _report_base_name("component/../escape", "1.2.3", "v1.2.3/rc0"),
        )


if __name__ == "__main__":
    unittest.main()
