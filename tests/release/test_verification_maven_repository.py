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

"""Unit tests for Maven repository reproducibility helpers."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from apache_buildish_release_tooling.release.artifact_registration.kinds.maven_repository import (
    _RepositoryFile,
)
from apache_buildish_release_tooling.release.progress import ProgressReporter
from apache_buildish_release_tooling.release.verification.secondary.maven_repository_repro import (
    compare_maven_repository_trees,
)


class MavenRepositoryReproducibilityTest(unittest.TestCase):
    """Keep Maven repository local comparison scoped to staged paths."""

    def test_compare_maven_repository_trees_ignores_unrelated_local_files_and_skips_sidecars_by_default(
        self,
    ) -> None:
        with TemporaryDirectory() as temp_dir:
            rebuilt_root = (
                Path(temp_dir)
                / "m2repo"
                / "org"
                / "example"
                / "app"
                / "1.0.0"
            )
            rebuilt_root.mkdir(parents=True, exist_ok=True)
            rebuilt_pom_path = rebuilt_root / "app-1.0.0.pom"
            rebuilt_pom_path.write_text("<project>stable</project>\n", encoding="utf-8")
            extra_local_path = (
                Path(temp_dir)
                / "m2repo"
                / "com"
                / "example"
                / "dependency"
                / "2.0.0"
                / "dependency-2.0.0.jar"
            )
            extra_local_path.parent.mkdir(parents=True, exist_ok=True)
            extra_local_path.write_bytes(b"dependency bytes\n")

            staged_pom_payload = b"<project>stable</project>\n"
            staged_signature_payload = b"signature bytes\n"
            staged_sidecar_payload = (("0" * 128) + "  app-1.0.0.pom\n").encode("utf-8")
            path_results, issues, matches = compare_maven_repository_trees(
                artifact_id="maven-staging-main",
                staged_by_path={
                    "org/example/app/1.0.0/app-1.0.0.pom": _RepositoryFile(
                        relative_path="org/example/app/1.0.0/app-1.0.0.pom",
                        size_bytes=len(staged_pom_payload),
                        source_url="https://example.invalid/org/example/app/1.0.0/app-1.0.0.pom",
                    ),
                    "org/example/app/1.0.0/app-1.0.0.pom.asc": _RepositoryFile(
                        relative_path="org/example/app/1.0.0/app-1.0.0.pom.asc",
                        size_bytes=len(staged_signature_payload),
                        source_url="https://example.invalid/org/example/app/1.0.0/app-1.0.0.pom.asc",
                    ),
                    "org/example/app/1.0.0/app-1.0.0.pom.sha512": _RepositoryFile(
                        relative_path="org/example/app/1.0.0/app-1.0.0.pom.sha512",
                        size_bytes=len(staged_sidecar_payload),
                        source_url="https://example.invalid/org/example/app/1.0.0/app-1.0.0.pom.sha512",
                    ),
                },
                staged_cache={
                    "org/example/app/1.0.0/app-1.0.0.pom": staged_pom_payload,
                    "org/example/app/1.0.0/app-1.0.0.pom.asc": staged_signature_payload,
                    "org/example/app/1.0.0/app-1.0.0.pom.sha512": staged_sidecar_payload,
                },
                rebuilt_repository_path=Path(temp_dir) / "m2repo",
                path_rules=(),
                require_signatures=False,
                progress_reporter=ProgressReporter(
                    enabled=False,
                    color_enabled=False,
                    stream=StringIO(),
                ),
            )

        self.assertTrue(matches)
        self.assertEqual([], issues)
        self.assertEqual(
            {
                "org/example/app/1.0.0/app-1.0.0.pom",
                "org/example/app/1.0.0/app-1.0.0.pom.asc",
                "org/example/app/1.0.0/app-1.0.0.pom.sha512",
            },
            {result.path for result in path_results},
        )
        self.assertEqual(
            {"org/example/app/1.0.0/app-1.0.0.pom.asc", "org/example/app/1.0.0/app-1.0.0.pom.sha512"},
            {
                result.path
                for result in path_results
                if result.verdict == "skipped"
            },
        )
        self.assertNotIn(
            "com/example/dependency/2.0.0/dependency-2.0.0.jar",
            {result.path for result in path_results},
        )
