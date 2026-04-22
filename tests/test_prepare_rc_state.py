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

"""Tests for pure prepare-RC naming helpers."""

from __future__ import annotations

import unittest

from apache_buildish_release_tooling.prepare_rc_state import (
    prepare_rc_source_artifact_name,
    prepare_rc_source_artifact_prefix_path,
    prepare_rc_source_artifact_root_name,
)


class PrepareRcStateTest(unittest.TestCase):
    """Verify source-artifact naming helpers used by RC workflows."""

    def test_prepare_rc_source_artifact_name(self) -> None:
        self.assertEqual(
            "apache-buildish-example-1.2.3-incubating-src.tar.gz",
            prepare_rc_source_artifact_name("apache-buildish-example", "1.2.3"),
        )

    def test_prepare_rc_source_artifact_root_name(self) -> None:
        self.assertEqual(
            "apache-buildish-example-1.2.3-incubating-src",
            prepare_rc_source_artifact_root_name("apache-buildish-example-1.2.3-incubating-src.tar.gz"),
        )

    def test_prepare_rc_source_artifact_prefix_path(self) -> None:
        self.assertEqual(
            "apache-buildish-example-1.2.3-incubating-src/",
            prepare_rc_source_artifact_prefix_path("apache-buildish-example-1.2.3-incubating-src.tar.gz"),
        )
