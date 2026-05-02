# Copyright 2026 The Apache Software Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for committed harness repository-binding config."""

from __future__ import annotations

import json
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

import yaml

from apache_buildish_release_tooling.harness.cli import main as harness_main
from apache_buildish_release_tooling.harness.config import (
    default_local_override_path,
    load_release_harness_config,
    repository_root_for_config,
)
from tests.support import cleanup_sandbox, create_build_test_sandbox


class ReleaseHarnessConfigTest(unittest.TestCase):
    """Coverage for `buildish-release-tooling/harness/release-harness.yaml` resolution."""

    sandbox_dir: Path

    def setUp(self) -> None:
        """Create a disposable sandbox for one config test."""

        self.sandbox_dir = create_build_test_sandbox()

    def tearDown(self) -> None:
        """Remove the disposable sandbox after each config test."""

        cleanup_sandbox(self.sandbox_dir)

    def _write_yaml(self, path: Path, payload: dict[str, object]) -> None:
        """Write one YAML mapping fixture."""

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    def test_defaults_resolve_to_sibling_repository_paths(self) -> None:
        """Committed config should resolve missing local paths to `../<repo-name>`."""

        repo_root = self.sandbox_dir / "buildish-mammoth-cache"
        harness_dir = repo_root / "buildish-release-tooling" / "harness"
        harness_dir.mkdir(parents=True)
        config_path = harness_dir / "release-harness.yaml"
        self._write_yaml(
            config_path,
            {
                "schema_version": "1",
                "self_repository": {
                    "repository_id": "apache/buildish-mammoth-cache",
                },
                "repository_overrides": {
                    "apache/buildish-release-tooling": {
                        "local_checkout_mode": "always",
                    }
                },
            },
        )

        resolved = load_release_harness_config(config_path)

        self.assertEqual(repo_root, resolved.self_repository.local_path)
        self.assertEqual(
            repo_root.parent / "buildish-release-tooling",
            resolved.repository_overrides["apache/buildish-release-tooling"].local_path,
        )
        self.assertFalse(resolved.local_override_present)
        self.assertEqual(config_path.with_name("release-harness.local.yaml"), resolved.local_override_path)

    def test_local_override_file_replaces_default_path(self) -> None:
        """A gitignored local override file should override only the requested binding fields."""

        repo_root = self.sandbox_dir / "buildish-site-pipeline"
        harness_dir = repo_root / "buildish-release-tooling" / "harness"
        harness_dir.mkdir(parents=True)
        config_path = harness_dir / "release-harness.yaml"
        local_override_path = default_local_override_path(config_path)
        self._write_yaml(
            config_path,
            {
                "schema_version": "1",
                "self_repository": {
                    "repository_id": "apache/buildish-site-pipeline",
                },
                "repository_overrides": {
                    "apache/buildish-release-tooling": {
                        "local_checkout_mode": "always",
                    }
                },
            },
        )
        self._write_yaml(
            local_override_path,
            {
                "self_repository": {
                    "local_path": "/opt/dev/buildish-site-pipeline",
                },
                "repository_overrides": {
                    "apache/buildish-release-tooling": {
                        "local_path": "/opt/dev/buildish-release-tooling",
                    }
                },
            },
        )

        resolved = load_release_harness_config(config_path)

        self.assertTrue(resolved.local_override_present)
        self.assertEqual(Path("/opt/dev/buildish-site-pipeline"), resolved.self_repository.local_path)
        self.assertEqual(
            Path("/opt/dev/buildish-release-tooling"),
            resolved.repository_overrides["apache/buildish-release-tooling"].local_path,
        )
        self.assertEqual("always", resolved.repository_overrides["apache/buildish-release-tooling"].local_checkout_mode)

    def test_relative_local_override_paths_are_resolved_from_config_directory(self) -> None:
        """Relative override paths should be interpreted relative to `release-harness.yaml`."""

        repo_root = self.sandbox_dir / "buildish-no-gradle-wrapper-jar"
        harness_dir = repo_root / "buildish-release-tooling" / "harness"
        harness_dir.mkdir(parents=True)
        config_path = harness_dir / "release-harness.yaml"
        self._write_yaml(
            config_path,
            {
                "schema_version": "1",
                "self_repository": {
                    "repository_id": "apache/buildish-no-gradle-wrapper-jar",
                    "local_path": "build/custom-self",
                },
                "repository_overrides": {
                    "apache/buildish-release-tooling": {
                        "local_checkout_mode": "always",
                        "local_path": "build/custom-tooling",
                    }
                },
            },
        )

        resolved = load_release_harness_config(config_path)

        self.assertEqual(repo_root / "build" / "custom-self", resolved.self_repository.local_path)
        self.assertEqual(
            repo_root / "build" / "custom-tooling",
            resolved.repository_overrides["apache/buildish-release-tooling"].local_path,
        )

    def test_repository_root_is_parent_of_buildish_release_tooling_directory(self) -> None:
        """The standard harness layout should resolve relative paths from the component repo root."""

        config_path = (
            self.sandbox_dir
            / "buildish-mammoth-cache"
            / "buildish-release-tooling"
            / "harness"
            / "release-harness.yaml"
        )
        self.assertEqual(
            self.sandbox_dir / "buildish-mammoth-cache",
            repository_root_for_config(config_path),
        )

    def test_resolved_config_json_model_preserves_binding_fields(self) -> None:
        """Resolved harness configs should serialize through the typed JSON model."""

        repo_root = self.sandbox_dir / "buildish-site-pipeline"
        harness_dir = repo_root / "buildish-release-tooling" / "harness"
        harness_dir.mkdir(parents=True)
        config_path = harness_dir / "release-harness.yaml"
        self._write_yaml(
            config_path,
            {
                "schema_version": "1",
                "self_repository": {
                    "repository_id": "apache/buildish-site-pipeline",
                },
                "repository_overrides": {
                    "apache/buildish-release-tooling": {
                        "local_checkout_mode": "always",
                    }
                },
            },
        )

        payload = load_release_harness_config(config_path).to_json_model().model_dump(mode="json")

        self.assertEqual(str(config_path), payload["config_path"])
        self.assertEqual(
            "apache/buildish-site-pipeline",
            payload["self_repository"]["repository_id"],
        )
        self.assertEqual(
            "always",
            payload["repository_overrides"]["apache/buildish-release-tooling"]["local_checkout_mode"],
        )

    def test_cli_resolve_config_emits_typed_json_payload(self) -> None:
        """The harness CLI should emit the typed resolved-config payload."""

        repo_root = self.sandbox_dir / "buildish-mammoth-cache"
        harness_dir = repo_root / "buildish-release-tooling" / "harness"
        harness_dir.mkdir(parents=True)
        config_path = harness_dir / "release-harness.yaml"
        self._write_yaml(
            config_path,
            {
                "schema_version": "1",
                "self_repository": {
                    "repository_id": "apache/buildish-mammoth-cache",
                },
            },
        )
        stdout = StringIO()
        stderr = StringIO()

        with (
            mock.patch("sys.stdout", stdout),
            mock.patch("sys.stderr", stderr),
        ):
            with self.assertRaises(SystemExit) as exc_info:
                harness_main(["resolve-config", str(config_path)])

        self.assertEqual(0, exc_info.exception.code)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(str(config_path), payload["config_path"])
        self.assertEqual(
            str(repo_root),
            payload["self_repository"]["local_path"],
        )
        self.assertEqual("", stderr.getvalue())
