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

"""Tests for GitHub summary rendering."""

from __future__ import annotations

import os
import unittest

from buildish_release_tooling.release.summary import SummaryWriter

from tests.support import cleanup_sandbox, create_build_test_sandbox


class SummaryWriterTest(unittest.TestCase):
    """Verify summary file rendering for headings, checksums, and signatures."""

    def test_summary_blocks(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        summary_path = sandbox_dir / "summary.md"
        signature_path = sandbox_dir / "source.asc"
        signature_path.write_text(
            "\n".join(
                [
                    "-----BEGIN PGP SIGNATURE-----",
                    "draft-signature",
                    "-----END PGP SIGNATURE-----",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        writer = SummaryWriter(summary_path)
        writer.append_heading("Release Candidate")
        writer.append_sha512_block(
            "apache-example-project-1.2.3-incubating-src.tar.gz",
            "abc123",
        )
        writer.append_checksum_block(
            "sha256",
            "apache-example-project-1.2.3-incubating-src.tar.gz",
            "def456",
        )
        writer.append_signature_block(
            "apache-example-project-1.2.3-incubating-src.tar.gz",
            signature_path,
        )
        writer.append_key_value_table(
            "Technical details",
            [
                ("Version", "`1.2.3`"),
                ("Repository", "`apache/example-project`"),
            ],
        )
        writer.append_bullet_list("Mirror assets", ["`rc-vote-manifest.json`", "`rc-vote-manifest.json.asc`"])
        writer.append_json_block("Manifest", {"version": "1.2.3", "rc_tag": "v1.2.3-rc0"})
        content = summary_path.read_text(encoding="utf-8")
        self.assertIn("## Release Candidate", content)
        self.assertIn("abc123  apache-example-project-1.2.3-incubating-src.tar.gz", content)
        self.assertIn("def456  apache-example-project-1.2.3-incubating-src.tar.gz", content)
        self.assertIn("-----BEGIN PGP SIGNATURE-----", content)
        self.assertIn("| Field | Value |", content)
        self.assertIn("- `rc-vote-manifest.json`", content)
        self.assertIn('"rc_tag": "v1.2.3-rc0"', content)

    def test_from_environment_requires_github_step_summary(self) -> None:
        original_env = dict(os.environ)
        def restore_env() -> None:
            os.environ.clear()
            os.environ.update(original_env)

        self.addCleanup(restore_env)
        os.environ.pop("GITHUB_STEP_SUMMARY", None)
        with self.assertRaisesRegex(ValueError, "GITHUB_STEP_SUMMARY is required"):
            SummaryWriter.from_environment()
