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

from tests.release.materialization_support import generated_action_commit, local_materialization_remote
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
        self.origin_dir, self.clone_dir = init_git_origin_and_clone(self.sandbox_dir)
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
                "object": {"sha": self.state.final_tag.target_commit, "type": "commit"}
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
                "https://github.com/apache/example-project/releases/tag/v1.2.3"
            ),
            "created_at": "2026-08-05T09:00:00Z",
            "published_at": None if draft else "2026-08-05T09:05:00Z",
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
            "main", create_request["target_commitish"]
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
        self.assertEqual("main", update_request["target_commitish"])
        self.assertEqual(self.state.final_tag.name, update_request["tag_name"])

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
        self.assertEqual("2026-08-05T09:05:00Z", release_manifest["created_at"])

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
        mismatched_manifest = json.loads(
            durable_manifest_path.read_text(encoding="utf-8")
        )
        mismatched_markdown = "Different release notes.\n"
        mismatched_manifest["release_notes"] = {
            "source_path": "release-notes/1.2.3.md",
            "sha256": hashlib.sha256(mismatched_markdown.encode("utf-8")).hexdigest(),
            "markdown": mismatched_markdown,
        }
        mismatched_manifest_path = (
            self.sandbox_dir / "mismatched-manifest" / "release-manifest-v1.json"
        )
        mismatched_manifest_path.parent.mkdir()
        mismatched_manifest_path.write_text(
            json.dumps(mismatched_manifest) + "\n", encoding="utf-8"
        )
        gh_path, gh_state_dir = self._fake_gh(list_response=[public])
        completed = self._run(
            [
                "attach-github-release-manifest",
                "--release-state",
                str(self.state_path),
                "--release-manifest",
                str(mismatched_manifest_path),
            ],
            manifest_path=self.sandbox_dir / "mismatched-manifest-attach-result.json",
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertNotEqual(0, completed.returncode)
        self.assertIn(
            "release manifest release notes do not match final-release state",
            completed.stderr,
        )

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

    def test_manifest_is_sealed_on_draft_and_survives_immutable_publication(self) -> None:
        self._exercise_sealed_publication()

    def test_materialized_direct_release_is_sealed_and_survives_immutable_publication(self) -> None:
        self.config_path.write_text(self.config_path.read_text().replace(
            "final_mode: exact-source-commit", "final_mode: detached-materialization-commit\n  materialized_paths: [dist]"
        ))
        local_materialization_remote(self.clone_dir, self.origin_dir)
        commit = generated_action_commit(self.clone_dir, self.state.source.commit_sha)
        bound = self.sandbox_dir / "bound-direct.json"
        completed = self._run(
            ["bind-materialization", "--release-state", str(self.state_path), "--materialized-commit", commit,
             "--bundle-output", str(self.sandbox_dir / "direct.bundle")], manifest_path=bound,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.state_path = bound
        self.state = DirectReleaseState.model_validate_json(bound.read_text())
        run_quiet(["git", "tag", "-d", "v1.2.3"], cwd=self.clone_dir, check=True)
        gh_path, gh_state_dir = create_fake_gh_launcher(
            self.sandbox_dir, list_response=[], create_tag_response={"sha": "c" * 40},
            create_ref_response={"ref": "refs/tags/v1.2.3"},
        )
        created = self._run(["create-final-tag", "--release-state", str(bound)],
                            manifest_path=self.sandbox_dir / "materialized-final-tag.json", gh_path=gh_path, gh_state_dir=gh_state_dir)
        self.assertEqual(0, created.returncode, created.stderr)
        self.assertEqual(commit, git_rev_parse(self.clone_dir, "v1.2.3^{commit}"))
        self._exercise_sealed_publication()

    def _exercise_sealed_publication(self) -> None:
        draft = self._release(draft=True)
        draft["html_url"] = "https://github.com/apache/example-project/releases/tag/untagged-temporary"
        gh_path, gh_state_dir = self._fake_gh(list_response=[draft])
        stage_path = self.sandbox_dir / "sealed-stage.json"
        completed = self._run(
            ["stage-github-final-release", "--release-state", str(self.state_path)],
            manifest_path=stage_path, gh_path=gh_path, gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        manifest_path = self.sandbox_dir / "release-manifest-v1.json"
        completed = self._run(
            ["create-release-manifest", "--release-state", str(self.state_path),
             "--publication-result", str(stage_path)], manifest_path=manifest_path,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        manifest_text = manifest_path.read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)
        digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        self.assertEqual(draft["created_at"], manifest["created_at"])
        self.assertTrue(manifest["extensions"][0]["draft"])
        self.assertNotIn("published_at", manifest["extensions"][0])
        self.assertTrue(manifest["publications"][0]["uri"].endswith("/releases/tag/v1.2.3"))
        asset = {"id": 102, "name": manifest_path.name, "size": manifest_path.stat().st_size,
                 "digest": f"sha256:{digest}"}
        sealed_draft = {**draft, "assets": [asset]}
        public = {**self._release(draft=False, assets=[asset]), "immutable": True}
        gh_path, gh_state_dir = self._fake_gh(
            list_response=[draft], list_responses=([draft], [sealed_draft]),
        )
        completed = self._run(
            ["attach-github-release-manifest", "--release-state", str(self.state_path),
             "--release-manifest", str(manifest_path)],
            manifest_path=self.sandbox_dir / "sealed-attachment.json",
            gh_path=gh_path, gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        # The publication gate rejects a missing or substituted manifest before any PATCH.
        for observed, expected_digest in ((draft, digest), (sealed_draft, "0" * 64)):
            gh_path, gh_state_dir = self._fake_gh(list_response=[observed])
            completed = self._run(
                ["publish-github-final-release", "--release-state", str(self.state_path),
                 "--require-manifest-digest", expected_digest],
                manifest_path=self.sandbox_dir / "rejected-finalization.json",
                gh_path=gh_path, gh_state_dir=gh_state_dir,
            )
            self.assertNotEqual(0, completed.returncode)
            self.assertIn("sealed release manifest", completed.stderr)
            self.assertFalse((gh_state_dir / "update-release-request.json").exists())
        gh_path, gh_state_dir = self._fake_gh(
            list_response=[sealed_draft], list_responses=([sealed_draft], [public]),
            update_release_response=public, release_asset_text_by_id={102: manifest_text},
        )
        completed = self._run(
            ["publish-github-final-release", "--release-state", str(self.state_path),
             "--require-manifest-digest", digest],
            manifest_path=self.sandbox_dir / "sealed-publish.json",
            gh_path=gh_path, gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        # Validation and idempotent attachment must never upload to the now-locked Release.
        for command in (
            ["verify-github-final-release", "--release-state", str(self.state_path)],
            ["publish-github-final-release", "--release-state", str(self.state_path),
             "--require-manifest-digest", digest],
            ["attach-github-release-manifest", "--release-state", str(self.state_path),
             "--release-manifest", str(manifest_path)],
        ):
            gh_path, gh_state_dir = self._fake_gh(
                list_response=[public], release_asset_text_by_id={102: manifest_text},
            )
            tracked = [gh_state_dir / "release-upload-files.log", gh_state_dir / "update-release-request.json"]
            before = [path.read_bytes() if path.exists() else None for path in tracked]
            request_log = gh_state_dir / "requests.log"
            prior_requests = request_log.read_text() if request_log.exists() else ""
            completed = self._run(command, manifest_path=self.sandbox_dir / "sealed-rerun.json",
                                  gh_path=gh_path, gh_state_dir=gh_state_dir)
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual(before, [path.read_bytes() if path.exists() else None for path in tracked])
            self.assertNotIn("PATCH", request_log.read_text()[len(prior_requests):])
        # A complete promotion rerun reuses the real sealed snapshot, including its timestamp.
        gh_path, gh_state_dir = self._fake_gh(
            list_response=[public], release_asset_text_by_id={102: manifest_text},
        )
        completed = self._run(
            ["stage-github-final-release", "--release-state", str(self.state_path)],
            manifest_path=stage_path, gh_path=gh_path, gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        regenerated_path = self.sandbox_dir / "regenerated-manifest.json"
        completed = self._run(
            ["create-release-manifest", "--release-state", str(self.state_path),
             "--publication-result", str(stage_path)], manifest_path=regenerated_path,
            gh_path=gh_path, gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(manifest_path.read_bytes(), regenerated_path.read_bytes())
        # A prematurely published immutable release cannot be repaired with an upload.
        gh_path, gh_state_dir = self._fake_gh(
            list_response=[{**self._release(draft=False), "immutable": True}],
        )
        upload_log = gh_state_dir / "release-upload-files.log"
        prior_uploads = upload_log.read_bytes() if upload_log.exists() else None
        completed = self._run(
            ["attach-github-release-manifest", "--release-state", str(self.state_path),
             "--release-manifest", str(manifest_path)],
            manifest_path=self.sandbox_dir / "locked-missing-manifest.json",
            gh_path=gh_path, gh_state_dir=gh_state_dir,
        )
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("missing its sealed manifest", completed.stderr)
        self.assertEqual(prior_uploads, upload_log.read_bytes() if upload_log.exists() else None)
        # Only visibility/publication time can change; a different Release identity fails.
        for changed in ({"id": 43}, {"created_at": "2026-08-05T08:00:00Z"},
                        {"html_url": "https://github.com/other/repo/releases/tag/v1.2.3"}):
            gh_path, gh_state_dir = self._fake_gh(
                list_response=[{**public, **changed}], release_asset_text_by_id={102: manifest_text},
            )
            completed = self._run(
                ["verify-github-final-release", "--release-state", str(self.state_path)],
                manifest_path=self.sandbox_dir / "rejected-snapshot.json",
                gh_path=gh_path, gh_state_dir=gh_state_dir,
            )
            self.assertNotEqual(0, completed.returncode)

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
