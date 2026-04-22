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

"""Unit tests for ATR JSON reader helpers."""

from __future__ import annotations

import stat
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from buildish_release_tooling.release.commands.atr import (
    AtrRuntimeConfig,
    _atr_host_from_base_url,
    _parse_json_output,
    _run_atr_command,
    _write_atr_client_config,
)


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

    def test_atr_base_url_requires_https_url(self) -> None:
        self.assertEqual("release.apache.org", _atr_host_from_base_url("https://release.apache.org"))
        with self.assertRaisesRegex(ValueError, "https://"):
            _atr_host_from_base_url("http://release.apache.org")
        with self.assertRaisesRegex(ValueError, "https://"):
            _atr_host_from_base_url("release.apache.org")

    def test_write_atr_client_config_uses_private_file_mode(self) -> None:
        runtime = AtrRuntimeConfig(
            base_url="https://release.apache.org",
            host="release.apache.org",
            committee="example",
            project_key="example-project",
            asf_uid="tester",
            pat="secret-pat",
            strict_checking=True,
        )
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "atr.yaml"

            _write_atr_client_config(config_path, runtime)

            self.assertEqual(0o600, stat.S_IMODE(config_path.stat().st_mode))
            self.assertIn("secret-pat", config_path.read_text(encoding="utf-8"))

    def test_run_atr_command_redacts_pat(self) -> None:
        runtime = AtrRuntimeConfig(
            base_url="https://release.apache.org",
            host="release.apache.org",
            committee="example",
            project_key="example-project",
            asf_uid="tester",
            pat="secret-pat",
            strict_checking=True,
        )
        with mock.patch(
            "buildish_release_tooling.release.commands.atr.run_logged_command"
        ) as run_logged_command:
            _run_atr_command(runtime, ["atr", "release", "info"], env={"ATR_CLIENT_CONFIG_PATH": "atr.yaml"})

        self.assertEqual(["secret-pat"], run_logged_command.call_args.kwargs["extra_secret_values"])
