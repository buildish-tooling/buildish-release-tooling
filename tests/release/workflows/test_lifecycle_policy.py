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
            "release-promote.yml",
            "release-testpypi.yml",
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
            "release-promote.yml",
        ):
            with self.subTest(workflow=name):
                self.assertEqual(expected, self._load(name)["concurrency"])

    def test_only_explicit_publication_jobs_receive_contents_write(self) -> None:
        expected = {
            "release-candidate.yml": {"publish-candidate"},
            "release-promote.yml": {"create-final-tag", "stage", "publish", "manifest"},
            "release-testpypi.yml": set(),
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
            "release-promote.yml",
            "release-testpypi.yml",
        ):
            text = (self.workflow_dir / name).read_text(encoding="utf-8")
            with self.subTest(workflow=name):
                self.assertIn("actions/upload-artifact@", text)
                self.assertIn("actions/download-artifact@", text)
                self.assertIn("sha256sum --check --strict", text)

    def test_privileged_jobs_execute_only_the_dispatched_workflow_revision(
        self,
    ) -> None:
        candidate = self._load("release-candidate.yml")
        jobs = cast(YamlMapping, candidate["jobs"])
        for job_name in ("prepare-assets", "publish-candidate"):
            job = cast(YamlMapping, jobs[job_name])
            self.assertEqual("release-candidate", job["environment"])
            steps = cast(list[YamlMapping], job["steps"])
            checkout = next(
                step
                for step in steps
                if str(step.get("uses", "")).startswith("actions/checkout@")
            )
            self.assertEqual(
                "${{ github.workflow_sha }}",
                cast(YamlMapping, checkout["with"])["ref"],
            )
        text = (self.workflow_dir / "release-candidate.yml").read_text(encoding="utf-8")
        self.assertIn("ref: ${{ needs.resolve.outputs.source_commit }}", text)
        self.assertEqual(
            1, text.count("ref: ${{ needs.resolve.outputs.source_commit }}")
        )

    def test_signing_secrets_are_consumed_only_after_candidate_environment_gate(
        self,
    ) -> None:
        jobs = cast(YamlMapping, self._load("release-candidate.yml")["jobs"])
        secret_names = {
            "BUILDISH_RELEASE_GPG_SECRET_SUBKEY",
            "BUILDISH_RELEASE_GPG_PASSPHRASE",
        }
        consumers: dict[str, set[str]] = {}
        for job_name, job_payload in jobs.items():
            job = cast(YamlMapping, job_payload)
            step_text = str(job.get("steps", []))
            used = {name for name in secret_names if name in step_text}
            if used:
                consumers[job_name] = used
                self.assertEqual("release-candidate", job.get("environment"))

        self.assertEqual({"prepare-assets": secret_names}, consumers)
        self.assertEqual(
            "release-candidate",
            cast(YamlMapping, jobs["publish-candidate"])["environment"],
        )

    def test_source_check_jobs_have_all_required_read_permissions(self) -> None:
        for workflow_name, job_name in (
            ("release-candidate.yml", "verify-source"),
            ("release-testpypi.yml", "verify-source"),
        ):
            jobs = cast(YamlMapping, self._load(workflow_name)["jobs"])
            job = cast(YamlMapping, jobs[job_name])
            self.assertEqual(
                {
                    "actions": "read",
                    "checks": "read",
                    "contents": "read",
                    "statuses": "read",
                },
                job["permissions"],
            )

    def test_testpypi_exercises_direct_state_and_safe_recovery(self) -> None:
        payload = self._load("release-testpypi.yml")
        jobs = cast(YamlMapping, payload["jobs"])
        self.assertEqual(
            {"resolve", "verify-source", "build", "inspect", "publish", "verify"},
            set(jobs),
        )
        text = (self.workflow_dir / "release-testpypi.yml").read_text(encoding="utf-8")
        self.assertIn("resolve-direct-release", text)
        self.assertIn("release-testpypi-config.yaml", text)
        self.assertIn("--allow-incomplete", text)
        self.assertIn("publication_state != 'complete'", text)
        self.assertIn("skip-existing: true", text)
        self.assertIn("--release-state", text)
        self.assertIn("publish.result == 'skipped'", text)

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
        for name in ("release-promote.yml",):
            text = (self.workflow_dir / name).read_text(encoding="utf-8")
            with self.subTest(workflow=name):
                self.assertIn("release-manifest-v1.json", text)
                self.assertIn("ATTACH_RESULT_PATH", text)
                self.assertIn('MANIFEST_PATH="$ATTACH_RESULT_PATH"', text)
                self.assertIn("release-manifest-attachment/attach-result.json", text)
                self.assertIn("attach-github-release-manifest", text)
                self.assertIn("needs.publish.outputs.publication_digest", text)
                self.assertIn("EXPECTED_STATE_DIGEST", text)
                self.assertIn("EXPECTED_PUBLICATION_DIGEST", text)
                self.assertLess(
                    text.index("publish-github-final-release"),
                    text.index("attach-github-release-manifest"),
                )

    def test_only_package_publish_jobs_receive_oidc_permission(self) -> None:
        expected = {
            "release-candidate.yml": set(),
            "release-promote.yml": {"publish-pypi"},
            "release-testpypi.yml": {"publish"},
            "release-verify-candidate.yml": set(),
        }
        for name, expected_jobs in expected.items():
            jobs = cast(YamlMapping, self._load(name)["jobs"])
            actual_jobs = {
                job_name
                for job_name, job in jobs.items()
                if isinstance(job, dict)
                and cast(YamlMapping, job.get("permissions", {})).get("id-token")
                == "write"
            }
            self.assertEqual(expected_jobs, actual_jobs)

    def test_production_pypi_publishes_only_promoted_candidate_distributions(
        self,
    ) -> None:
        text = (self.workflow_dir / "release-promote.yml").read_text(encoding="utf-8")
        self.assertIn("promotion-input-${{ github.run_id }}", text)
        self.assertNotIn("github.run_attempt", text)
        self.assertIn("pypa/gh-action-pypi-publish@", text)
        self.assertIn("--allow-incomplete", text)
        self.assertIn("skip-existing: true", text)
        self.assertIn("verify-pypi-publication", text)
        self.assertIn("--secondary-publication-result", text)
        self.assertIn("publication-evidence.sha256", text)
        self.assertIn("--secondary-verification-result", text)
        self.assertIn("--verification-evidence-publication-result", text)
        self.assertIn("attach-github-release-assets", text)
        self.assertIn("--immutable", text)
        self.assertIn("*.publish-attestations.json", text)
        self.assertIn("attestation-evidence.json", text)


if __name__ == "__main__":
    unittest.main()
