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

"""Tests for orthogonal release configuration loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import cast
import unittest

import yaml

from buildish_release_tooling.release.config import (
    ReleaseConfig,
    load_release_config,
    load_verification_override_config,
    require_asf_profile,
    validate_selected_release_targets,
)

from tests.support import (
    cleanup_sandbox,
    create_build_test_sandbox,
    fixture_component_config_path,
)


def _direct_github_payload() -> dict[str, object]:
    return {
        "component": {
            "id": "buildish-example",
            "display_name": "Buildish Example",
        },
        "versioning": {
            "scheme": "semver",
            "final_tag_template": "v{version}",
        },
        "source": {
            "selection": "explicit-ref-or-default-branch",
            "default_branch": "main",
            "snapshot": {"mode": "platform-generated"},
            "checks": {
                "run_selected_ref_tests": True,
                "require_release_branch_ci": False,
            },
        },
        "lifecycle": {"mode": "direct"},
        "artifacts": {"produced": [], "checksums": []},
        "publication": {
            "authoritative": {
                "kind": "github-release",
                "repository": "buildish-tooling/buildish-example",
            },
            "convenience": [],
            "secondary": [],
        },
        "tags": {"final_mode": "exact-source-commit", "moving": []},
        "policy_profiles": {},
    }


def _write_yaml(path: Path, payload: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


class ReleaseConfigTest(unittest.TestCase):
    """Verify lifecycle and capability dimensions remain independently validated."""

    def test_load_direct_github_config_without_asf_fields(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "release-config.yaml"
        _write_yaml(config_path, _direct_github_payload())

        loaded = load_release_config(str(config_path))

        self.assertEqual("buildish-example", loaded.component.id)
        self.assertEqual("direct", loaded.lifecycle.mode)
        self.assertEqual("platform-generated", loaded.source.snapshot.mode)
        self.assertEqual("github-release", loaded.publication.authoritative.kind)
        self.assertIsNone(loaded.policy_profiles.asf)
        self.assertIsNone(loaded.candidate)
        self.assertIsNone(loaded.vote_materials)
        validate_selected_release_targets(loaded, allow_test_targets=False)

    def test_candidate_config_defaults_to_one_based_public_candidates(self) -> None:
        payload = _direct_github_payload()
        payload["lifecycle"] = {"mode": "candidate"}
        payload["candidate"] = {}

        loaded = ReleaseConfig.model_validate(payload)

        self.assertIsNotNone(loaded.candidate)
        self.assertEqual(1, loaded.candidate.start_number if loaded.candidate else None)
        self.assertEqual(
            "public-prerelease",
            loaded.candidate.visibility if loaded.candidate else None,
        )

    def test_candidate_start_number_may_be_zero(self) -> None:
        payload = _direct_github_payload()
        payload["lifecycle"] = {"mode": "candidate"}
        payload["candidate"] = {"start_number": 0}

        loaded = ReleaseConfig.model_validate(payload)

        self.assertEqual(0, loaded.candidate.start_number if loaded.candidate else None)

    def test_candidate_block_is_required_exactly_for_candidate_lifecycle(self) -> None:
        missing = _direct_github_payload()
        missing["lifecycle"] = {"mode": "candidate"}
        with self.assertRaisesRegex(ValueError, "candidate config must be present exactly"):
            ReleaseConfig.model_validate(missing)

        unexpected = _direct_github_payload()
        unexpected["candidate"] = {"start_number": 1}
        with self.assertRaisesRegex(ValueError, "candidate config must be present exactly"):
            ReleaseConfig.model_validate(unexpected)

    def test_direct_lifecycle_rejects_vote_materials(self) -> None:
        payload = _direct_github_payload()
        payload["vote_materials"] = {
            "profile": "generic",
            "release_name": "Buildish Example",
            "verification_guide_url": "https://example.invalid/verify",
            "instructions": "verify",
        }

        with self.assertRaisesRegex(ValueError, "vote_materials requires"):
            ReleaseConfig.model_validate(payload)

    def test_asf_capabilities_require_explicit_asf_profile(self) -> None:
        payload = _direct_github_payload()
        payload["source"] = {
            "selection": "release-branch",
            "snapshot": {
                "mode": "built-asset",
                "filename_template": "example-{version}-src.tar.gz",
                "archive_root_template": "example-{version}-src",
            },
            "checks": {
                "run_selected_ref_tests": False,
                "require_release_branch_ci": True,
            },
        }
        payload["publication"] = {
            "authoritative": {"kind": "asf-dist-svn"},
            "convenience": [],
            "secondary": [],
        }

        with self.assertRaisesRegex(ValueError, "require policy_profiles.asf"):
            ReleaseConfig.model_validate(payload)

    def test_asf_dist_requires_a_built_source_snapshot(self) -> None:
        payload = _direct_github_payload()
        payload["publication"] = {
            "authoritative": {"kind": "asf-dist-svn"},
            "convenience": [],
            "secondary": [],
        }
        payload["policy_profiles"] = {
            "asf": {
                "dist_dev_base": "https://dist.apache.org/repos/dist/dev/buildish/example",
                "dist_release_base": "https://dist.apache.org/repos/dist/release/buildish/example",
                "keys_url": "https://downloads.apache.org/buildish/KEYS",
            }
        }

        with self.assertRaisesRegex(ValueError, "requires source.snapshot.mode built-asset"):
            ReleaseConfig.model_validate(payload)

    def test_selected_asf_targets_validate_production_and_test_urls(self) -> None:
        loaded = load_release_config(
            str(fixture_component_config_path("buildish-site-pipeline"))
        )
        validate_selected_release_targets(loaded, allow_test_targets=False)

        payload = loaded.model_dump(mode="json")
        asf_payload = payload["policy_profiles"]["asf"]
        asf_payload["dist_dev_base"] = "file:///tmp/buildish/dev"
        asf_payload["dist_release_base"] = "http://localhost/buildish/release"
        test_target_config = ReleaseConfig.model_validate(payload)
        validate_selected_release_targets(test_target_config, allow_test_targets=True)
        with self.assertRaisesRegex(ValueError, "must use https://dist.apache.org"):
            validate_selected_release_targets(test_target_config, allow_test_targets=False)

    def test_incomplete_enabled_asf_atr_config_is_rejected(self) -> None:
        loaded = load_release_config(
            str(fixture_component_config_path("buildish-site-pipeline"))
        )
        payload = loaded.model_dump(mode="json")
        payload["policy_profiles"]["asf"]["atr"] = {
            "enabled": True,
            "base_url": "https://release-test.apache.org",
            "committee": "buildish",
        }

        with self.assertRaisesRegex(ValueError, "product_line"):
            ReleaseConfig.model_validate(payload)

    def test_checked_in_fixture_matrix_is_explicitly_asf_candidate_based(self) -> None:
        expected_start_numbers = {
            "buildish-mammoth-cache": 1,
            "buildish-no-gradle-wrapper-jar": 1,
            "buildish-site-pipeline": 0,
        }
        for component_id, expected_start_number in expected_start_numbers.items():
            with self.subTest(component=component_id):
                loaded = load_release_config(
                    str(fixture_component_config_path(component_id))
                )
                self.assertEqual(component_id, loaded.component.id)
                self.assertEqual("candidate", loaded.lifecycle.mode)
                self.assertEqual(
                    expected_start_number,
                    loaded.candidate.start_number if loaded.candidate else None,
                )
                self.assertEqual("asf", loaded.vote_materials.profile if loaded.vote_materials else None)
                self.assertEqual(
                    "https://downloads.apache.org/incubator/buildish/KEYS",
                    require_asf_profile(loaded).keys_url,
                )

    def test_unknown_fields_are_rejected_at_nested_boundaries(self) -> None:
        payload = _direct_github_payload()
        component = cast(dict[str, object], payload["component"])
        component["asf_keys_url"] = "https://example.invalid/KEYS"

        with self.assertRaisesRegex(ValueError, "Extra inputs are not permitted"):
            ReleaseConfig.model_validate(payload)


class VerificationOverrideConfigTest(unittest.TestCase):
    """Retain bounded loading for the current verification override contract."""

    def test_load_verification_override_config(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "override.yaml"
        _write_yaml(
            config_path,
            {
                "verify_rc": {
                    "profile_overrides": {
                        "source-release": {
                            "build": {"env": {"BUILD_FLAG": "local"}}
                        }
                    }
                }
            },
        )

        loaded = load_verification_override_config(str(config_path))

        self.assertEqual(
            "local",
            loaded.profile_overrides["source-release"].build.env["BUILD_FLAG"],
        )


if __name__ == "__main__":
    unittest.main()
