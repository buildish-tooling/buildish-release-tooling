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
"""Release publication command integration tests."""

"""Shared support for release-publication command tests."""

from tests.release.commands.support import (
    Path,
    ReleaseCommandsIntegrationTestSupport,
    checkout_svn_repo,
    cleanup_sandbox,
    clone_git_origin,
    copy_test_tree,
    create_build_test_sandbox,
    init_git_origin_repo,
    init_svn_repo,
    json,
)


class ReleasePublicationCommandTestBase(ReleaseCommandsIntegrationTestSupport):
    """Shared Git and SVN fixtures for release-publication command tests."""

    _baseline_root: Path

    _origin_template: Path

    _svn_repo_template: Path

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._baseline_root = create_build_test_sandbox()
        cls._origin_template = init_git_origin_repo(
            cls._baseline_root, dir_name="origin-template"
        )
        cls._svn_repo_template, _repo_url = init_svn_repo(
            cls._baseline_root, dir_name="svnrepo-template"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_sandbox(cls._baseline_root)
        super().tearDownClass()

    def _create_git_sandbox(self) -> tuple[Path, Path, Path]:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir = copy_test_tree(self._origin_template, sandbox_dir / "origin")
        clone_dir = clone_git_origin(origin_dir, sandbox_dir / "clone")
        return sandbox_dir, origin_dir, clone_dir

    def _create_git_svn_sandbox(self) -> tuple[Path, Path, Path, Path, str, Path]:
        sandbox_dir, origin_dir, clone_dir = self._create_git_sandbox()
        repo_dir = copy_test_tree(self._svn_repo_template, sandbox_dir / "svnrepo")
        working_copy_dir = sandbox_dir / "svnwc"
        repo_url = checkout_svn_repo(repo_dir, working_copy_dir)
        return sandbox_dir, origin_dir, clone_dir, repo_dir, repo_url, working_copy_dir

    @staticmethod
    def _rc_vote_manifest_text(
        *,
        source_commit_sha: str,
        incubator_disclaimer_text: str | None = None,
        asf_keys_url: str = "https://dist.apache.org/repos/dist/release/incubator/example/KEYS",
    ) -> str:
        payload: dict[str, object] = {
            "schema_version": "1",
            "manifest_type": "rc-vote",
            "component_id": "example-project",
            "version": "1.2.3",
            "release_line": "1.2.x",
            "release_branch": "release/1.2.x",
            "source_repository_url": "https://github.com/apache/example-project",
            "source_commit_sha": source_commit_sha,
            "source_date_epoch": 1714132800,
            "rc_tag": "v1.2.3-rc0",
            "final_tag": "v1.2.3",
            "final_tag_mode": "rc-source-commit",
            "provenance": {
                "created_at": "2026-04-26T12:00:00Z",
                "tooling": {
                    "repository": "buildish-tooling/buildish-release-tooling",
                    "repository_url": "https://github.com/buildish-tooling/buildish-release-tooling",
                    "git_commit_sha": "fedcba9876543210fedcba9876543210fedcba98",
                },
            },
            "trust_roots": {
                "asf_keys": {
                    "uri": asf_keys_url,
                    "known_length_bytes": 9,
                    "known_prefix_sha512": "a" * 128,
                }
            },
            "draft_github_release": {
                "repository": "apache/example-project",
                "tag": "v1.2.3-rc0",
                "url": "https://github.com/apache/example-project/releases/tag/v1.2.3-rc0",
            },
            "vote_materials": {
                "source_artifacts": [
                    {
                        "role": "asf-source-release",
                        "filename": "apache-example-project-1.2.3-incubating-src.tar.gz",
                        "uri": (
                            "https://dist.apache.org/repos/dist/dev/incubator/example/example-project/"
                            "1.2.3-rc0/apache-example-project-1.2.3-incubating-src.tar.gz"
                        ),
                        "artifact_origin": "source-commit",
                        "git_commit_sha": source_commit_sha,
                        "checksums": {
                            "sha512": {
                                "value": "b" * 128,
                                "uri": (
                                    "https://dist.apache.org/repos/dist/dev/incubator/example/example-project/"
                                    "1.2.3-rc0/apache-example-project-1.2.3-incubating-src.tar.gz.sha512"
                                ),
                            }
                        },
                        "signatures": [
                            {
                                "type": "openpgp-detached-ascii-armored",
                                "uri": (
                                    "https://dist.apache.org/repos/dist/dev/incubator/example/example-project/"
                                    "1.2.3-rc0/apache-example-project-1.2.3-incubating-src.tar.gz.asc"
                                ),
                            }
                        ],
                    }
                ],
                "secondary_artifacts": [],
            },
            "verification": {
                "staging_svn_url": (
                    "https://dist.apache.org/repos/dist/dev/incubator/example/example-project/1.2.3-rc0/"
                ),
                "authoritative_manifest": {
                    "uri": (
                        "https://dist.apache.org/repos/dist/dev/incubator/example/example-project/"
                        "1.2.3-rc0/rc-vote-manifest.json"
                    ),
                    "checksum_uris": {
                        "sha512": (
                            "https://dist.apache.org/repos/dist/dev/incubator/example/example-project/"
                            "1.2.3-rc0/rc-vote-manifest.json.sha512"
                        )
                    },
                    "signatures": [
                        {
                            "type": "openpgp-detached-ascii-armored",
                            "uri": (
                                "https://dist.apache.org/repos/dist/dev/incubator/example/example-project/"
                                "1.2.3-rc0/rc-vote-manifest.json.asc"
                            ),
                        }
                    ],
                },
            },
        }
        if incubator_disclaimer_text is not None:
            payload["incubator_disclaimer"] = {
                "source_path": "DISCLAIMER",
                "text": incubator_disclaimer_text,
                "sha512": "c" * 128,
            }
        return json.dumps(payload)
