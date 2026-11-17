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

"""Regression tests for binding generated Git trees to reviewed source."""

from __future__ import annotations

import subprocess
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from buildish_release_tooling.release.config import ReleaseConfig
from buildish_release_tooling.release.core.config import TagPolicyConfig

from pydantic import ValidationError
from tests.support import run_cli, cli_env

from buildish_release_tooling.release.core.materialization import (
    MaterializationBinding,
    normalized_materialized_paths,
)
from buildish_release_tooling.release.core.models import (
    ComponentIdentity,
    ReleaseIdentity,
    SourceRevision,
    TagIdentity,
)
from buildish_release_tooling.release.core.state import (
    DirectReleaseState,
    CandidateReleaseState,
    PromotionState,
)
from buildish_release_tooling.release.manifests import (
    CandidateManifestV1,
    ReleaseManifestV1,
)
from buildish_release_tooling.release.git_repo import GitRepository
from buildish_release_tooling.release.materialized_content import (
    validate_materialized_commit,
    validate_materialized_state,
    export_materialization,
    import_materialization,
)


class MaterializedContentTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.git("init", "-b", "main")
        (self.root / "README.md").write_text("reviewed source\n")
        self.source = self.commit()
        (self.root / "dist").mkdir()
        (self.root / "dist/main.cjs").write_text("console.log('generated main');\n")
        self.materialized = self.commit()
        self.repo = GitRepository(self.root)

    def git(self, *args: str) -> str:
        return subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "core.hooksPath=/dev/null",
                *args,
            ],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()

    def commit(self, *args: str) -> str:
        self.git("add", "--all")
        self.git("commit", "-m", "fixture", *args)
        return self.git("rev-parse", "HEAD")

    def binding(self) -> MaterializationBinding:
        return MaterializationBinding(
            source_commit_sha=self.source,
            commit_sha=self.materialized,
            tree_sha=self.git("rev-parse", "HEAD^{tree}"),
            paths=["dist"],
            bundle_sha256="a" * 64,
        )

    def test_state_requires_explicit_binding_for_distinct_tag_target(self) -> None:
        payload = {
            "release": ReleaseIdentity(
                component=ComponentIdentity(id="example", display_name="Example"),
                version="1.2.3",
            ),
            "source": SourceRevision(
                commit_sha=self.source, repository="https://example.test/source"
            ),
            "final_tag": TagIdentity(
                name="v1.2.3", target_commit=self.materialized, purpose="final"
            ),
        }
        with self.assertRaises(ValidationError):
            DirectReleaseState.model_validate(payload)
        state = DirectReleaseState.model_validate(
            {**payload, "materialization": self.binding()}
        )
        self.assertEqual(self.source, state.source.commit_sha)
        self.assertEqual(self.materialized, state.final_tag.target_commit)
        encoded = state.model_dump_json()
        self.assertEqual(state, DirectReleaseState.model_validate_json(encoded))

    def test_direct_child_and_generated_tree_validate_without_checkout(self) -> None:
        head = self.git("rev-parse", "HEAD")
        self.assertEqual(
            self.binding().tree_sha,
            validate_materialized_commit(
                self.repo,
                source=self.source,
                commit=self.materialized,
                paths=["dist"],
            ),
        )
        self.assertEqual(head, self.git("rev-parse", "HEAD"))
        with self.assertRaisesRegex(ValueError, "tree"):
            validate_materialized_commit(
                self.repo,
                source=self.source,
                commit=self.materialized,
                paths=["dist"],
                tree="f" * 40,
            )

    def test_wrong_source_and_extra_commit_are_rejected(self) -> None:
        (self.root / "dist/post.cjs").write_text("console.log('post');\n")
        later = self.commit()
        with self.assertRaisesRegex(ValueError, "sole parent"):
            validate_materialized_commit(
                self.repo, source=self.source, commit=later, paths=["dist"]
            )
        payload = self.binding().model_dump()
        payload["source_commit_sha"] = "e" * 40
        with self.assertRaisesRegex(ValidationError, "selected source"):
            DirectReleaseState.model_validate(
                {
                    "release": {
                        "component": {"id": "example", "display_name": "Example"},
                        "version": "1.2.3",
                    },
                    "source": {
                        "commit_sha": self.source,
                        "repository": "https://example.test/source",
                    },
                    "materialization": payload,
                    "final_tag": {
                        "name": "v1.2.3",
                        "purpose": "final",
                        "target_commit": self.materialized,
                    },
                }
            )

    def test_path_changes_deletions_and_mode_changes_cannot_escape_policy(self) -> None:
        for mutation in ("modify", "delete", "mode"):
            with self.subTest(mutation=mutation):
                self.git("reset", "--hard", self.materialized)
                path = self.root / "README.md"
                if mutation == "modify":
                    path.write_text("unreviewed modification\n")
                elif mutation == "delete":
                    path.unlink()
                else:
                    path.chmod(0o755)
                self.commit("--amend", "--no-edit")
                with self.assertRaisesRegex(ValueError, "outside trusted policy"):
                    validate_materialized_commit(
                        self.repo,
                        source=self.source,
                        commit=self.git("rev-parse", "HEAD"),
                        paths=["dist"],
                    )

    def test_symlink_payloads_and_unsafe_policy_paths_are_rejected(self) -> None:
        (self.root / "dist/link").symlink_to("../README.md")
        self.commit("--amend", "--no-edit")
        with self.assertRaisesRegex(ValueError, "regular files"):
            validate_materialized_commit(
                self.repo,
                source=self.source,
                commit=self.git("rev-parse", "HEAD"),
                paths=["dist"],
            )
        for path in (
            ".",
            "../dist",
            "/dist",
            "dist/../src",
            "dist/*",
            ":(glob)**",
            "dist/",
            ".git/config",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                normalized_materialized_paths([path])

    def test_all_lifecycle_states_and_manifests_preserve_separate_identities(
        self,
    ) -> None:
        base = {
            "release": {
                "component": {"id": "example", "display_name": "Example"},
                "version": "1.2.3",
            },
            "source": {
                "commit_sha": self.source,
                "repository": "https://example.test/source",
            },
            "materialization": self.binding().model_dump(),
        }
        candidate_tag = {
            "name": "v1.2.3-rc1",
            "target_commit": self.materialized,
            "purpose": "candidate",
        }
        final_tag = {
            "name": "v1.2.3",
            "target_commit": self.materialized,
            "purpose": "final",
        }
        candidate = {
            "release": base["release"],
            "label": "rc",
            "number": 1,
            "tag": candidate_tag,
        }
        stable = {"tooling": {}, "created_at": "2026-11-17T00:00:00Z"}
        payloads = (
            (
                CandidateReleaseState,
                {
                    **base,
                    "source_date_epoch": 1,
                    "candidate": candidate,
                    "final_tag_identity": final_tag,
                },
            ),
            (
                PromotionState,
                {
                    **base,
                    "source_date_epoch": 1,
                    "candidate": candidate,
                    "candidate_manifest_digest": "a" * 64,
                    "final_tag": final_tag,
                },
            ),
            (
                CandidateManifestV1,
                {
                    **base,
                    **stable,
                    "candidate": candidate,
                    "candidate_tag": candidate_tag,
                },
            ),
            (ReleaseManifestV1, {**base, **stable, "final_tag": final_tag}),
        )
        for model, payload in payloads:
            with self.subTest(model=model.__name__):
                instance = model.model_validate(payload)
                self.assertEqual(self.source, instance.source.commit_sha)
                self.assertEqual(self.binding(), instance.materialization)
                self.assertEqual(
                    instance, model.model_validate_json(instance.model_dump_json())
                )
                unbound = dict(payload)
                unbound.pop("materialization")
                with self.assertRaises(ValidationError):
                    model.model_validate(unbound)

    def test_trusted_policy_is_required_independently_of_serialized_binding(
        self,
    ) -> None:
        config = ReleaseConfig.model_validate(
            {
                "component": {"id": "example", "display_name": "Example"},
                "source": {"selection": "explicit-ref", "snapshot": {"mode": "none"}},
                "lifecycle": {"mode": "direct"},
                "publication": {
                    "authoritative": {
                        "kind": "github-release",
                        "repository": "example/example",
                    }
                },
            }
        )
        state = DirectReleaseState.model_validate(
            {
                "release": {
                    "component": {"id": "example", "display_name": "Example"},
                    "version": "1.2.3",
                },
                "source": {
                    "repository": "https://example.test/source",
                    "commit_sha": self.source,
                },
                "final_tag": {
                    "name": "v1.2.3",
                    "purpose": "final",
                    "target_commit": self.materialized,
                },
                "materialization": self.binding(),
            }
        )
        with self.assertRaisesRegex(ValueError, "not permitted"):
            validate_materialized_state(self.repo, config, state)
        config.tags = TagPolicyConfig(
            final_mode="detached-materialization-commit", materialized_paths=["other"]
        )
        with self.assertRaisesRegex(ValueError, "trusted tags.materialized_paths"):
            validate_materialized_state(self.repo, config, state)
        config.tags = TagPolicyConfig(
            final_mode="detached-materialization-commit", materialized_paths=["dist"]
        )
        validate_materialized_state(self.repo, config, state)
        pending = state.model_dump()
        pending.pop("materialization")
        pending["final_tag"]["target_commit"] = self.source
        with self.assertRaisesRegex(ValueError, "requires a bound"):
            validate_materialized_state(
                self.repo, config, DirectReleaseState.model_validate(pending)
            )
        config.tags = TagPolicyConfig()
        validate_materialized_state(
            self.repo, config, DirectReleaseState.model_validate(pending)
        )

    def test_replace_refs_cannot_change_the_object_under_validation(self) -> None:
        original_tree = self.binding().tree_sha
        (self.root / "README.md").write_text("replacement must not be used\n")
        replacement = self.commit("--amend", "--no-edit")
        self.git("replace", self.materialized, replacement)
        self.assertEqual(
            original_tree,
            validate_materialized_commit(
                self.repo,
                source=self.source,
                commit=self.materialized,
                paths=["dist"],
                tree=original_tree,
            ),
        )

    def test_git_configuration_cannot_hide_changes_outside_the_policy(self) -> None:
        self.git(
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{self.source},external-link",
        )
        self.git("commit", "--amend", "--no-edit")
        commit = self.git("rev-parse", "HEAD")
        with (
            mock.patch.dict(
                "os.environ",
                {
                    "GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "diff.ignoreSubmodules",
                    "GIT_CONFIG_VALUE_0": "all",
                },
            ),
            self.assertRaisesRegex(ValueError, "outside trusted policy"),
        ):
            validate_materialized_commit(
                self.repo, source=self.source, commit=commit, paths=["dist"]
            )

    def transport_fixture(self) -> tuple[ReleaseConfig, DirectReleaseState, Path]:
        config = ReleaseConfig.model_validate(
            {
                "component": {"id": "example", "display_name": "Example"},
                "source": {"selection": "explicit-ref", "snapshot": {"mode": "none"}},
                "lifecycle": {"mode": "direct"},
                "publication": {
                    "authoritative": {
                        "kind": "github-release",
                        "repository": "example/example",
                    }
                },
                "tags": {
                    "final_mode": "detached-materialization-commit",
                    "materialized_paths": ["dist"],
                },
            }
        )
        state = DirectReleaseState.model_validate(
            {
                "release": {
                    "component": {"id": "example", "display_name": "Example"},
                    "version": "1.2.3",
                },
                "source": {
                    "repository": "https://example.test/source",
                    "commit_sha": self.source,
                },
                "final_tag": {
                    "name": "v1.2.3",
                    "purpose": "final",
                    "target_commit": self.source,
                },
            }
        )
        bundle = self.root / "build/materialized.bundle"
        binding = export_materialization(
            self.repo, config, state, commit=self.materialized, bundle=bundle
        )
        payload = state.model_dump()
        payload["materialization"] = binding
        payload["final_tag"]["target_commit"] = self.materialized
        return config, DirectReleaseState.model_validate(payload), bundle

    def test_shallow_materialized_checkout_accepts_separately_fetched_source(
        self,
    ) -> None:
        consumer = self.root / "build/shallow-materialized"
        subprocess.run(
            [
                "git",
                "clone",
                "--depth=1",
                "--no-tags",
                self.root.as_uri(),
                str(consumer),
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(consumer), "fetch", "--depth=1", "origin", self.source],
            check=True,
            capture_output=True,
        )
        hidden = subprocess.run(
            [
                "git",
                "-C",
                str(consumer),
                "rev-list",
                "--parents",
                "-n",
                "1",
                self.materialized,
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()
        self.assertEqual([self.materialized], hidden)
        tree = validate_materialized_commit(
            GitRepository(consumer),
            source=self.source,
            commit=self.materialized,
            paths=["dist"],
        )
        self.assertEqual(self.git("rev-parse", f"{self.materialized}^{{tree}}"), tree)

    def test_bundle_import_into_independent_shallow_source_checkout_preserves_head(
        self,
    ) -> None:
        config, state, bundle = self.transport_fixture()
        self.git("branch", "source-only", self.source)
        consumer = self.root / "build/consumer"
        subprocess.run(
            [
                "git",
                "clone",
                "--no-local",
                "--depth=1",
                "--branch",
                "source-only",
                self.root.as_uri(),
                str(consumer),
            ],
            check=True,
            capture_output=True,
        )
        repo = GitRepository(consumer)
        missing = subprocess.run(
            ["git", "-C", str(consumer), "cat-file", "-e", self.materialized],
            capture_output=True,
        )
        self.assertNotEqual(0, missing.returncode)
        with self.assertRaisesRegex(ValueError, "producer bundle digest"):
            import_materialization(
                repo, config, state, bundle=bundle, expected_sha256="0" * 64
            )
        if state.materialization is None:
            self.fail("missing binding")
        digest = state.materialization.bundle_sha256
        state_file = self.root / "bound-state.json"
        config_file = self.root / "config.yaml"
        result_file = self.root / "imported-state.json"
        state_file.write_text(state.model_dump_json())
        config_file.write_text(config.model_dump_json(exclude_none=True))
        original_file = self.root / "original-state.json"
        original_payload = state.model_dump(mode="json")
        original_payload["materialization"] = None
        original_payload["final_tag"]["target_commit"] = self.source
        original_file.write_text(json.dumps(original_payload))
        substituted = state.model_dump(mode="json")
        substituted["source"]["commit_sha"] = "e" * 40
        substituted["materialization"]["source_commit_sha"] = "e" * 40
        state_file.write_text(json.dumps(substituted))
        rejected = run_cli(
            [
                "import-materialization",
                "--component-config",
                str(config_file),
                "--release-state",
                str(state_file),
                "--source-state",
                str(original_file),
                "--bundle",
                str(bundle),
                "--bundle-sha256",
                digest,
            ],
            cwd=consumer,
            env=cli_env(result_file),
        )
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn("original trusted source state", rejected.stderr)
        absent = subprocess.run(
            ["git", "-C", str(consumer), "cat-file", "-e", self.materialized],
            capture_output=True,
        )
        self.assertNotEqual(0, absent.returncode)
        state_file.write_text(state.model_dump_json())
        result = run_cli(
            [
                "import-materialization",
                "--component-config",
                str(config_file),
                "--release-state",
                str(state_file),
                "--source-state",
                str(original_file),
                "--bundle",
                str(bundle),
                "--bundle-sha256",
                digest,
            ],
            cwd=consumer,
            env=cli_env(result_file),
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            state, DirectReleaseState.model_validate_json(result_file.read_text())
        )
        self.assertEqual(self.source, repo.current_head_commit())
        self.assertEqual(self.materialized, repo.resolve_commit(self.materialized))
        # An identical rerun imports the same M; it does not regenerate a commit.
        import_materialization(
            repo, config, state, bundle=bundle, expected_sha256=digest
        )
        self.assertEqual(self.source, repo.current_head_commit())
        config.tags = TagPolicyConfig()
        with mock.patch(
            "buildish_release_tooling.release.materialized_content.git_output"
        ) as git:
            with self.assertRaisesRegex(ValueError, "not permitted"):
                import_materialization(
                    repo, config, state, bundle=bundle, expected_sha256=digest
                )
            git.assert_not_called()

    def test_bundle_corruption_and_retention_loss_fail_without_regeneration(
        self,
    ) -> None:
        config, state, bundle = self.transport_fixture()
        binding = state.materialization
        if binding is None:
            self.fail("missing binding")
        self.assertEqual(
            binding,
            export_materialization(
                self.repo, config, state, commit=self.materialized, bundle=bundle
            ),
        )
        original = bundle.read_bytes()
        bundle.write_bytes(original + b"corruption")
        with self.assertRaisesRegex(ValueError, "bundle bytes"):
            import_materialization(
                self.repo,
                config,
                state,
                bundle=bundle,
                expected_sha256=binding.bundle_sha256,
            )
        with self.assertRaisesRegex(ValueError, "retain the original"):
            export_materialization(
                self.repo, config, state, commit=self.materialized, bundle=bundle
            )
        bundle.unlink()
        with self.assertRaisesRegex(ValueError, "retain the original"):
            export_materialization(
                self.repo, config, state, commit=self.materialized, bundle=bundle
            )

    def test_build_producer_cannot_change_the_original_source_state(self) -> None:
        from buildish_release_tooling.release.materialized_content import (
            validate_original_state,
        )

        _config, state, _bundle = self.transport_fixture()
        original = state.model_dump(mode="json")
        original["materialization"] = None
        original["final_tag"]["target_commit"] = self.source
        trusted = DirectReleaseState.model_validate(original)
        validate_original_state(state, trusted)
        for field, value in (
            ("source", {**original["source"], "commit_sha": "e" * 40}),
            ("release", {**original["release"], "version": "9.9.9"}),
        ):
            with self.subTest(field=field):
                changed = state.model_dump(mode="json")
                changed[field] = value
                if field == "source":
                    changed["materialization"]["source_commit_sha"] = "e" * 40
                with self.assertRaisesRegex(
                    ValueError, "original trusted source state"
                ):
                    validate_original_state(
                        DirectReleaseState.model_validate(changed), trusted
                    )

    def test_trusted_remote_object_publication_is_immutable_and_race_safe(self) -> None:
        from buildish_release_tooling.release.git_materialization import (
            publish_materialized_ref,
        )
        from buildish_release_tooling.release.process import (
            CommandExecutionError,
            run_logged_command,
        )

        remote = self.root / "build/remote.git"
        remote.parent.mkdir()
        self.git("init", "--bare", str(remote))
        self.git("remote", "add", "origin", "https://github.com/example/example.git")
        self.git(
            "config",
            f"url.{remote.as_uri()}.insteadOf",
            "https://github.com/example/example.git",
        )
        ref = f"refs/heads/buildish-internal/materialized/{self.materialized}"
        self.assertEqual(
            "pushed",
            publish_materialized_ref(
                self.repo,
                repository_slug="example/example",
                commit_sha=self.materialized,
            ),
        )
        self.assertEqual(
            "already-present",
            publish_materialized_ref(
                self.repo,
                repository_slug="example/example",
                commit_sha=self.materialized,
            ),
        )
        self.assertEqual(
            self.materialized, self.git("--git-dir", str(remote), "rev-parse", ref)
        )
        self.git("--git-dir", str(remote), "update-ref", "-d", ref)

        def race(argv, **kwargs):
            if "push" in argv:
                self.git("--git-dir", str(remote), "update-ref", ref, self.source)
            return run_logged_command(argv, **kwargs)

        with mock.patch(
            "buildish_release_tooling.release.git_materialization.run_logged_command",
            side_effect=race,
        ):
            with self.assertRaises(CommandExecutionError):
                publish_materialized_ref(
                    self.repo,
                    repository_slug="example/example",
                    commit_sha=self.materialized,
                )
        self.assertEqual(
            self.source, self.git("--git-dir", str(remote), "rev-parse", ref)
        )
        with self.assertRaisesRegex(ValueError, "conflicts"):
            publish_materialized_ref(
                self.repo,
                repository_slug="example/example",
                commit_sha=self.materialized,
            )

    def test_built_source_and_platform_snapshot_follow_their_distinct_git_identities(
        self,
    ) -> None:
        import tarfile
        from buildish_release_tooling.release.source_artifact import create_from_git

        built_source = self.root / "build/source.tar.gz"
        platform_equivalent = self.root / "build/tagged-tree.tar.gz"
        create_from_git(self.root, self.source, "example/", built_source)
        create_from_git(self.root, self.materialized, "example/", platform_equivalent)
        with tarfile.open(built_source) as archive:
            self.assertNotIn("example/dist/main.cjs", archive.getnames())
        with tarfile.open(platform_equivalent) as archive:
            self.assertIn("example/dist/main.cjs", archive.getnames())

    def test_merge_and_unrelated_commits_cannot_be_materialization(self) -> None:
        tree = self.binding().tree_sha
        merge = self.git(
            "commit-tree",
            tree,
            "-p",
            self.source,
            "-p",
            self.materialized,
            "-m",
            "merge",
        )
        unrelated = self.git("commit-tree", tree, "-m", "unrelated")
        for commit in (merge, unrelated, self.source):
            with (
                self.subTest(commit=commit),
                self.assertRaisesRegex(ValueError, "sole parent"),
            ):
                validate_materialized_commit(
                    self.repo, source=self.source, commit=commit, paths=["dist"]
                )

    def test_remote_tag_conflicts_are_rejected_before_generated_ref_publication(
        self,
    ) -> None:
        from buildish_release_tooling.release.materialized_content import (
            publish_materialized_objects,
        )

        config, state, _bundle = self.transport_fixture()
        remote = self.root / "build/tag-origin.git"
        self.git("init", "--bare", str(remote))
        self.git("remote", "add", "origin", "https://github.com/example/example.git")
        self.git(
            "config",
            f"url.{remote.as_uri()}.insteadOf",
            "https://github.com/example/example.git",
        )
        ref = f"refs/heads/buildish-internal/materialized/{self.materialized}"
        for annotated in (True, False):
            with self.subTest(annotated=annotated):
                if annotated:
                    self.git(
                        "tag", "-a", "v1.2.3", "-m", "conflicting tag", self.source
                    )
                else:
                    self.git("tag", "v1.2.3", self.materialized)
                self.git("push", remote.as_uri(), "refs/tags/v1.2.3")
                self.git("tag", "-d", "v1.2.3")
                with self.assertRaisesRegex(
                    ValueError, "existing remote tag conflicts"
                ):
                    publish_materialized_objects(
                        self.repo,
                        config,
                        state,
                        repository="example/example",
                        tag="v1.2.3",
                    )
                missing = subprocess.run(
                    [
                        "git",
                        "--git-dir",
                        str(remote),
                        "show-ref",
                        "--verify",
                        "--quiet",
                        ref,
                    ],
                    capture_output=True,
                )
                self.assertNotEqual(0, missing.returncode)
                self.git(
                    "--git-dir", str(remote), "update-ref", "-d", "refs/tags/v1.2.3"
                )

    def test_configured_publication_repository_wins_over_fork_origin_without_token(
        self,
    ) -> None:
        from buildish_release_tooling.release.git_materialization import (
            publish_materialized_ref,
        )

        approved = self.root / "approved.git"
        fork = self.root / "fork.git"
        for destination in (approved, fork):
            self.git("init", "--bare", str(destination))
        self.git("remote", "add", "origin", "git@github.com:contributor/fork.git")
        # Both endpoints are redirected locally so even a regression cannot use the network.
        self.git(
            "config",
            f"url.{approved.as_uri()}.insteadOf",
            "https://github.com/upstream/project.git",
        )
        self.git(
            "config",
            f"url.{fork.as_uri()}.insteadOf",
            "git@github.com:contributor/fork.git",
        )
        with mock.patch.dict("os.environ", {"GH_TOKEN": "", "GITHUB_TOKEN": ""}):
            publish_materialized_ref(
                self.repo,
                repository_slug="upstream/project",
                commit_sha=self.materialized,
            )
        ref = f"refs/heads/buildish-internal/materialized/{self.materialized}"
        self.assertEqual(
            self.materialized, self.git("--git-dir", str(approved), "rev-parse", ref)
        )
        missing = subprocess.run(
            ["git", "--git-dir", str(fork), "show-ref", "--verify", "--quiet", ref],
            capture_output=True,
        )
        self.assertNotEqual(0, missing.returncode)
