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

"""Tests for semantic-version release-state helpers."""

from __future__ import annotations

import unittest

from apache_buildish_release_tooling.release_state import (
    compare_versions,
    derive_specific_release_line,
    derive_moving_tags,
    highest_existing_rc_number_or_zero,
    is_version_in_release_line,
    latest_rc_tag_from_tags,
    next_rc_number_from_tags,
    published_versions_from_entries,
    resolve_release_branch,
    version_from_final_tag,
    versions_to_archive_for_line,
)


class ReleaseStateTest(unittest.TestCase):
    """Verify version- and branch-resolution helpers."""

    def test_resolve_release_branch_prefers_specific_branch(self) -> None:
        self.assertEqual(
            "release/1.2.x",
            resolve_release_branch("1.2.3", ["release/1.x", "release/1.2.x"]),
        )

    def test_highest_existing_rc_number_or_zero(self) -> None:
        self.assertEqual(
            2,
            highest_existing_rc_number_or_zero("1.2.3", ["v1.2.3-rc0", "v1.2.3-rc2", "v1.2.4-rc1"]),
        )

    def test_latest_rc_tag_from_tags(self) -> None:
        self.assertEqual(
            "v1.2.3-rc2", latest_rc_tag_from_tags("1.2.3", ["v1.2.3-rc0", "v1.2.3-rc2"])
        )

    def test_next_rc_number_from_tags(self) -> None:
        self.assertEqual(
            3,
            next_rc_number_from_tags("1.2.3", ["v1.2.3-rc0", "v1.2.3-rc2"]),
        )
        self.assertEqual(0, next_rc_number_from_tags("1.2.3", []))

    def test_derive_moving_tags(self) -> None:
        self.assertEqual(
            ["v1", "v1.2"],
            derive_moving_tags("1.2.3", ["github-action", "github-release"], True, False),
        )
        self.assertEqual(
            ["1", "1.2", "latest"],
            derive_moving_tags("1.2.3", ["dockerhub"], True, True),
        )

    def test_versions_to_archive_for_line(self) -> None:
        self.assertEqual(
            ["1.2.1", "1.2.3"],
            versions_to_archive_for_line("1.2.x", "1.2.4", ["1.1.9", "1.2.1", "1.2.3", "2.0.0"]),
        )

    def test_derive_specific_release_line(self) -> None:
        self.assertEqual("1.2.x", derive_specific_release_line("1.2.3"))

    def test_published_versions_from_entries(self) -> None:
        self.assertEqual(
            ["1.2.1", "1.2.3", "2.0.0"],
            published_versions_from_entries(["notes.txt", "2.0.0/", "1.2.3/", "1.2.1/"]),
        )

    def test_compare_versions(self) -> None:
        self.assertEqual(-1, compare_versions("1.2.3", "1.3.0"))
        self.assertEqual(0, compare_versions("1.2.3", "1.2.3"))
        self.assertEqual(1, compare_versions("1.3.0", "1.2.3"))

    def test_version_from_final_tag(self) -> None:
        self.assertEqual("1.2.3", version_from_final_tag("v1.2.3"))
        self.assertIsNone(version_from_final_tag("v1.2.3-rc0"))
        self.assertIsNone(version_from_final_tag("not-a-tag"))

    def test_is_version_in_release_line(self) -> None:
        self.assertTrue(is_version_in_release_line("1.x", "1.3.4"))
        self.assertTrue(is_version_in_release_line("1.2.x", "1.2.3"))
        self.assertFalse(is_version_in_release_line("1.2.x", "1.3.0"))
