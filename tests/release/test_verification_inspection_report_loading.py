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

"""Tests for inspect-repro report and bundle loading helpers."""

from __future__ import annotations

import unittest
from pathlib import Path

from buildish_release_tooling.release.verification.inspection.report_loading import (
    resolve_contained_relative_path,
)


class InspectionReportLoadingTest(unittest.TestCase):
    """Verify path containment helpers for retained inspection bundles."""

    def test_resolve_contained_relative_path_accepts_nested_relative_paths(self) -> None:
        root = Path.cwd() / "report-dir"

        self.assertEqual(
            root / "bundle" / "inspection-bundle.json",
            resolve_contained_relative_path(
                root,
                "bundle/inspection-bundle.json",
                field_name="inspection_bundle.manifest_relative_path",
            ),
        )

    def test_resolve_contained_relative_path_rejects_escapes(self) -> None:
        root = Path.cwd() / "report-dir"

        with self.assertRaisesRegex(ValueError, "relative and remain under"):
            resolve_contained_relative_path(
                root,
                "../bundle",
                field_name="inspection_bundle.relative_path_from_report",
            )

        with self.assertRaisesRegex(ValueError, "relative and remain under"):
            resolve_contained_relative_path(
                root,
                str(Path.cwd() / "bundle"),
                field_name="inspection_bundle.relative_path_from_report",
            )
