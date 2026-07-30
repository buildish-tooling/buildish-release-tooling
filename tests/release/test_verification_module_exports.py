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

"""Regression coverage for verification-module compatibility wrappers."""

from __future__ import annotations

import unittest

from buildish_release_tooling.release.verification import inspect_repro
from buildish_release_tooling.release.verification.inspection import (
    inspect_repro_report,
    inspect_repro_report_json,
)


class VerificationModuleExportsTest(unittest.TestCase):
    """Keep recently split verification module import surfaces stable."""

    def test_inspect_repro_wrapper_reexports_current_functions(self) -> None:
        self.assertIs(inspect_repro.inspect_repro_report, inspect_repro_report)
        self.assertIs(inspect_repro.inspect_repro_report_json, inspect_repro_report_json)

    def test_inspect_repro_wrapper_declares_expected_public_exports(self) -> None:
        self.assertEqual(
            ["inspect_repro_report", "inspect_repro_report_json"],
            inspect_repro.__all__,
        )
