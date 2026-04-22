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

"""Policy checks for the component-owned release lifecycle workflows."""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import cast

from buildish_release_tooling.harness.backends.act.workflow_yaml import (
    _load_github_actions_yaml,
)
from buildish_release_tooling.harness.yaml_types import YamlMapping


class ReleaseWorkflowPolicyTest(unittest.TestCase):
    """Enforce the security and composition boundary of release workflows."""

    workflow_dir: Path
    workflow_names: tuple[str, ...]

    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow_dir = Path(__file__).resolve().parents[3] / ".github" / "workflows"
        cls.workflow_names = (
            "release-candidate.yml",
            "release-direct.yml",
            "release-promote.yml",
            "release-verify-candidate.yml",
        )

    def _load(self, name: str) -> YamlMapping:
        payload = _load_github_actions_yaml(self.workflow_dir / name)
        self.assertIsInstance(payload, dict)
        return payload

    def test_only_lifecycle_named_release_workflows_exist(self) -> None:
        actual = sorted(path.name for path in self.workflow_dir.glob("release*.yml"))
        self.assertEqual(sorted(self.workflow_names), actual)

    def test_workflows_default_to_read_only_contents(self) -> None:
        for name in self.workflow_names:
            with self.subTest(workflow=name):
                self.assertEqual({"contents": "read"}, self._load(name)["permissions"])

    def test_mutation_workflows_share_non_canceling_version_concurrency(self) -> None:
        expected = {
            "group": "buildish-release-${{ github.repository }}-${{ inputs.version }}",
            "cancel-in-progress": False,
        }
        for name in (
            "release-candidate.yml",
            "release-direct.yml",
            "release-promote.yml",
        ):
            with self.subTest(workflow=name):
                self.assertEqual(expected, self._load(name)["concurrency"])

    def test_only_explicit_publication_jobs_receive_contents_write(self) -> None:
        expected = {
            "release-candidate.yml": {"publish-candidate"},
            "release-direct.yml": {"create-final-tag", "stage", "publish", "manifest"},
            "release-promote.yml": {"create-final-tag", "stage", "publish", "manifest"},
            "release-verify-candidate.yml": set(),
        }
        for name, expected_jobs in expected.items():
            jobs = cast(YamlMapping, self._load(name)["jobs"])
            self.assertIsInstance(jobs, dict)
            actual_jobs = {
                job_name
                for job_name, job in jobs.items()
                if isinstance(job, dict)
                and job.get("permissions") == {"contents": "write"}
            }
            self.assertEqual(expected_jobs, actual_jobs)

    def test_all_external_actions_use_immutable_sha_pins(self) -> None:
        action_pattern = re.compile(r"^[^@]+@[0-9a-f]{40}$")
        for name in self.workflow_names:
            payload = self._load(name)
            jobs = cast(YamlMapping, payload["jobs"])
            for job_name, job in jobs.items():
                self.assertIsInstance(job, dict)
                job_payload = cast(YamlMapping, job)
                steps = cast(list[YamlMapping], job_payload.get("steps", []))
                for step in steps:
                    uses = step.get("uses")
                    if uses is not None:
                        self.assertRegex(
                            cast(str, uses), action_pattern, f"{name}:{job_name}"
                        )

    def test_nontrivial_same_run_files_use_workflow_artifacts(self) -> None:
        for name in (
            "release-candidate.yml",
            "release-direct.yml",
            "release-promote.yml",
        ):
            text = (self.workflow_dir / name).read_text(encoding="utf-8")
            with self.subTest(workflow=name):
                self.assertIn("actions/upload-artifact@", text)
                self.assertIn("actions/download-artifact@", text)
                self.assertIn("sha256sum --check --strict", text)

    def test_promotion_requires_exact_candidate_identity(self) -> None:
        on_block = cast(YamlMapping, self._load("release-promote.yml")["on"])
        dispatch = cast(YamlMapping, on_block["workflow_dispatch"])
        inputs = cast(YamlMapping, dispatch["inputs"])
        self.assertEqual(
            {"version", "candidate_tag", "candidate_manifest_digest"},
            set(inputs),
        )
        self.assertTrue(
            all(
                cast(YamlMapping, value)["required"] is True
                for value in inputs.values()
            )
        )
        text = (self.workflow_dir / "release-promote.yml").read_text(encoding="utf-8")
        self.assertNotIn("resolve-latest", text.lower())
        self.assertIn("verify-github-candidate", text)
        self.assertIn("--candidate-manifest-output", text)

    def test_final_manifest_is_attached_once_after_publication(self) -> None:
        for name in ("release-direct.yml", "release-promote.yml"):
            text = (self.workflow_dir / name).read_text(encoding="utf-8")
            with self.subTest(workflow=name):
                self.assertIn("release-manifest-v1.json", text)
                self.assertIn("attach-github-release-manifest", text)
                self.assertIn("needs.publish.outputs.publication_digest", text)
                self.assertIn("EXPECTED_STATE_DIGEST", text)
                self.assertIn("EXPECTED_PUBLICATION_DIGEST", text)
                self.assertLess(
                    text.index("publish-github-final-release"),
                    text.index("attach-github-release-manifest"),
                )


if __name__ == "__main__":
    unittest.main()
