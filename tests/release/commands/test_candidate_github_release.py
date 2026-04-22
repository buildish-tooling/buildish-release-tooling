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

"""GitHub candidate lifecycle integration tests."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from buildish_release_tooling.release.core.state import (
    CandidateReleaseState,
    PromotionState,
)
from buildish_release_tooling.release.platforms.github.candidate import (
    artifact_references_from_paths,
    candidate_release_name,
)
from buildish_release_tooling.release.platforms.github.manifests import (
    GitHubCandidatePublication,
    StageGitHubCandidateResult,
)
from buildish_release_tooling.release.platforms.github.text import (
    render_candidate_release_body,
    render_direct_final_release_body,
)

from tests.support import (
    cleanup_sandbox,
    cli_env,
    create_build_test_sandbox,
    create_fake_gh_launcher,
    git_create_annotated_tag,
    init_git_origin_and_clone,
    run_cli,
    set_github_origin_url,
)


class GitHubCandidateLifecycleIntegrationTest(unittest.TestCase):
    """Exercise retained public candidates and exact durable manifests."""

    def setUp(self) -> None:
        self.sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, self.sandbox_dir)
        _origin_dir, self.clone_dir = init_git_origin_and_clone(self.sandbox_dir)
        set_github_origin_url(self.clone_dir, "buildish-tooling/buildish-example")
        self.config_path = self.sandbox_dir / "release-config.yaml"
        self.config_path.write_text(
            "\n".join(
                [
                    "component:",
                    "  id: buildish-example",
                    "  display_name: Buildish Example",
                    "source:",
                    "  selection: explicit-ref-or-default-branch",
                    "  default_branch: main",
                    "  snapshot:",
                    "    mode: platform-generated",
                    "lifecycle:",
                    "  mode: candidate",
                    "candidate:",
                    "  label: rc",
                    "  start_number: 1",
                    "  visibility: public-prerelease",
                    "  retention: retain-published",
                    "publication:",
                    "  authoritative:",
                    "    kind: github-release",
                    "    repository: buildish-tooling/buildish-example",
                    "vote_materials:",
                    "  profile: generic",
                    "  release_name: Buildish Example",
                    "  verification_guide_url: https://buildish.org/verify/",
                    "  instructions: Verify the exact candidate manifest and artifacts.",
                    "policy_profiles: {}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def _run(
        self,
        command: list[str],
        *,
        result_path: Path,
        gh_path: Path | None = None,
        gh_state_dir: Path | None = None,
    ):
        return run_cli(
            [*command, "--component-config", str(self.config_path)],
            cwd=self.clone_dir,
            env=cli_env(
                result_path,
                extra_env=(
                    {"FAKE_GH_STATE_DIR": str(gh_state_dir)}
                    if gh_state_dir is not None
                    else None
                ),
                prepend_dirs=(gh_path.parent,) if gh_path is not None else (),
            ),
        )

    def _resolve(self, filename: str) -> tuple[Path, CandidateReleaseState]:
        state_path = self.sandbox_dir / filename
        completed = self._run(
            ["resolve-candidate", "1.2.3"],
            result_path=state_path,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        return state_path, CandidateReleaseState.model_validate_json(
            state_path.read_text(encoding="utf-8")
        )

    def _fake_gh(
        self,
        state: CandidateReleaseState,
        *,
        list_response: object,
        **kwargs,
    ) -> tuple[Path, Path]:
        tag_object_sha = "b" * 40
        return create_fake_gh_launcher(
            self.sandbox_dir,
            list_response=list_response,
            read_ref_response={
                "ref": f"refs/tags/{state.candidate.tag.name}",
                "object": {"sha": tag_object_sha, "type": "tag"},
            },
            read_tag_response={
                "object": {"sha": state.source.commit_sha, "type": "commit"}
            },
            **kwargs,
        )

    def _fake_final_gh(
        self,
        promotion: PromotionState,
        *,
        list_response: object,
        **kwargs,
    ) -> tuple[Path, Path]:
        return create_fake_gh_launcher(
            self.sandbox_dir,
            list_response=list_response,
            read_ref_response={
                "ref": f"refs/tags/{promotion.final_tag.name}",
                "object": {"sha": "d" * 40, "type": "tag"},
            },
            read_tag_response={
                "object": {"sha": promotion.source.commit_sha, "type": "commit"}
            },
            **kwargs,
        )

    @staticmethod
    def _release(
        state: CandidateReleaseState,
        *,
        draft: bool,
        prerelease: bool,
        assets: list[dict[str, object]],
    ) -> dict[str, object]:
        return {
            "id": 42 + state.candidate.number,
            "tag_name": state.candidate.tag.name,
            "name": candidate_release_name(state),
            "body": render_candidate_release_body(state, state.artifacts),
            "draft": draft,
            "prerelease": prerelease,
            "html_url": (
                "https://github.com/buildish-tooling/buildish-example/releases/tag/"
                f"{state.candidate.tag.name}"
            ),
            "assets": assets,
        }

    def test_candidate_one_is_retained_while_candidate_two_is_staged(self) -> None:
        state_path, state = self._resolve("candidate-1-state.json")
        gh_path, gh_state_dir = self._fake_gh(
            state,
            list_response=[],
            create_tag_response={"sha": "a" * 40},
            create_ref_response={"ref": f"refs/tags/{state.candidate.tag.name}"},
        )
        tag_result_path = self.sandbox_dir / "candidate-1-tag.json"
        completed = self._run(
            ["create-candidate-tag", "--candidate-state", str(state_path)],
            result_path=tag_result_path,
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)

        asset_path = self.sandbox_dir / "buildish-example-1.2.3.zip"
        asset_path.write_bytes(b"candidate one asset\n")
        state = state.model_copy(
            update={"artifacts": artifact_references_from_paths([asset_path])}
        )
        asset = state.artifacts[0]
        asset_payload = {
            "id": 101,
            "name": asset.logical_name,
            "size": asset.size_bytes,
            "digest": f"sha256:{asset.digests['sha256']}",
        }
        draft_without_assets = self._release(
            state,
            draft=True,
            prerelease=False,
            assets=[],
        )
        draft_with_asset = self._release(
            state,
            draft=True,
            prerelease=False,
            assets=[asset_payload],
        )
        gh_path, gh_state_dir = self._fake_gh(
            state,
            list_response=[],
            list_responses=([], [draft_with_asset]),
            create_response=draft_without_assets,
        )
        stage_result_path = self.sandbox_dir / "candidate-1-stage.json"
        completed = self._run(
            [
                "stage-github-candidate",
                "--candidate-state",
                str(state_path),
                "--asset",
                str(asset_path),
            ],
            result_path=stage_result_path,
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        self.assertEqual(
            "created",
            json.loads(stage_result_path.read_text(encoding="utf-8"))["outcome"],
        )
        self.assertEqual(
            "false",
            (gh_state_dir / "release-upload-clobber.txt")
            .read_text(encoding="utf-8")
            .strip(),
        )

        candidate_manifest_path = self.sandbox_dir / "candidate-manifest.json"
        completed = self._run(
            [
                "create-candidate-manifest",
                "--candidate-state",
                str(state_path),
                "--stage-result",
                str(stage_result_path),
            ],
            result_path=candidate_manifest_path,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest_text = candidate_manifest_path.read_text(encoding="utf-8")
        manifest_digest = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
        manifest_asset = {
            "id": 202,
            "name": "candidate-manifest.json",
            "size": candidate_manifest_path.stat().st_size,
            "digest": f"sha256:{manifest_digest}",
        }
        draft_with_manifest = self._release(
            state,
            draft=True,
            prerelease=False,
            assets=[asset_payload, manifest_asset],
        )
        gh_path, gh_state_dir = self._fake_gh(
            state,
            list_response=[draft_with_asset],
            list_responses=([draft_with_asset], [draft_with_manifest]),
        )
        attach_result_path = self.sandbox_dir / "candidate-1-attach.json"
        completed = self._run(
            [
                "attach-github-candidate-manifest",
                "--candidate-state",
                str(state_path),
                "--candidate-manifest",
                str(candidate_manifest_path),
            ],
            result_path=attach_result_path,
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)

        gh_path, gh_state_dir = self._fake_gh(
            state,
            list_response=[draft_with_manifest],
            release_asset_text_by_id={202: manifest_text},
        )
        verify_result_path = self.sandbox_dir / "candidate-1-verify.json"
        downloaded_manifest_path = self.sandbox_dir / "verified-candidate-manifest.json"
        completed = self._run(
            [
                "verify-github-candidate",
                "--candidate-tag",
                state.candidate.tag.name,
                "--candidate-manifest-digest",
                manifest_digest,
                "--candidate-manifest-output",
                str(downloaded_manifest_path),
            ],
            result_path=verify_result_path,
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        self.assertEqual(
            manifest_text, downloaded_manifest_path.read_text(encoding="utf-8")
        )

        public_config_text = self.config_path.read_text(encoding="utf-8")
        self.config_path.write_text(
            public_config_text.replace(
                "  visibility: public-prerelease",
                "  visibility: draft",
            ),
            encoding="utf-8",
        )
        gh_path, gh_state_dir = self._fake_gh(
            state,
            list_response=[draft_with_manifest],
            release_asset_text_by_id={202: manifest_text},
        )
        draft_finalize_path = self.sandbox_dir / "candidate-1-retain-draft.json"
        completed = self._run(
            [
                "finalize-github-candidate",
                "--candidate-tag",
                state.candidate.tag.name,
                "--candidate-manifest-digest",
                manifest_digest,
            ],
            result_path=draft_finalize_path,
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        self.assertEqual(
            "retained-draft",
            json.loads(draft_finalize_path.read_text(encoding="utf-8"))["outcome"],
        )
        self.assertNotIn(
            "PATCH",
            (gh_state_dir / "requests.log").read_text(encoding="utf-8"),
        )
        self.config_path.write_text(public_config_text, encoding="utf-8")

        public_candidate_one = self._release(
            state,
            draft=False,
            prerelease=True,
            assets=[asset_payload, manifest_asset],
        )
        gh_path, gh_state_dir = self._fake_gh(
            state,
            list_response=[draft_with_manifest],
            list_responses=([draft_with_manifest], [public_candidate_one]),
            update_release_response=public_candidate_one,
            release_asset_text_by_id={202: manifest_text},
        )
        finalize_result_path = self.sandbox_dir / "candidate-1-finalize.json"
        completed = self._run(
            [
                "finalize-github-candidate",
                "--candidate-tag",
                state.candidate.tag.name,
                "--candidate-manifest-digest",
                manifest_digest,
            ],
            result_path=finalize_result_path,
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        self.assertEqual(
            "published",
            json.loads(finalize_result_path.read_text(encoding="utf-8"))["outcome"],
        )

        state_two_path, state_two = self._resolve("candidate-2-state.json")
        self.assertEqual("v1.2.3-rc2", state_two.candidate.tag.name)
        gh_path, gh_state_dir = self._fake_gh(
            state_two,
            list_response=[public_candidate_one],
            create_tag_response={"sha": "c" * 40},
            create_ref_response={"ref": f"refs/tags/{state_two.candidate.tag.name}"},
        )
        completed = self._run(
            ["create-candidate-tag", "--candidate-state", str(state_two_path)],
            result_path=self.sandbox_dir / "candidate-2-tag.json",
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)

        draft_candidate_two = self._release(
            state_two,
            draft=True,
            prerelease=False,
            assets=[],
        )
        gh_path, gh_state_dir = self._fake_gh(
            state_two,
            list_response=[public_candidate_one],
            create_response=draft_candidate_two,
        )
        completed = self._run(
            ["stage-github-candidate", "--candidate-state", str(state_two_path)],
            result_path=self.sandbox_dir / "candidate-2-stage.json",
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        self.assertNotIn(
            "DELETE",
            (gh_state_dir / "requests.log").read_text(encoding="utf-8"),
        )

    def test_wrong_candidate_manifest_digest_fails_without_mutation(self) -> None:
        state_path, state = self._resolve("candidate-state.json")
        del state_path
        manifest_text = "{}\n"
        actual_digest = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
        manifest_asset = {
            "id": 202,
            "name": "candidate-manifest.json",
            "size": len(manifest_text.encode("utf-8")),
            "digest": f"sha256:{actual_digest}",
        }
        release = self._release(
            state,
            draft=True,
            prerelease=False,
            assets=[manifest_asset],
        )
        gh_path, gh_state_dir = self._fake_gh(
            state,
            list_response=[release],
            release_asset_text_by_id={202: manifest_text},
        )

        completed = self._run(
            [
                "finalize-github-candidate",
                "--candidate-tag",
                state.candidate.tag.name,
                "--candidate-manifest-digest",
                "f" * 64,
            ],
            result_path=self.sandbox_dir / "wrong-digest.json",
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )

        self.assertNotEqual(0, completed.returncode)
        requests = (gh_state_dir / "requests.log").read_text(encoding="utf-8")
        self.assertNotIn("PATCH", requests)
        self.assertNotIn("DELETE", requests)

    def test_remote_candidate_tag_drift_fails_before_release_mutation(self) -> None:
        state_path, state = self._resolve("tag-drift-state.json")
        git_create_annotated_tag(self.clone_dir, state.candidate.tag.name)
        gh_path, gh_state_dir = create_fake_gh_launcher(
            self.sandbox_dir,
            list_response=[],
            read_ref_response={
                "ref": f"refs/tags/{state.candidate.tag.name}",
                "object": {"sha": "a" * 40, "type": "tag"},
            },
            read_tag_response={"object": {"sha": "f" * 40, "type": "commit"}},
        )

        completed = self._run(
            ["stage-github-candidate", "--candidate-state", str(state_path)],
            result_path=self.sandbox_dir / "tag-drift-result.json",
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )

        self.assertNotEqual(0, completed.returncode)
        requests = (gh_state_dir / "requests.log").read_text(encoding="utf-8")
        self.assertNotIn("POST", requests)
        self.assertNotIn("PATCH", requests)

    def test_candidate_asset_drift_fails_without_clobber(self) -> None:
        state_path, state = self._resolve("asset-drift-state.json")
        git_create_annotated_tag(self.clone_dir, state.candidate.tag.name)
        asset_path = self.sandbox_dir / "example.zip"
        asset_path.write_bytes(b"expected candidate bytes\n")
        state_with_asset = state.model_copy(
            update={"artifacts": artifact_references_from_paths([asset_path])}
        )
        expected_asset = state_with_asset.artifacts[0]
        drifted_release = self._release(
            state_with_asset,
            draft=True,
            prerelease=False,
            assets=[
                {
                    "id": 501,
                    "name": expected_asset.logical_name,
                    "size": expected_asset.size_bytes,
                    "digest": f"sha256:{'f' * 64}",
                }
            ],
        )
        gh_path, gh_state_dir = self._fake_gh(
            state,
            list_response=[drifted_release],
        )

        completed = self._run(
            [
                "stage-github-candidate",
                "--candidate-state",
                str(state_path),
                "--asset",
                str(asset_path),
            ],
            result_path=self.sandbox_dir / "asset-drift-result.json",
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("sha256 mismatch", completed.stderr)
        self.assertFalse((gh_state_dir / "release-upload-files.log").exists())

    def test_asf_vote_profile_is_an_extension_over_the_same_candidate_manifest(
        self,
    ) -> None:
        state_path, state = self._resolve("asf-vote-candidate-state.json")
        stage_path = self.sandbox_dir / "asf-vote-stage.json"
        stage = StageGitHubCandidateResult(
            component=state.release.component.id,
            version=state.release.version,
            candidate=state.candidate,
            source_commit=state.source.commit_sha,
            publication=GitHubCandidatePublication(
                repository="buildish-tooling/buildish-example",
                release_id=43,
                release_url=(
                    "https://github.com/buildish-tooling/buildish-example/releases/tag/"
                    f"{state.candidate.tag.name}"
                ),
                tag=state.candidate.tag.name,
                draft=True,
                prerelease=False,
            ),
            outcome="created",
        )
        stage_path.write_text(stage.model_dump_json(indent=2) + "\n", encoding="utf-8")
        candidate_manifest_path = self.sandbox_dir / "candidate-manifest.json"
        completed = self._run(
            [
                "create-candidate-manifest",
                "--candidate-state",
                str(state_path),
                "--stage-result",
                str(stage_path),
            ],
            result_path=candidate_manifest_path,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        asf_config = (
            self.config_path.read_text(encoding="utf-8")
            .replace("  profile: generic", "  profile: asf")
            .replace(
                "policy_profiles: {}",
                "\n".join(
                    [
                        "policy_profiles:",
                        "  asf:",
                        "    project_status: tlp",
                        "    dist_dev_base: https://dist.apache.org/repos/dist/dev/buildish/example",
                        "    dist_release_base: https://dist.apache.org/repos/dist/release/buildish/example",
                        "    keys_url: https://downloads.apache.org/buildish/KEYS",
                    ]
                ),
            )
        )
        self.config_path.write_text(asf_config, encoding="utf-8")
        vote_path = self.sandbox_dir / "asf-vote-package.json"

        completed = self._run(
            [
                "create-vote-package",
                "--candidate-manifest",
                str(candidate_manifest_path),
                "--profile",
                "asf",
            ],
            result_path=vote_path,
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        vote = json.loads(vote_path.read_text(encoding="utf-8"))
        self.assertEqual("asf-vote", vote["extensions"][0]["kind"])
        self.assertEqual("pmc", vote["extensions"][0]["style"])
        self.assertEqual(
            "https://downloads.apache.org/buildish/KEYS",
            vote["extensions"][0]["keys"]["uri"],
        )
        self.assertEqual(
            state.candidate.tag.name,
            vote["embedded_candidate_manifest"]["candidate"]["tag"]["name"],
        )

    def test_exact_candidate_two_promotes_to_unsuffixed_final_release(self) -> None:
        git_create_annotated_tag(self.clone_dir, "v1.2.3-rc1")
        state_path, state = self._resolve("candidate-2-state.json")
        self.assertEqual("v1.2.3-rc2", state.candidate.tag.name)
        gh_path, gh_state_dir = self._fake_gh(
            state,
            list_response=[],
            create_tag_response={"sha": "a" * 40},
            create_ref_response={"ref": f"refs/tags/{state.candidate.tag.name}"},
        )
        completed = self._run(
            ["create-candidate-tag", "--candidate-state", str(state_path)],
            result_path=self.sandbox_dir / "candidate-2-tag.json",
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)

        draft = self._release(state, draft=True, prerelease=False, assets=[])
        gh_path, gh_state_dir = self._fake_gh(
            state,
            list_response=[],
            create_response=draft,
        )
        stage_path = self.sandbox_dir / "candidate-2-stage.json"
        completed = self._run(
            ["stage-github-candidate", "--candidate-state", str(state_path)],
            result_path=stage_path,
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)

        manifest_path = self.sandbox_dir / "candidate-manifest.json"
        completed = self._run(
            [
                "create-candidate-manifest",
                "--candidate-state",
                str(state_path),
                "--stage-result",
                str(stage_path),
            ],
            result_path=manifest_path,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest_text = manifest_path.read_text(encoding="utf-8")
        digest = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
        vote_package_path = self.sandbox_dir / "vote-package.json"
        completed = self._run(
            [
                "create-vote-package",
                "--candidate-manifest",
                str(manifest_path),
                "--profile",
                "generic",
            ],
            result_path=vote_package_path,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        vote_package = json.loads(vote_package_path.read_text(encoding="utf-8"))
        self.assertEqual(digest, vote_package["candidate_manifest"]["digest"])
        self.assertEqual("generic", vote_package["profile_selector"])
        self.assertEqual([], vote_package["extensions"])
        manifest_asset = {
            "id": 302,
            "name": "candidate-manifest.json",
            "size": manifest_path.stat().st_size,
            "digest": f"sha256:{digest}",
        }
        draft_with_manifest = self._release(
            state,
            draft=True,
            prerelease=False,
            assets=[manifest_asset],
        )
        gh_path, gh_state_dir = self._fake_gh(
            state,
            list_response=[draft],
            list_responses=([draft], [draft_with_manifest]),
        )
        completed = self._run(
            [
                "attach-github-candidate-manifest",
                "--candidate-state",
                str(state_path),
                "--candidate-manifest",
                str(manifest_path),
            ],
            result_path=self.sandbox_dir / "candidate-2-attach.json",
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)

        public_candidate = self._release(
            state,
            draft=False,
            prerelease=True,
            assets=[manifest_asset],
        )
        gh_path, gh_state_dir = self._fake_gh(
            state,
            list_response=[draft_with_manifest],
            list_responses=([draft_with_manifest], [public_candidate]),
            update_release_response=public_candidate,
            release_asset_text_by_id={302: manifest_text},
        )
        completed = self._run(
            [
                "finalize-github-candidate",
                "--candidate-tag",
                state.candidate.tag.name,
                "--candidate-manifest-digest",
                digest,
            ],
            result_path=self.sandbox_dir / "candidate-2-finalize.json",
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)

        promotion_path = self.sandbox_dir / "promotion-state.json"
        completed = self._run(
            [
                "resolve-promotion",
                "--candidate-tag",
                state.candidate.tag.name,
                "--candidate-manifest",
                str(manifest_path),
                "--candidate-manifest-digest",
                digest,
                "1.2.3",
            ],
            result_path=promotion_path,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        promotion = PromotionState.model_validate_json(
            promotion_path.read_text(encoding="utf-8")
        )
        self.assertEqual("v1.2.3", promotion.final_tag.name)
        self.assertEqual(state.candidate, promotion.candidate)

        gh_path, gh_state_dir = create_fake_gh_launcher(
            self.sandbox_dir,
            list_response=[public_candidate],
            create_tag_response={"sha": "e" * 40},
            create_ref_response={"ref": "refs/tags/v1.2.3"},
        )
        completed = self._run(
            ["create-final-tag", "--promotion-state", str(promotion_path)],
            result_path=self.sandbox_dir / "final-tag.json",
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)

        final_draft = {
            "id": 99,
            "tag_name": "v1.2.3",
            "name": "Buildish Example 1.2.3",
            "body": render_direct_final_release_body(promotion),
            "draft": True,
            "prerelease": False,
            "html_url": (
                "https://github.com/buildish-tooling/buildish-example/releases/tag/v1.2.3"
            ),
            "assets": [],
        }
        gh_path, gh_state_dir = self._fake_final_gh(
            promotion,
            list_response=[public_candidate],
            create_response=final_draft,
        )
        completed = self._run(
            ["stage-github-final-release", "--release-state", str(promotion_path)],
            result_path=self.sandbox_dir / "final-stage.json",
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)

        final_public = {**final_draft, "draft": False}
        gh_path, gh_state_dir = self._fake_final_gh(
            promotion,
            list_response=[final_draft, public_candidate],
            list_responses=(
                [final_draft, public_candidate],
                [final_public, public_candidate],
            ),
            update_release_response=final_public,
        )
        final_result_path = self.sandbox_dir / "final-publish.json"
        completed = self._run(
            ["publish-github-final-release", "--release-state", str(promotion_path)],
            result_path=final_result_path,
            gh_path=gh_path,
            gh_state_dir=gh_state_dir,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        result = json.loads(final_result_path.read_text(encoding="utf-8"))
        self.assertEqual("published", result["outcome"])
        self.assertEqual("v1.2.3", result["publication"]["tag"])

        release_manifest_path = self.sandbox_dir / "release-manifest.json"
        completed = self._run(
            [
                "create-release-manifest",
                "--release-state",
                str(promotion_path),
                "--publication-result",
                str(final_result_path),
            ],
            result_path=release_manifest_path,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        release_manifest = json.loads(release_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            "v1.2.3-rc2",
            release_manifest["promoted_candidate"]["candidate"]["tag"]["name"],
        )
        self.assertEqual(
            "same-source-revision",
            release_manifest["promotion_evidence"][0]["relation"],
        )


if __name__ == "__main__":
    unittest.main()
