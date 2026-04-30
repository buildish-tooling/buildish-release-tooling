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

"""Integration tests for reproducible source-artifact creation."""

from __future__ import annotations

import datetime as dt
import hashlib
import tarfile
import unittest

from apache_buildish_release_tooling.release.source_artifact import checksum, create_from_git, write_checksum_file

from tests.support import (
    cleanup_sandbox,
    create_build_test_sandbox,
    init_git_origin_and_clone,
    run_quiet,
)


class SourceArtifactIntegrationTest(unittest.TestCase):
    """Verify that source artifacts are reproducible across detached clones."""

    def test_source_artifact_is_reproducible_across_detached_clones(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_a = init_git_origin_and_clone(sandbox_dir)
        clone_b = sandbox_dir / "clone-b"
        docs_dir = origin_dir / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "README.md").write_text("alpha\n", encoding="utf-8")
        (origin_dir / "LICENSE.txt").write_text("beta\n", encoding="utf-8")
        run_quiet(["git", "-C", str(origin_dir), "add", "docs/README.md", "LICENSE.txt"], check=True)
        run_quiet(["git", "-C", str(origin_dir), "commit", "-m", "add archive content"], check=True)
        run_quiet(["git", "-C", str(clone_a), "pull", "--ff-only"], check=True)
        run_quiet(["git", "clone", str(origin_dir), str(clone_b)], check=True)
        commit = run_quiet(
            ["git", "-C", str(clone_a), "rev-parse", "HEAD"],
            check=True,
        )
        ref = commit.stdout.strip()
        artifact_a = sandbox_dir / "a.tar.gz"
        artifact_b = sandbox_dir / "b.tar.gz"
        create_from_git(
            clone_a,
            ref,
            "apache-buildish-example-1.2.3-incubating-src/",
            artifact_a,
        )
        create_from_git(
            clone_b,
            ref,
            "apache-buildish-example-1.2.3-incubating-src/",
            artifact_b,
        )
        self.assertEqual(artifact_a.read_bytes(), artifact_b.read_bytes())
        with tarfile.open(artifact_a, mode="r:gz") as archive:
            member_names = archive.getnames()
            self.assertIn("apache-buildish-example-1.2.3-incubating-src", member_names)
            self.assertIn(
                "apache-buildish-example-1.2.3-incubating-src/docs/README.md",
                member_names,
            )
            fixed_mtime = int(dt.datetime(1980, 2, 1, 0, 0, tzinfo=dt.UTC).timestamp())
            for member in archive.getmembers():
                self.assertEqual(fixed_mtime, member.mtime)

    def test_checksum_sidecar_generation_supports_sha256_and_sha512(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        artifact_path = sandbox_dir / "artifact.zip"
        artifact_path.write_bytes(b"payload\n")

        expected_sha256 = hashlib.sha256(b"payload\n").hexdigest()
        expected_sha512 = hashlib.sha512(b"payload\n").hexdigest()
        self.assertEqual(expected_sha256, checksum(artifact_path, "sha256"))
        self.assertEqual(expected_sha512, checksum(artifact_path, "sha512"))

        sha256_path = write_checksum_file(artifact_path, "sha256", expected_sha256)
        sha512_path = write_checksum_file(artifact_path, "sha512", expected_sha512)
        self.assertEqual(
            f"{expected_sha256}  artifact.zip\n",
            sha256_path.read_text(encoding="utf-8"),
        )
        self.assertEqual(
            f"{expected_sha512}  artifact.zip\n",
            sha512_path.read_text(encoding="utf-8"),
        )
