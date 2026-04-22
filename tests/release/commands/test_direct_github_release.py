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

"""Direct GitHub release command integration tests."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from buildish_release_tooling.release.core.state import DirectReleaseState
from buildish_release_tooling.release.platforms.github.text import (
    render_direct_final_release_body,
)

from tests.support import (
    cleanup_sandbox,
    cli_env,
    create_build_test_sandbox,
    create_fake_gh_launcher,
    git_create_annotated_tag,
    git_rev_parse,
    init_git_origin_and_clone,
    run_quiet,
    run_cli,
    set_github_origin_url,
)


class DirectGitHubReleaseCommandIntegrationTest(unittest.TestCase):
    """Exercise the composable direct-release steps without ASF policy."""

    def setUp(self) -> None:
        self.sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, self.sandbox_dir)
        _origin_dir, self.clone_dir = init_git_origin_and_clone(self.sandbox_dir)
        set_github_origin_url(
            self.clone_dir,
            "apache/example-project",
        )
        self.config_path = self.sandbox_dir / "release-config.yaml"
        self.config_path.write_text(
            "\n".join(
                [
                    "component:",
                    "  id: example-project",
                    "  display_name: Apache Example Project",
                    "versioning:",
                    "  scheme: semver",
                    '  final_tag_template: "v{version}"',
                    "source:",
                    "  selection: explicit-ref-or-default-branch",
                    "  default_branch: main",
                    "  snapshot:",
                    "    mode: platform-generated",
                    "lifecycle:",
                    "  mode: direct",
                    "artifacts:",
                    "  produced: []",
                    "  checksums: []",
                    "publication:",
                    "  authoritative:",
                    "    kind: github-release",
                    "    repository: apache/example-project",
                    "tags:",
                    "  final_mode: exact-source-commit",
                    "  moving: []",
                    "policy_profiles: {}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        self.state_path = self.sandbox_dir / "direct-release-state.json"
        completed = self._run(
            ["resolve-direct-release", "1.2.3"],
            manifest_path=self.state_path,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        git_create_annotated_tag(self.clone_dir, "v1.2.3")
        self.state = DirectReleaseState.model_validate_json(
            self.state_path.read_text(encoding="utf-8")
        )
        self.release_body = render_direct_final_release_body(self.state)

    def _run(
        self,
        command: list[str],
        *,
        manifest_path: Path,
        gh_path: Path | None = None,
        gh_state_dir: Path | None = None,
    ):
        extra_env = (
            {"FAKE_GH_STATE_DIR": str(gh_state_dir)}
            if gh_state_dir is not None
            else None
        )
        return run_cli(
            [*command, "--component-config", str(self.config_path)],
            cwd=self.clone_dir,
            env=cli_env(
                manifest_path,
                extra_env=extra_env,
                prepend_dirs=(gh_path.parent,) if gh_path is not None else (),
            ),
        )

    def _fake_gh(self, **kwargs):
        tag_object_sha = "b" * 40
        return create_fake_gh_launcher(
            self.sandbox_dir,
            read_ref_response={
                "ref": "refs/tags/v1.2.3",
                "object": {"sha": tag_object_sha, "type": "tag"},
            },
            read_tag_response={
                "object": {"sha": self.state.source.commit_sha, "type": "commit"}
            },
            **kwargs,
        )

    def _release(
        self,
        *,
        draft: bool,
        assets: list[dict[str, object]] | None = None,
        body: str | None = None,
    ) -> dict[str, object]:
        return {
            "id": 42,
            "tag_name": "v1.2.3",
            "name": "Apache Example Project 1.2.3",
            "body": self.release_body if body is None else body,
            "draft": draft,
            "prerelease": False,
            "html_url": (
                "https://github.com/apache/example-project/"
                "releases/tag/v1.2.3"
            ),
            "assets": assets or [],
        }

    def test_no_asset_direct_release_stages_verifies_and_publishes_idempotently(
        self,
    ) -> None:
        draft = self._release(draft=True)
        public = self._release(draft=False)
        gh_path, gh_state_dir = self._fake_gh(
            list_response=[],
            create_response=draft,
        )
        stage_result_path = self.sandbox_dir / "stage-result.json"
        completed = self._run(
            ["stage-github-final-release", "--release-state", str(self.state_path)],
            manifest_path=stage_result_path,
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        self.assertEqual(
            "created",
            json.loads(stage_result_path.read_text(encoding="utf-8"))["outcome"],
        )
        create_request = json.loads(
            (gh_state_dir / "create-release-request.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            self.state.source.commit_sha, create_request["target_commitish"]
        )
        self.assertTrue(create_request["draft"])
        self.assertFalse(create_request["prerelease"])

        gh_path, gh_state_dir = self._fake_gh(
            list_response=[draft],
        )
        verify_result_path = self.sandbox_dir / "verify-result.json"
        completed = self._run(
            ["verify-github-final-release", "--release-state", str(self.state_path)],
            manifest_path=verify_result_path,
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        self.assertEqual(
            "verified",
            json.loads(verify_result_path.read_text(encoding="utf-8"))["outcome"],
        )

        gh_path, gh_state_dir = self._fake_gh(
            list_response=[draft],
            list_responses=([draft], [public]),
            update_release_response=public,
        )
        publish_result_path = self.sandbox_dir / "publish-result.json"
        completed = self._run(
            ["publish-github-final-release", "--release-state", str(self.state_path)],
            manifest_path=publish_result_path,
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        self.assertEqual(
            "published",
            json.loads(publish_result_path.read_text(encoding="utf-8"))["outcome"],
        )
        update_request = json.loads(
            (gh_state_dir / "update-release-request.json").read_text(encoding="utf-8")
        )
        self.assertFalse(update_request["draft"])

        gh_path, gh_state_dir = self._fake_gh(
            list_response=[public],
        )
        rerun_path = self.sandbox_dir / "publish-rerun-result.json"
        completed = self._run(
            ["publish-github-final-release", "--release-state", str(self.state_path)],
            manifest_path=rerun_path,
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        self.assertEqual(
            "already-complete",
            json.loads(rerun_path.read_text(encoding="utf-8"))["outcome"],
        )
        self.assertNotIn(
            "PATCH",
            (gh_state_dir / "requests.log").read_text(encoding="utf-8"),
        )

        release_manifest_path = self.sandbox_dir / "direct-release-manifest.json"
        completed = self._run(
            [
                "create-release-manifest",
                "--release-state",
                str(self.state_path),
                "--publication-result",
                str(rerun_path),
            ],
            manifest_path=release_manifest_path,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        release_manifest = json.loads(release_manifest_path.read_text(encoding="utf-8"))
        self.assertNotIn("promoted_candidate", release_manifest)
        self.assertEqual([], release_manifest["promotion_evidence"])

        durable_manifest_path = self.sandbox_dir / "release-manifest-v1.json"
        durable_manifest_path.write_bytes(release_manifest_path.read_bytes())
        manifest_digest = hashlib.sha256(durable_manifest_path.read_bytes()).hexdigest()
        manifest_asset = {
            "id": 102,
            "name": "release-manifest-v1.json",
            "size": durable_manifest_path.stat().st_size,
            "digest": f"sha256:{manifest_digest}",
        }
        public_with_manifest = self._release(draft=False, assets=[manifest_asset])
        gh_path, gh_state_dir = self._fake_gh(
            list_response=[public],
            list_responses=([public], [public_with_manifest]),
        )
        attach_result_path = self.sandbox_dir / "attach-release-manifest-result.json"
        completed = self._run(
            [
                "attach-github-release-manifest",
                "--release-state",
                str(self.state_path),
                "--release-manifest",
                str(durable_manifest_path),
            ],
            manifest_path=attach_result_path,
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        attach_result = json.loads(attach_result_path.read_text(encoding="utf-8"))
        self.assertEqual("attached", attach_result["outcome"])
        self.assertEqual(manifest_digest, attach_result["release_manifest"]["digest"])
        self.assertEqual(
            "false",
            (gh_state_dir / "release-upload-clobber.txt")
            .read_text(encoding="utf-8")
            .strip(),
        )
        uploaded_files = (gh_state_dir / "release-upload-files.log").read_text(
            encoding="utf-8"
        )

        attach_rerun_result_path = (
            self.sandbox_dir / "attach-release-manifest-rerun-result.json"
        )
        completed = self._run(
            [
                "attach-github-release-manifest",
                "--release-state",
                str(self.state_path),
                "--release-manifest",
                str(durable_manifest_path),
            ],
            manifest_path=attach_rerun_result_path,
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        attach_rerun_result = json.loads(
            attach_rerun_result_path.read_text(encoding="utf-8")
        )
        self.assertEqual("already-complete", attach_rerun_result["outcome"])
        self.assertEqual(
            uploaded_files,
            (gh_state_dir / "release-upload-files.log").read_text(encoding="utf-8"),
        )

    def test_built_asset_is_uploaded_without_clobber_and_revalidated(self) -> None:
        asset_bytes = b"direct release asset\n"
        digest = hashlib.sha256(asset_bytes).hexdigest()
        asset_path = self.sandbox_dir / "example-project-1.2.3.zip"
        asset_path.write_bytes(asset_bytes)
        payload = self.state.model_dump(mode="json", exclude_none=True)
        payload["artifacts"] = [
            {
                "kind": "generic-file",
                "logical_name": asset_path.name,
                "digests": {"sha256": digest},
                "size_bytes": len(asset_bytes),
                "locations": [],
            }
        ]
        asset_state = DirectReleaseState.model_validate(payload)
        asset_state_path = self.sandbox_dir / "direct-release-with-asset.json"
        asset_state_path.write_text(
            asset_state.model_dump_json(indent=2, exclude_none=True) + "\n",
            encoding="utf-8",
        )
        asset_body = render_direct_final_release_body(asset_state)
        draft_without_asset = self._release(draft=True, body=asset_body)
        draft_with_asset = self._release(
            draft=True,
            body=asset_body,
            assets=[
                {
                    "id": 101,
                    "name": asset_path.name,
                    "size": len(asset_bytes),
                    "digest": f"sha256:{digest}",
                }
            ],
        )
        gh_path, gh_state_dir = self._fake_gh(
            list_response=[draft_without_asset],
            list_responses=([draft_without_asset], [draft_with_asset]),
        )
        result_path = self.sandbox_dir / "asset-stage-result.json"

        completed = self._run(
            [
                "stage-github-final-release",
                "--release-state",
                str(asset_state_path),
                "--asset",
                str(asset_path),
            ],
            manifest_path=result_path,
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        self.assertEqual(
            "completed",
            json.loads(result_path.read_text(encoding="utf-8"))["outcome"],
        )
        self.assertEqual(
            "false",
            (gh_state_dir / "release-upload-clobber.txt")
            .read_text(encoding="utf-8")
            .strip(),
        )

    def test_metadata_drift_stops_staging_without_mutation(self) -> None:
        drifted = self._release(draft=True, body="unexpected release body")
        gh_path, gh_state_dir = self._fake_gh(
            list_response=[drifted],
        )

        completed = self._run(
            ["stage-github-final-release", "--release-state", str(self.state_path)],
            manifest_path=self.sandbox_dir / "drift-result.json",
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("release body does not match", completed.stderr)
        self.assertFalse((gh_state_dir / "create-release-request.json").exists())
        self.assertFalse((gh_state_dir / "update-release-request.json").exists())
        self.assertFalse((gh_state_dir / "release-upload-files.log").exists())

    def test_read_reports_observed_state_without_desired_metadata_comparison(
        self,
    ) -> None:
        observed = self._release(draft=True, body="externally authored body")
        gh_path, gh_state_dir = self._fake_gh(
            list_response=[observed],
        )
        result_path = self.sandbox_dir / "read-result.json"

        completed = self._run(
            ["read-github-final-release", "--release-state", str(self.state_path)],
            manifest_path=result_path,
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        result = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual("observed", result["outcome"])
        self.assertTrue(result["publication"]["draft"])

    def test_create_final_tag_accepts_direct_state_without_candidate(self) -> None:
        run_quiet(
            ["git", "-C", str(self.clone_dir), "tag", "-d", "v1.2.3"],
            check=True,
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            self.sandbox_dir,
            list_response=[],
            create_tag_response={"sha": "a" * 40},
            create_ref_response={"ref": "refs/tags/v1.2.3"},
        )
        result_path = self.sandbox_dir / "create-final-tag-result.json"

        completed = self._run(
            ["create-final-tag", "--release-state", str(self.state_path)],
            manifest_path=result_path,
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        result = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertNotIn("selected_rc_tag", result)
        self.assertEqual("github-api", result["tag_creation_mode"])
        self.assertEqual(
            self.state.source.commit_sha, git_rev_parse(self.clone_dir, "v1.2.3^{}")
        )


if __name__ == "__main__":
    unittest.main()
