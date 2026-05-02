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

"""Unit tests for ATR JSON reader helpers."""

from __future__ import annotations

import unittest

from apache_buildish_release_tooling.release.commands.atr import _parse_json_output


class AtrJsonReaderTest(unittest.TestCase):
    """Keep ATR JSON response parsing fail-closed on malformed payloads."""

    def test_parse_json_output_rejects_non_object_payloads(self) -> None:
        malformed_payloads = (
            "[]",
            '"not-an-object"',
            "17",
            "null",
        )
        for payload in malformed_payloads:
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(
                    ValueError,
                    "atr release info did not return a JSON object payload",
                ):
                    _parse_json_output(payload, source="atr release info")
