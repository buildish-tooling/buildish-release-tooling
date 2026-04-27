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

"""Integration tests for the CLI command surface.

This file is the broadest command-contract suite in the repository. Most tests exercise the real
CLI entrypoint against temporary Git repositories, local SVN repositories, fake GitHub CLIs, and
temporary GPG material so that command orchestration is covered end to end.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import unittest
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast
from unittest import mock

from apache_buildish_release_tooling.release.asf_svn import AsfSvnClient
from apache_buildish_release_tooling.release.git_materialization import (
    delete_remote_ref_best_effort,
    push_remote_ref,
)

from tests.support import (
    cli_env,
    cleanup_sandbox,
    command_available,
    create_build_test_sandbox,
    create_fake_atr_launcher,
    create_fake_docker_launcher,
    create_fake_gh_launcher,
    fetch_git_origin_refs,
    git_create_annotated_tag,
    git_create_branch,
    git_rev_parse,
    init_git_origin_and_clone,
    init_svn_repo_and_checkout,
    run_cli,
    set_github_origin_url,
)


def _read_simple_github_outputs(path: Path) -> dict[str, str]:
    """Return one simple key/value mapping from a GitHub step output file."""

    outputs: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        key, value = line.split("=", 1)
        outputs[key] = value
    return outputs


def _write_sha512_sidecar(target_path: Path) -> None:
    """Write a Maven-style bare SHA512 sidecar next to one file."""

    digest_value = hashlib.sha512(target_path.read_bytes()).hexdigest()
    target_path.with_name(f"{target_path.name}.sha512").write_text(
        f"{digest_value}\n",
        encoding="utf-8",
    )


def _write_test_maven_repository(root_path: Path) -> tuple[dict[str, str], dict[str, int]]:
    """Create one small file-based Maven repository snapshot for artifact-registration tests."""

    expected_sha512_by_path: dict[str, str] = {}
    expected_sizes_by_path: dict[str, int] = {}

    def write_text(relative_path: str, text: str) -> Path:
        local_path = root_path / relative_path
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(text, encoding="utf-8")
        expected_sha512_by_path[relative_path] = hashlib.sha512(text.encode("utf-8")).hexdigest()
        expected_sizes_by_path[relative_path] = len(text.encode("utf-8"))
        return local_path

    def write_bytes(relative_path: str, payload: bytes) -> Path:
        local_path = root_path / relative_path
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(payload)
        expected_sha512_by_path[relative_path] = hashlib.sha512(payload).hexdigest()
        expected_sizes_by_path[relative_path] = len(payload)
        return local_path

    archetype_catalog = write_text("archetype-catalog.xml", "<archetypes/>\n")
    _write_sha512_sidecar(archetype_catalog)
    expected_sha512_by_path["archetype-catalog.xml.sha512"] = hashlib.sha512(
        archetype_catalog.with_name("archetype-catalog.xml.sha512").read_bytes()
    ).hexdigest()
    expected_sizes_by_path["archetype-catalog.xml.sha512"] = archetype_catalog.with_name(
        "archetype-catalog.xml.sha512"
    ).stat().st_size

    metadata = write_text(
        "org/apache/example/example-artifact/maven-metadata.xml",
        "<metadata><versioning><release>1.2.3</release></versioning></metadata>\n",
    )
    _write_sha512_sidecar(metadata)
    expected_sha512_by_path[
        "org/apache/example/example-artifact/maven-metadata.xml.sha512"
    ] = hashlib.sha512(metadata.with_name("maven-metadata.xml.sha512").read_bytes()).hexdigest()
    expected_sizes_by_path[
        "org/apache/example/example-artifact/maven-metadata.xml.sha512"
    ] = metadata.with_name("maven-metadata.xml.sha512").stat().st_size

    jar_path = write_bytes(
        "org/apache/example/example-artifact/1.2.3/example-artifact-1.2.3.jar",
        b"jar payload\n",
    )
    _write_sha512_sidecar(jar_path)
    expected_sha512_by_path[
        "org/apache/example/example-artifact/1.2.3/example-artifact-1.2.3.jar.sha512"
    ] = hashlib.sha512(jar_path.with_name("example-artifact-1.2.3.jar.sha512").read_bytes()).hexdigest()
    expected_sizes_by_path[
        "org/apache/example/example-artifact/1.2.3/example-artifact-1.2.3.jar.sha512"
    ] = jar_path.with_name("example-artifact-1.2.3.jar.sha512").stat().st_size
    jar_path.with_name("example-artifact-1.2.3.jar.md5").write_text(
        "d41d8cd98f00b204e9800998ecf8427e\n",
        encoding="utf-8",
    )
    expected_sha512_by_path[
        "org/apache/example/example-artifact/1.2.3/example-artifact-1.2.3.jar.md5"
    ] = hashlib.sha512(jar_path.with_name("example-artifact-1.2.3.jar.md5").read_bytes()).hexdigest()
    expected_sizes_by_path[
        "org/apache/example/example-artifact/1.2.3/example-artifact-1.2.3.jar.md5"
    ] = jar_path.with_name("example-artifact-1.2.3.jar.md5").stat().st_size

    jar_signature = write_text(
        "org/apache/example/example-artifact/1.2.3/example-artifact-1.2.3.jar.asc",
        "-----BEGIN PGP SIGNATURE-----\nabc123\n-----END PGP SIGNATURE-----\n",
    )
    _write_sha512_sidecar(jar_signature)
    expected_sha512_by_path[
        "org/apache/example/example-artifact/1.2.3/example-artifact-1.2.3.jar.asc.sha512"
    ] = hashlib.sha512(jar_signature.with_name("example-artifact-1.2.3.jar.asc.sha512").read_bytes()).hexdigest()
    expected_sizes_by_path[
        "org/apache/example/example-artifact/1.2.3/example-artifact-1.2.3.jar.asc.sha512"
    ] = jar_signature.with_name("example-artifact-1.2.3.jar.asc.sha512").stat().st_size

    pom_path = write_text(
        "org/apache/example/example-artifact/1.2.3/example-artifact-1.2.3.pom",
        "<project><modelVersion>4.0.0</modelVersion></project>\n",
    )
    _write_sha512_sidecar(pom_path)
    expected_sha512_by_path[
        "org/apache/example/example-artifact/1.2.3/example-artifact-1.2.3.pom.sha512"
    ] = hashlib.sha512(pom_path.with_name("example-artifact-1.2.3.pom.sha512").read_bytes()).hexdigest()
    expected_sizes_by_path[
        "org/apache/example/example-artifact/1.2.3/example-artifact-1.2.3.pom.sha512"
    ] = pom_path.with_name("example-artifact-1.2.3.pom.sha512").stat().st_size

    return expected_sha512_by_path, expected_sizes_by_path


class CommandCredentialHandlingUnitTest(unittest.TestCase):
    """Verify credential-sensitive command construction without real subprocesses."""

    def test_push_remote_ref_uses_git_askpass_for_github_https_pushes(self) -> None:
        repo = mock.Mock()
        repo.path = Path("/sandbox/repo")
        repo.remote_url.return_value = "git@github.com:apache/buildish-example.git"
        seen_script_path: Path | None = None

        def fake_run_logged_command(
            command: Sequence[str],
            **kwargs: Any,
        ) -> subprocess.CompletedProcess[str]:
            nonlocal seen_script_path
            self.assertEqual(
                [
                    "git",
                    "-C",
                    "/sandbox/repo",
                    "push",
                    "https://github.com/apache/buildish-example.git",
                    "HEAD:refs/buildish/test",
                ],
                command,
            )
            self.assertNotIn("gh-secret-token", "".join(command))
            self.assertEqual(["gh-secret-token"], cast(Sequence[str], kwargs["extra_secret_values"]))
            env = cast(Mapping[str, str], kwargs["env"])
            self.assertEqual("0", env["GIT_TERMINAL_PROMPT"])
            self.assertEqual("", env["GH_TOKEN"])
            self.assertEqual("", env["GITHUB_TOKEN"])
            self.assertEqual("gh-secret-token", env["BUILDISH_GIT_ASKPASS_TOKEN"])
            self.assertEqual("x-access-token", env["BUILDISH_GIT_ASKPASS_USERNAME"])
            seen_script_path = Path(env["GIT_ASKPASS"])
            self.assertTrue(seen_script_path.is_file())
            self.assertEqual(
                "\n".join(
                    [
                        "#!/bin/sh",
                        "set -eu",
                        'prompt="${1-}"',
                        'case "$prompt" in',
                        "  *Username*|*username*)",
                        '    printf \'%s\\n\' "${BUILDISH_GIT_ASKPASS_USERNAME:-x-access-token}"',
                        "    ;;",
                        "  *)",
                        '    printf \'%s\\n\' "${BUILDISH_GIT_ASKPASS_TOKEN:?}"',
                        "    ;;",
                        "esac",
                        "",
                    ]
                ),
                seen_script_path.read_text(encoding="utf-8"),
            )
            return subprocess.CompletedProcess(list(command), 0, "", "")

        with (
            mock.patch.dict(os.environ, {"GITHUB_TOKEN": "gh-secret-token"}, clear=False),
            mock.patch(
                "apache_buildish_release_tooling.release.git_materialization.run_logged_command",
                side_effect=fake_run_logged_command,
            ),
        ):
            actual = push_remote_ref(
                repo,
                repository_slug="apache/buildish-example",
                source_ref="HEAD",
                target_ref="refs/buildish/test",
                force=False,
            )

        self.assertEqual("pushed", actual)
        self.assertIsNotNone(seen_script_path)
        if seen_script_path is None:
            self.fail("expected askpass helper path to be captured")
        self.assertFalse(seen_script_path.exists())

    def test_delete_remote_ref_best_effort_uses_git_askpass_for_github_https_pushes(self) -> None:
        repo = mock.Mock()
        repo.path = Path("/sandbox/repo")
        repo.remote_url.return_value = "git@github.com:apache/buildish-example.git"
        seen_script_path: Path | None = None

        def fake_run_logged_command(
            command: Sequence[str],
            **kwargs: Any,
        ) -> subprocess.CompletedProcess[str]:
            nonlocal seen_script_path
            self.assertEqual(
                [
                    "git",
                    "-C",
                    "/sandbox/repo",
                    "push",
                    "https://github.com/apache/buildish-example.git",
                    ":refs/buildish/test",
                ],
                command,
            )
            env = cast(Mapping[str, str], kwargs["env"])
            seen_script_path = Path(env["GIT_ASKPASS"])
            self.assertTrue(seen_script_path.is_file())
            return subprocess.CompletedProcess(list(command), 0, "", "")

        with (
            mock.patch.dict(os.environ, {"GH_TOKEN": "gh-secret-token"}, clear=False),
            mock.patch(
                "apache_buildish_release_tooling.release.git_materialization.run_logged_command",
                side_effect=fake_run_logged_command,
            ),
        ):
            actual = delete_remote_ref_best_effort(
                repo,
                repository_slug="apache/buildish-example",
                ref_name="refs/buildish/test",
            )

        self.assertEqual("deleted", actual)
        self.assertIsNotNone(seen_script_path)
        if seen_script_path is None:
            self.fail("expected askpass helper path to be captured")
        self.assertFalse(seen_script_path.exists())


class CommandsIntegrationTest(unittest.TestCase):
    """Verify high-level command behavior through the CLI entrypoint."""

    @staticmethod
    def _write_component_config(
        config_path: Path,
        *,
        component_id: str,
        dev_base_url: str,
        release_base_url: str,
        vote_release_name: str = "Apache Buildish Example",
        moving_tags_enabled: bool = True,
        latest_tag_enabled: bool = False,
        secondary_targets: tuple[str, ...] = ("github-action",),
        final_tag_mode: str = "rc-source-commit",
        atr_lines: tuple[str, ...] = (),
    ) -> None:
        """Write a minimal component configuration used by CLI integration tests."""

        config_path.write_text(
            "\n".join(
                [
                    f"component_id: {component_id}",
                    f"source_artifact_prefix: apache-{component_id}",
                    f"asf_dist_dev_base: {dev_base_url}",
                    f"asf_dist_release_base: {release_base_url}",
                    f"moving_tags_enabled: {'true' if moving_tags_enabled else 'false'}",
                    f"latest_tag_enabled: {'true' if latest_tag_enabled else 'false'}",
                    "secondary_targets:",
                    *[f"  - {target}" for target in secondary_targets],
                    f"final_tag_mode: {final_tag_mode}",
                    f"vote_release_name: {vote_release_name}",
                    "release_verification_guide_url: https://buildish.apache.org/buildish-example/release-verification/",
                    "verify_rc_instructions: verify",
                    "prepare_rc_runs_tests: false",
                    "release_branch_ci_required: true",
                    *atr_lines,
                ]
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _stage_source_release_files(
        sandbox_dir: Path,
        working_copy_dir: Path,
        *,
        component_id: str,
        version: str,
        rc_number: int,
    ) -> str:
        """Stage the minimal ASF source-release files in one SVN working copy RC directory."""

        client = AsfSvnClient()
        subprocess.run(["svn", "update", str(working_copy_dir)], check=True, capture_output=True, text=True)
        artifact_name = f"apache-{component_id}-{version}-incubating-src.tar.gz"
        artifact_path = sandbox_dir / artifact_name
        artifact_bytes = b"dummy source payload\n"
        artifact_path.write_bytes(artifact_bytes)
        artifact_sha512 = hashlib.sha512(artifact_bytes).hexdigest()
        sha512_path = sandbox_dir / f"{artifact_name}.sha512"
        sha512_path.write_text(f"{artifact_sha512}  {artifact_name}\n", encoding="utf-8")
        asc_path = sandbox_dir / f"{artifact_name}.asc"
        asc_path.write_text("-----BEGIN PGP SIGNATURE-----\n<dummy>\n-----END PGP SIGNATURE-----\n", encoding="utf-8")
        target_dir = (
            working_copy_dir
            / "dist"
            / "dev"
            / "incubator"
            / "buildish"
            / component_id
            / f"{version}-rc{rc_number}"
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["svn", "add", "--force", str(target_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
        for source_path, destination_name in (
            (artifact_path, artifact_name),
            (sha512_path, f"{artifact_name}.sha512"),
            (asc_path, f"{artifact_name}.asc"),
        ):
            destination_path = target_dir / destination_name
            destination_path.write_bytes(source_path.read_bytes())
            subprocess.run(
                ["svn", "add", "--force", str(destination_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        client.commit_working_copy(working_copy_dir, "stage source release files")
        return artifact_sha512

    @staticmethod
    def _stage_rc_vote_manifest_files(
        working_copy_dir: Path,
        *,
        component_id: str,
        version: str,
        rc_number: int,
        repo_url: str,
        artifact_sha512: str,
    ) -> str:
        """Stage one RC vote manifest plus sidecars in the RC SVN directory."""

        manifest_text = json.dumps(
            {
                "schema_version": "1",
                "manifest_type": "rc-vote",
                "component_id": component_id,
                "version": version,
                "release_line": "1.2.x",
                "release_branch": "release/1.2.x",
                "source_commit_sha": "0123456789abcdef0123456789abcdef01234567",
                "rc_tag": f"v{version}-rc{rc_number}",
                "final_tag": f"v{version}",
                "final_tag_mode": "rc-source-commit",
                "provenance": {"created_at": "2026-04-26T12:00:00Z", "tooling": {}},
                "trust_roots": {
                    "asf_keys": {
                        "uri": "https://downloads.apache.org/incubator/buildish/KEYS",
                        "known_length_bytes": 9,
                        "known_prefix_sha512": "abc123",
                    }
                },
                "draft_github_release": {
                    "repository": "apache/buildish-example",
                    "tag": f"v{version}-rc{rc_number}",
                    "url": f"https://github.com/apache/buildish-example/releases/tag/v{version}-rc{rc_number}",
                },
                "vote_materials": {
                    "source_artifacts": [
                        {
                            "role": "asf-source-release",
                            "filename": f"apache-{component_id}-{version}-incubating-src.tar.gz",
                            "uri": (
                                f"{repo_url}/dist/dev/incubator/buildish/{component_id}/"
                                f"{version}-rc{rc_number}/apache-{component_id}-{version}-incubating-src.tar.gz"
                            ),
                            "artifact_origin": "source-commit",
                            "git_commit_sha": "0123456789abcdef0123456789abcdef01234567",
                            "checksums": {
                                "sha512": {
                                    "value": artifact_sha512,
                                    "uri": (
                                        f"{repo_url}/dist/dev/incubator/buildish/{component_id}/"
                                        f"{version}-rc{rc_number}/apache-{component_id}-{version}-incubating-src.tar.gz.sha512"
                                    ),
                                }
                            },
                            "signatures": [
                                {
                                    "type": "openpgp-detached-ascii-armored",
                                    "uri": (
                                        f"{repo_url}/dist/dev/incubator/buildish/{component_id}/"
                                        f"{version}-rc{rc_number}/apache-{component_id}-{version}-incubating-src.tar.gz.asc"
                                    ),
                                }
                            ],
                        }
                    ],
                    "secondary_artifacts": [],
                },
                "verification": {
                    "staging_svn_url": (
                        f"{repo_url}/dist/dev/incubator/buildish/{component_id}/{version}-rc{rc_number}/"
                    ),
                    "authoritative_manifest": {
                        "uri": (
                            f"{repo_url}/dist/dev/incubator/buildish/{component_id}/"
                            f"{version}-rc{rc_number}/rc-vote-manifest.json"
                        ),
                        "checksum_uris": {
                            "sha512": (
                                f"{repo_url}/dist/dev/incubator/buildish/{component_id}/"
                                f"{version}-rc{rc_number}/rc-vote-manifest.json.sha512"
                            )
                        },
                        "signatures": [
                            {
                                "type": "openpgp-detached-ascii-armored",
                                "uri": (
                                    f"{repo_url}/dist/dev/incubator/buildish/{component_id}/"
                                    f"{version}-rc{rc_number}/rc-vote-manifest.json.asc"
                                ),
                            }
                        ],
                    },
                },
            },
            indent=2,
        ) + "\n"
        manifest_sha512 = hashlib.sha512(manifest_text.encode("utf-8")).hexdigest()
        manifest_dir = (
            working_copy_dir
            / "dist"
            / "dev"
            / "incubator"
            / "buildish"
            / component_id
            / f"{version}-rc{rc_number}"
        )
        subprocess.run(
            ["svn", "add", "--force", str(manifest_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
        files = {
            "rc-vote-manifest.json": manifest_text,
            "rc-vote-manifest.json.sha512": f"{manifest_sha512}  rc-vote-manifest.json\n",
            "rc-vote-manifest.json.asc": (
                "-----BEGIN PGP SIGNATURE-----\n<dummy manifest>\n-----END PGP SIGNATURE-----\n"
            ),
        }
        for file_name, content in files.items():
            path = manifest_dir / file_name
            path.write_text(content, encoding="utf-8")
            subprocess.run(["svn", "add", "--force", str(path)], check=True, capture_output=True, text=True)
        AsfSvnClient().commit_working_copy(working_copy_dir, "stage rc vote manifest")
        return manifest_text

    def _prepare_detached_materialization_repo(self) -> tuple[Path, Path, Path, Path]:
        """Create one disposable repository pair configured for detached-materialization tests."""

        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        subprocess.run(["git", "-C", str(origin_dir), "checkout", "release/1.2.x"], check=True)
        (origin_dir / ".gitignore").write_text("/dist/\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(origin_dir), "add", ".gitignore"], check=True)
        subprocess.run(["git", "-C", str(origin_dir), "commit", "-m", "ignore dist"], check=True)
        subprocess.run(["git", "-C", str(origin_dir), "checkout", "main"], check=True)
        fetch_git_origin_refs(clone_dir)
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
            final_tag_mode="detached-materialization-commit",
        )
        return sandbox_dir, origin_dir, clone_dir, config_path

    def test_prepare_rc_command_uses_yaml_component_config(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "prepare-rc.json"
        github_output_path = sandbox_dir / "prepare-rc.outputs"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc2")
        fetch_git_origin_refs(clone_dir)
        expected_commit = git_rev_parse(
            clone_dir,
            "refs/remotes/origin/release/1.2.x^{commit}",
        )
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        completed = run_cli(
            [
                "prepare-rc",
                "--component-config",
                str(config_path),
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(manifest_path, extra_env={"GITHUB_OUTPUT": str(github_output_path)}),
        )
        self.assertEqual(0, completed.returncode)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(expected_commit, manifest["resolved_source_ref"])
        self.assertEqual("release/1.2.x", manifest["resolved_release_branch"])
        self.assertEqual("3", manifest["rc_number"])
        self.assertEqual("v1.2.3-rc3", manifest["rc_tag"])
        github_outputs = _read_simple_github_outputs(github_output_path)
        self.assertEqual("v1.2.3-rc3", github_outputs["rc_tag"])
        self.assertEqual(expected_commit, github_outputs["resolved_source_ref"])

    def test_cleanup_dev_svn_rcs_command_deletes_matching_version_directories(self) -> None:
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        _repo_dir, repo_url, _working_copy_dir = init_svn_repo_and_checkout(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "cleanup-dev-svn-rcs.json"
        client = AsfSvnClient()
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=dev_base_url,
            release_base_url=release_base_url,
        )
        client.mkdir_url(dev_base_url, "create dev component path")
        for rc_directory in ("1.2.3-rc0", "1.2.3-rc2", "1.2.4-rc0"):
            client.mkdir_url(f"{dev_base_url}/{rc_directory}", f"create {rc_directory}")
        completed = run_cli(
            [
                "cleanup-dev-svn-rcs",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "1.2.3",
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(component_id, manifest["component"])
        self.assertEqual("1.2.3-rc0,1.2.3-rc2", manifest["deleted_rc_directories"])
        self.assertEqual(["1.2.4-rc0/"], client.list_entries(dev_base_url))
        summary_text = manifest_path.with_suffix(".summary.md").read_text(encoding="utf-8")
        self.assertIn("Cleanup ASF SVN dev/dist for version 1.2.3", summary_text)
        self.assertIn("| Deleted RC directory count | 2 |", summary_text)
        self.assertIn("1.2.3-rc0/", summary_text)

    def test_prepare_rc_rejects_non_production_release_targets_without_opt_in(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "prepare-rc.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="file:///tmp/buildish-test/dev",
            release_base_url="file:///tmp/buildish-test/release",
        )
        completed = run_cli(
            [
                "prepare-rc",
                "--component-config",
                str(config_path),
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn("--allow-non-production-release-targets", completed.stderr)

    def test_prepare_rc_allows_non_production_release_targets_with_opt_in(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "prepare-rc.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        expected_commit = git_rev_parse(clone_dir, "refs/remotes/origin/release/1.2.x^{commit}")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="file:///tmp/buildish-test/dev",
            release_base_url="file:///tmp/buildish-test/release",
        )
        completed = run_cli(
            [
                "prepare-rc",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(expected_commit, manifest["resolved_source_ref"])
        self.assertEqual("file:///tmp/buildish-test/dev/1.2.3-rc0/", manifest["staging_url"])

    def test_release_version_command_infers_release_line_and_pruning_from_svn(self) -> None:
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        _repo_dir, repo_url, _working_copy_dir = init_svn_repo_and_checkout(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "release-version.json"
        client = AsfSvnClient()
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc2")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=dev_base_url,
            release_base_url=release_base_url,
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3-rc2",
                    "name": "Apache Buildish Example 1.2.3",
                    "body": "\n".join(
                        [
                            "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "RC tag: v1.2.3-rc2",
                            f"Resolved source ref: {git_rev_parse(clone_dir, 'v1.2.3-rc2^{commit}')}",
                        ]
                    ),
                }
            ],
        )
        client.mkdir_url(release_base_url, "create release component path")
        for published_version in ("1.2.1", "1.2.2", "1.3.0"):
            client.mkdir_url(f"{release_base_url}/{published_version}", f"create {published_version}")
        completed = run_cli(
            [
                "release-version",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("1.2.x", manifest["release_line"])
        self.assertEqual("v1.2.3-rc2", manifest["selected_rc_tag"])
        self.assertEqual("1.2.1,1.2.2", manifest["archive_versions"])

    def test_sync_draft_github_release_command_recreates_matching_draft_release(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "sync-draft-github-release.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc2")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        expected_commit = git_rev_parse(
            clone_dir,
            "refs/remotes/origin/release/1.2.x^{commit}",
        )
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 11,
                    "draft": True,
                    "tag_name": "v1.2.3",
                    "name": "Apache Buildish Example 1.2.3",
                },
                {
                    "id": 12,
                    "draft": True,
                    "tag_name": "v1.2.3-rc2",
                    "name": "Stale RC draft",
                },
                {
                    "id": 99,
                    "draft": False,
                    "tag_name": "v1.2.2",
                    "name": "Apache Buildish Example 1.2.2",
                },
            ],
            create_response={
                "id": 42,
                "tag_name": "v1.2.3-rc3",
                "name": "Apache Buildish Example 1.2.3",
                "html_url": "https://github.com/apache/buildish-example/releases/tag/v1.2.3-rc3",
            },
        )
        completed = run_cli(
            [
                "sync-draft-github-release",
                "--component-config",
                str(config_path),
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("apache/buildish-example", manifest["repository_slug"])
        self.assertEqual(expected_commit, manifest["resolved_source_ref"])
        self.assertEqual("v1.2.3-rc3", manifest["rc_tag"])
        self.assertEqual("v1.2.3", manifest["final_tag"])
        self.assertEqual("11,12", manifest["deleted_release_ids"])
        self.assertEqual("created", manifest["sync_mode"])
        self.assertEqual("42", manifest["release_id"])
        self.assertEqual("v1.2.3-rc3", manifest["release_tag"])
        self.assertEqual(
            "https://github.com/apache/buildish-example/releases/tag/v1.2.3-rc3",
            manifest["release_url"],
        )
        create_request = json.loads(
            (gh_state_dir / "create-release-request.json").read_text(encoding="utf-8")
        )
        self.assertTrue(create_request["draft"])
        self.assertEqual("v1.2.3-rc3", create_request["tag_name"])
        self.assertEqual(expected_commit, create_request["target_commitish"])
        self.assertEqual("Apache Buildish Example 1.2.3", create_request["name"])
        self.assertIn("RC tag: v1.2.3-rc3", create_request["body"])
        self.assertIn(
            "ASF SVN staging URL: https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example/1.2.3-rc3/",
            create_request["body"],
        )
        deleted_endpoints = (
            gh_state_dir / "deleted-endpoints.log"
        ).read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            [
                "repos/apache/buildish-example/releases/11",
                "repos/apache/buildish-example/releases/12",
            ],
            deleted_endpoints,
        )
        summary_text = manifest_path.with_suffix(".summary.md").read_text(encoding="utf-8")
        self.assertIn("Sync draft GitHub Release", summary_text)
        self.assertIn("id: 42", summary_text)

    def test_publish_source_release_svn_command_promotes_latest_rc_directory(self) -> None:
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        _repo_dir, repo_url, working_copy_dir = init_svn_repo_and_checkout(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "publish-source-release-svn.json"
        client = AsfSvnClient()
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc2")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=dev_base_url,
            release_base_url=release_base_url,
        )
        client.mkdir_url(dev_base_url, "create dev component path")
        client.mkdir_url(release_base_url, "create release component path")
        client.mkdir_url(f"{dev_base_url}/1.2.3-rc2", "create rc directory")
        artifact_sha512 = self._stage_source_release_files(
            sandbox_dir,
            working_copy_dir,
            component_id=component_id,
            version="1.2.3",
            rc_number=2,
        )
        manifest_text = self._stage_rc_vote_manifest_files(
            working_copy_dir,
            component_id=component_id,
            version="1.2.3",
            rc_number=2,
            repo_url=repo_url,
            artifact_sha512=artifact_sha512,
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3-rc2",
                    "name": "Apache Buildish Example 1.2.3",
                    "body": "\n".join(
                        [
                            "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "RC tag: v1.2.3-rc2",
                            f"Resolved source ref: {git_rev_parse(clone_dir, 'v1.2.3-rc2^{commit}')}",
                        ],
                    ),
                    "assets": [{"id": 700, "name": "rc-vote-manifest.json"}],
                }
            ],
            release_asset_text_by_id={700: manifest_text},
        )
        completed = run_cli(
            [
                "publish-source-release-svn",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("v1.2.3-rc2", manifest["selected_rc_tag"])
        self.assertEqual(["1.2.3/"], client.list_entries(release_base_url))
        self.assertEqual("copied", manifest["publish_mode"])
        self.assertEqual(artifact_sha512, manifest["verified_source_artifact_sha512"])
        rerun = run_cli(
            [
                "publish-source-release-svn",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(0, rerun.returncode, msg=rerun.stderr)
        rerun_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("already-present", rerun_manifest["publish_mode"])

    def test_publish_source_release_svn_command_rejects_missing_required_source_files(self) -> None:
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        _repo_dir, repo_url, _working_copy_dir = init_svn_repo_and_checkout(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "publish-source-release-svn.json"
        client = AsfSvnClient()
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc2")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=dev_base_url,
            release_base_url=release_base_url,
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3-rc2",
                    "name": "Apache Buildish Example 1.2.3",
                    "body": "\n".join(
                        [
                            "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "RC tag: v1.2.3-rc2",
                            f"Resolved source ref: {git_rev_parse(clone_dir, 'v1.2.3-rc2^{commit}')}",
                        ],
                    ),
                    "assets": [{"id": 700, "name": "rc-vote-manifest.json"}],
                }
            ],
        )
        client.mkdir_url(dev_base_url, "create dev component path")
        client.mkdir_url(release_base_url, "create release component path")
        client.mkdir_url(f"{dev_base_url}/1.2.3-rc2", "create rc directory")
        completed = run_cli(
            [
                "publish-source-release-svn",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("missing required staged release files", completed.stderr)
        self.assertEqual([], client.list_entries(release_base_url))

    def test_publish_source_release_svn_command_rejects_staged_artifact_drift_from_vote_manifest(self) -> None:
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        _repo_dir, repo_url, working_copy_dir = init_svn_repo_and_checkout(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "publish-source-release-svn.json"
        client = AsfSvnClient()
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc2")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=dev_base_url,
            release_base_url=release_base_url,
        )
        client.mkdir_url(dev_base_url, "create dev component path")
        client.mkdir_url(release_base_url, "create release component path")
        client.mkdir_url(f"{dev_base_url}/1.2.3-rc2", "create rc directory")
        artifact_sha512 = self._stage_source_release_files(
            sandbox_dir,
            working_copy_dir,
            component_id=component_id,
            version="1.2.3",
            rc_number=2,
        )
        manifest_text = self._stage_rc_vote_manifest_files(
            working_copy_dir,
            component_id=component_id,
            version="1.2.3",
            rc_number=2,
            repo_url=repo_url,
            artifact_sha512=artifact_sha512,
        )
        subprocess.run(["svn", "update", str(working_copy_dir)], check=True, capture_output=True, text=True)
        drifted_artifact = (
            working_copy_dir
            / "dist"
            / "dev"
            / "incubator"
            / "buildish"
            / component_id
            / "1.2.3-rc2"
            / "apache-buildish-example-1.2.3-incubating-src.tar.gz"
        )
        drifted_artifact.write_bytes(b"drifted source payload\n")
        subprocess.run(["svn", "commit", "-m", "drift staged artifact", str(working_copy_dir)], check=True)
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3-rc2",
                    "name": "Apache Buildish Example 1.2.3",
                    "body": "\n".join(
                        [
                            "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "RC tag: v1.2.3-rc2",
                            f"Resolved source ref: {git_rev_parse(clone_dir, 'v1.2.3-rc2^{commit}')}",
                        ],
                    ),
                    "assets": [{"id": 700, "name": "rc-vote-manifest.json"}],
                }
            ],
            release_asset_text_by_id={700: manifest_text},
        )
        completed = run_cli(
            [
                "publish-source-release-svn",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertNotEqual(0, completed.returncode)
        self.assertIn(
            "staged source artifact .sha512 sidecar does not match the staged source artifact bytes",
            completed.stderr,
        )
        self.assertEqual([], client.list_entries(release_base_url))

    def test_publish_source_release_svn_command_rejects_rc_drift(self) -> None:
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        _repo_dir, repo_url, _working_copy_dir = init_svn_repo_and_checkout(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "publish-source-release-svn.json"
        client = AsfSvnClient()
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc1")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc2")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=dev_base_url,
            release_base_url=release_base_url,
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3-rc2",
                    "name": "Apache Buildish Example 1.2.3",
                    "body": "\n".join(
                        [
                            "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "RC tag: v1.2.3-rc2",
                            f"Resolved source ref: {git_rev_parse(clone_dir, 'v1.2.3-rc2^{commit}')}",
                        ]
                    ),
                }
            ],
        )
        client.mkdir_url(dev_base_url, "create dev component path")
        client.mkdir_url(release_base_url, "create release component path")
        client.mkdir_url(f"{dev_base_url}/1.2.3-rc2", "create rc directory")
        completed = run_cli(
            [
                "publish-source-release-svn",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "--selected-rc-tag",
                "v1.2.3-rc1",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "draft GitHub Release for v1.2.3 now points at v1.2.3-rc2, expected v1.2.3-rc1",
            completed.stderr,
        )

    def test_prune_older_line_releases_command_deletes_specific_line_versions(self) -> None:
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        _repo_dir, repo_url, _working_copy_dir = init_svn_repo_and_checkout(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "prune-older-line-releases.json"
        client = AsfSvnClient()
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc2")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=dev_base_url,
            release_base_url=release_base_url,
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3-rc2",
                    "name": "Apache Buildish Example 1.2.3",
                    "body": "\n".join(
                        [
                            "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "RC tag: v1.2.3-rc2",
                            f"Resolved source ref: {git_rev_parse(clone_dir, 'v1.2.3-rc2^{commit}')}",
                        ]
                    ),
                }
            ],
        )
        client.mkdir_url(release_base_url, "create release component path")
        for published_version in ("1.2.1", "1.2.2", "1.2.3", "1.3.0"):
            client.mkdir_url(f"{release_base_url}/{published_version}", f"create {published_version}")
        completed = run_cli(
            [
                "prune-older-line-releases",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("1.2.x", manifest["release_line"])
        self.assertEqual("1.2.1,1.2.2", manifest["pruned_versions"])
        self.assertEqual(["1.2.3/", "1.3.0/"], client.list_entries(release_base_url))

    def test_create_final_tag_command_creates_remote_annotated_tag(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "create-final-tag.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc2")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc3")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        expected_commit = git_rev_parse(clone_dir, "v1.2.3-rc2^{commit}")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3-rc2",
                    "name": "Apache Buildish Example 1.2.3",
                    "body": "\n".join(
                        [
                            "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "RC tag: v1.2.3-rc2",
                            f"Resolved source ref: {expected_commit}",
                        ]
                    ),
                }
            ],
            create_tag_response={"sha": "tag-object-sha"},
            create_ref_response={"ref": "refs/tags/v1.2.3"},
        )
        completed = run_cli(
            [
                "create-final-tag",
                "--component-config",
                str(config_path),
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("v1.2.3", manifest["final_tag"])
        self.assertEqual(expected_commit, manifest["target_commit"])
        self.assertEqual("github-api", manifest["tag_creation_mode"])
        self.assertEqual("v1.2.3-rc2", manifest["selected_rc_tag"])
        create_tag_request = json.loads((gh_state_dir / "create-tag-request.json").read_text(encoding="utf-8"))
        self.assertEqual("v1.2.3", create_tag_request["tag"])
        self.assertEqual(expected_commit, create_tag_request["object"])
        create_ref_request = json.loads((gh_state_dir / "create-ref-request.json").read_text(encoding="utf-8"))
        self.assertEqual("refs/tags/v1.2.3", create_ref_request["ref"])
        self.assertEqual("tag-object-sha", create_ref_request["sha"])

    def test_create_rc_materialization_tag_command_creates_local_rc_tag(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "create-rc-materialization-tag.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        expected_commit = git_rev_parse(clone_dir, "refs/remotes/origin/release/1.2.x^{commit}")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        completed = run_cli(
            [
                "create-rc-materialization-tag",
                "--component-config",
                str(config_path),
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("v1.2.3-rc0", manifest["rc_tag"])
        self.assertEqual(expected_commit, manifest["target_commit"])
        self.assertEqual("source-commit", manifest["tag_target_origin"])
        self.assertEqual(expected_commit, git_rev_parse(clone_dir, "v1.2.3-rc0^{commit}"))

    def test_materialize_rc_git_content_command_generates_default_temp_ref_and_stages_repeatable_paths(
        self,
    ) -> None:
        _sandbox_dir, origin_dir, clone_dir, config_path = self._prepare_detached_materialization_repo()
        manifest_path = config_path.parent / "materialize-rc-git-content.json"
        github_output_path = config_path.parent / "materialize-rc-git-content.outputs"
        resolved_source_ref = git_rev_parse(clone_dir, "refs/remotes/origin/release/1.2.x^{commit}")
        materialized_ref_name = "refs/heads/buildish-internal/materialized/v1.2.3-rc0/12345-6"

        completed = run_cli(
            [
                "materialize-rc-git-content",
                "--component-config",
                str(config_path),
                "--rc-tag",
                "v1.2.3-rc0",
                "--materialized-path",
                "dist",
                "--materialized-path",
                "NOTICE.generated",
                "--run-command",
                "mkdir -p dist && printf 'payload\\n' > dist/release.txt && "
                "printf 'generated notice\\n' > NOTICE.generated",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={
                    "GITHUB_OUTPUT": str(github_output_path),
                    "GITHUB_RUN_ID": "12345",
                    "GITHUB_RUN_ATTEMPT": "6",
                },
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("v1.2.3-rc0", manifest["rc_tag"])
        self.assertEqual(resolved_source_ref, manifest["resolved_source_ref"])
        self.assertEqual("dist,NOTICE.generated", manifest["materialized_paths"])
        self.assertEqual(materialized_ref_name, manifest["materialized_ref_name"])
        self.assertEqual("pushed", manifest["materialized_ref_mode"])
        github_outputs = _read_simple_github_outputs(github_output_path)
        self.assertEqual(manifest["materialized_commit_sha"], github_outputs["materialized_commit_sha"])
        self.assertEqual(materialized_ref_name, github_outputs["materialized_ref_name"])
        self.assertNotEqual(resolved_source_ref, manifest["materialized_commit_sha"])
        self.assertEqual(
            manifest["materialized_commit_sha"],
            git_rev_parse(origin_dir, f"{materialized_ref_name}^{{commit}}"),
        )
        materialized_payload = subprocess.run(
            ["git", "-C", str(clone_dir), "show", f"{manifest['materialized_commit_sha']}:dist/release.txt"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertEqual("payload\n", materialized_payload)
        materialized_notice = subprocess.run(
            ["git", "-C", str(clone_dir), "show", f"{manifest['materialized_commit_sha']}:NOTICE.generated"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertEqual("generated notice\n", materialized_notice)
        source_payload = subprocess.run(
            ["git", "-C", str(clone_dir), "show", f"{resolved_source_ref}:dist/release.txt"],
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(0, source_payload.returncode)
        self.assertIn(
            "Materialize RC Git content",
            manifest_path.with_suffix(".summary.md").read_text(encoding="utf-8"),
        )

    def test_create_rc_materialization_tag_command_can_cleanup_generated_materialized_ref(self) -> None:
        _sandbox_dir, origin_dir, clone_dir, config_path = self._prepare_detached_materialization_repo()
        materialize_manifest_path = config_path.parent / "materialize-rc-git-content.json"
        tag_manifest_path = config_path.parent / "create-rc-materialization-tag.json"

        completed = run_cli(
            [
                "materialize-rc-git-content",
                "--component-config",
                str(config_path),
                "--rc-tag",
                "v1.2.3-rc0",
                "--materialized-path",
                "dist",
                "--run-command",
                "mkdir -p dist && printf 'payload\\n' > dist/release.txt",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(materialize_manifest_path),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        materialize_manifest = json.loads(materialize_manifest_path.read_text(encoding="utf-8"))
        materialized_ref_name = materialize_manifest["materialized_ref_name"]
        self.assertRegex(
            materialized_ref_name,
            rf"^refs/heads/buildish-internal/materialized/v1\.2\.3-rc0/"
            rf"{re.escape(materialize_manifest['resolved_source_ref'][:12])}-[0-9a-f]{{8}}$",
        )

        completed = run_cli(
            [
                "create-rc-materialization-tag",
                "--component-config",
                str(config_path),
                "--rc-tag",
                "v1.2.3-rc0",
                "--target-commit",
                materialize_manifest["materialized_commit_sha"],
                "--cleanup-materialized-ref-name",
                materialized_ref_name,
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(tag_manifest_path),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(tag_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("v1.2.3-rc0", manifest["rc_tag"])
        self.assertEqual(materialize_manifest["materialized_commit_sha"], manifest["target_commit"])
        self.assertEqual("deleted", manifest["cleanup_materialized_ref_mode"])
        self.assertEqual(materialized_ref_name, manifest["cleanup_materialized_ref_name"])
        self.assertEqual(
            materialize_manifest["materialized_commit_sha"],
            git_rev_parse(clone_dir, "v1.2.3-rc0^{commit}"),
        )
        remote_ref_check = subprocess.run(
            ["git", "-C", str(origin_dir), "show-ref", "--verify", "--quiet", materialized_ref_name],
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(1, remote_ref_check.returncode)

    def test_create_rc_materialization_tag_command_fails_when_rc_tag_already_exists(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "create-rc-materialization-tag.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc0", "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        completed = run_cli(
            [
                "create-rc-materialization-tag",
                "--component-config",
                str(config_path),
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn("tag already exists: v1.2.3-rc0", completed.stderr)

    def test_sync_draft_github_release_reuses_same_rc_without_deleting_assets(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "sync-draft-github-release.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        expected_commit = git_rev_parse(clone_dir, "refs/remotes/origin/release/1.2.x^{commit}")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        release_body = "\n".join(
            [
                "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                "",
                "RC tag: v1.2.3-rc0",
                "Final tag: v1.2.3",
                f"Resolved source ref: {expected_commit}",
                "ASF SVN staging URL: https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example/1.2.3-rc0/",
                "Final tag mode: rc-source-commit",
                "",
                "This draft release is convenience metadata only and must remain unpublished until the ASF vote passes.",
            ]
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3-rc0",
                    "name": "Apache Buildish Example 1.2.3",
                    "body": release_body,
                    "html_url": "https://github.com/apache/buildish-example/releases/tag/v1.2.3-rc0",
                }
            ],
        )
        completed = run_cli(
            [
                "sync-draft-github-release",
                "--component-config",
                str(config_path),
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("reused", manifest["sync_mode"])
        self.assertEqual("", manifest["deleted_release_ids"])
        self.assertFalse((gh_state_dir / "deleted-endpoints.log").exists())
        self.assertFalse((gh_state_dir / "create-release-request.json").exists())

    def test_sync_draft_github_release_retags_legacy_final_tag_release(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "sync-draft-github-release.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        expected_commit = git_rev_parse(clone_dir, "refs/remotes/origin/release/1.2.x^{commit}")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        release_body = "\n".join(
            [
                "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                "",
                "RC tag: v1.2.3-rc0",
                "Final tag: v1.2.3",
                f"Resolved source ref: {expected_commit}",
                "ASF SVN staging URL: https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example/1.2.3-rc0/",
                "Final tag mode: rc-source-commit",
                "",
                "This draft release is convenience metadata only and must remain unpublished until the ASF vote passes.",
            ]
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3",
                    "name": "Apache Buildish Example 1.2.3",
                    "body": release_body,
                    "html_url": "https://github.com/apache/buildish-example/releases/tag/v1.2.3",
                }
            ],
            update_release_response={
                "id": 42,
                "draft": True,
                "tag_name": "v1.2.3-rc0",
                "name": "Apache Buildish Example 1.2.3",
                "html_url": "https://github.com/apache/buildish-example/releases/tag/v1.2.3-rc0",
            },
        )
        completed = run_cli(
            [
                "sync-draft-github-release",
                "--component-config",
                str(config_path),
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("updated", manifest["sync_mode"])
        self.assertEqual("v1.2.3-rc0", manifest["release_tag"])
        update_request = json.loads(
            (gh_state_dir / "update-release-request.json").read_text(encoding="utf-8")
        )
        self.assertEqual("v1.2.3-rc0", update_request["tag_name"])
        self.assertEqual(expected_commit, update_request["target_commitish"])

    def test_sync_draft_github_release_rejects_higher_existing_rc(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "sync-draft-github-release.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3",
                    "name": "Apache Buildish Example 1.2.3",
                    "body": "\n".join(
                        [
                            "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "RC tag: v1.2.3-rc1",
                        ]
                    ),
                }
            ],
        )
        completed = run_cli(
            [
                "sync-draft-github-release",
                "--component-config",
                str(config_path),
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn("higher RC", completed.stderr)

    def test_update_moving_tags_command_updates_only_aliases_that_do_not_roll_back(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "update-moving-tags.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        subprocess.run(
            ["git", "-C", str(origin_dir), "checkout", "-b", "line-1.3", "main"],
            check=True,
        )
        (origin_dir / "release-1.3.txt").write_text("1.3.4\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(origin_dir), "add", "release-1.3.txt"], check=True)
        subprocess.run(["git", "-C", str(origin_dir), "commit", "-m", "release 1.3.4"], check=True)
        subprocess.run(
            ["git", "-C", str(origin_dir), "tag", "-a", "v1.3.4", "-m", "v1.3.4"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(origin_dir), "tag", "-a", "v1", "-m", "v1"],
            check=True,
        )
        subprocess.run(["git", "-C", str(origin_dir), "checkout", "main"], check=True)
        subprocess.run(
            ["git", "-C", str(origin_dir), "tag", "-a", "v1.2.2", "-m", "v1.2.2"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(origin_dir), "tag", "-a", "v1.2", "-m", "v1.2"],
            check=True,
        )
        (origin_dir / "release-1.2.3.txt").write_text("1.2.3\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(origin_dir), "add", "release-1.2.3.txt"], check=True)
        subprocess.run(["git", "-C", str(origin_dir), "commit", "-m", "release 1.2.3"], check=True)
        subprocess.run(
            ["git", "-C", str(origin_dir), "tag", "-a", "v1.2.3", "-m", "v1.2.3"],
            check=True,
        )
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        expected_commit = git_rev_parse(clone_dir, "v1.2.3^{commit}")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
            secondary_targets=("github-action",),
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[],
            create_tag_response={"sha": "moving-tag-object-sha"},
            update_ref_response={"ref": "refs/tags/v1.2"},
        )
        completed = run_cli(
            [
                "update-moving-tags",
                "--component-config",
                str(config_path),
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(expected_commit, manifest["target_commit"])
        self.assertEqual("v1.2", manifest["updated_tags"])
        self.assertEqual("v1", manifest["skipped_tags"])
        create_tag_request = json.loads((gh_state_dir / "create-tag-request.json").read_text(encoding="utf-8"))
        self.assertEqual("v1.2", create_tag_request["tag"])
        self.assertEqual(expected_commit, create_tag_request["object"])
        update_ref_request = json.loads((gh_state_dir / "update-ref-request.json").read_text(encoding="utf-8"))
        self.assertEqual("moving-tag-object-sha", update_ref_request["sha"])
        requests_log = (gh_state_dir / "requests.log").read_text(encoding="utf-8")
        self.assertIn("PATCH repos/apache/buildish-example/git/refs/tags/v1.2", requests_log)
        self.assertNotIn("PATCH repos/apache/buildish-example/git/refs/tags/v1\n", requests_log)

    def test_update_moving_image_aliases_command_emits_derived_aliases(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "update-moving-image-aliases.json"
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
            secondary_targets=("dockerhub",),
        )
        completed = run_cli(
            [
                "update-moving-image-aliases",
                "--component-config",
                str(config_path),
                "1.2.3",
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("1.2.3", manifest["exact_image_tag"])
        self.assertEqual("1 1.2", manifest["image_aliases"])

    def test_publish_dockerhub_moving_tags_command_creates_alias_refs(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "publish-dockerhub-moving-tags.json"
        docker_path, docker_state_dir = create_fake_docker_launcher(sandbox_dir)
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
            secondary_targets=("dockerhub",),
        )
        completed = run_cli(
            [
                "publish-dockerhub-moving-tags",
                "--component-config",
                str(config_path),
                "1.2.3",
                "docker.io/apache/buildish-example:1.2.3",
            ],
            cwd=sandbox_dir,
            env=cli_env(
                manifest_path,
                extra_env={
                    "DOCKERHUB_USER": "buildish-bot",
                    "DOCKERHUB_TOKEN": "super-secret-token",
                    "FAKE_DOCKER_STATE_DIR": str(docker_state_dir),
                },
                prepend_dirs=(docker_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("docker.io/apache/buildish-example:1.2.3", manifest["source_image"])
        self.assertEqual("docker.io/apache/buildish-example", manifest["image_repository"])
        self.assertEqual(
            "docker.io/apache/buildish-example:1 docker.io/apache/buildish-example:1.2",
            manifest["published_alias_refs"],
        )
        self.assertEqual(
            "buildish-bot",
            (docker_state_dir / "login-user.txt").read_text(encoding="utf-8").strip(),
        )
        self.assertEqual(
            "docker.io",
            (docker_state_dir / "login-registry.txt").read_text(encoding="utf-8").strip(),
        )
        self.assertEqual(
            [
                "docker.io/apache/buildish-example:1|docker.io/apache/buildish-example:1.2.3|false",
                "docker.io/apache/buildish-example:1.2|docker.io/apache/buildish-example:1.2.3|false",
            ],
            (docker_state_dir / "imagetools-create.log").read_text(encoding="utf-8").splitlines(),
        )

    def test_attach_github_release_assets_command_uploads_assets_with_optional_sidecars(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for the GitHub Release asset-signing integration test")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "attach-github-release-assets.json"
        asset_path = sandbox_dir / "buildish-example.zip"
        source_home = sandbox_dir / "gpg-source"
        source_home.mkdir(parents=True, exist_ok=True)
        source_home.chmod(0o700)
        asset_path.write_bytes(b"release-asset\n")
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
            secondary_targets=("github-release-assets",),
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3",
                    "name": "Apache Buildish Example 1.2.3",
                    "html_url": "https://github.com/apache/buildish-example/releases/tag/v1.2.3",
                }
            ],
        )

        subprocess.run(
            [
                "gpg",
                "--batch",
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                "",
                "--quick-gen-key",
                "Release Tooling Tests <release-tooling-tests@example.invalid>",
                "ed25519",
                "sign",
                "1d",
            ],
            env={**os.environ, "GNUPGHOME": str(source_home)},
            check=True,
            capture_output=True,
            text=True,
        )
        secret_key = subprocess.run(
            [
                "gpg",
                "--armor",
                "--export-secret-keys",
                "Release Tooling Tests <release-tooling-tests@example.invalid>",
            ],
            env={**os.environ, "GNUPGHOME": str(source_home)},
            check=True,
            capture_output=True,
            text=True,
        ).stdout

        completed = run_cli(
            [
                "attach-github-release-assets",
                "--component-config",
                str(config_path),
                "--sign",
                "--checksum",
                "sha512",
                "--checksum",
                "sha256",
                "1.2.3",
                str(asset_path),
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={
                    "BUILDISH_GPG_PRIVATE_KEY": secret_key,
                    "FAKE_GH_STATE_DIR": str(gh_state_dir),
                },
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("42", manifest["release_id"])
        self.assertEqual("v1.2.3", manifest["release_tag"])
        self.assertEqual("buildish-example.zip", manifest["primary_asset_names"])
        self.assertEqual("sha512,sha256", manifest["checksum_algorithms"])
        self.assertIn("buildish-example.zip.asc", manifest["generated_signature_asset_names"])
        self.assertIn("buildish-example.zip.sha512", manifest["generated_checksum_asset_names"])
        self.assertIn("buildish-example.zip.sha256", manifest["generated_checksum_asset_names"])
        self.assertTrue(manifest["gpg_fingerprint"])

        self.assertTrue((asset_path.with_name("buildish-example.zip.asc")).is_file())
        self.assertEqual(
            [
                str(asset_path),
                str(asset_path.with_name("buildish-example.zip.sha512")),
                str(asset_path.with_name("buildish-example.zip.sha256")),
                str(asset_path.with_name("buildish-example.zip.asc")),
            ],
            (gh_state_dir / "release-upload-files.log").read_text(encoding="utf-8").splitlines(),
        )
        self.assertEqual(
            "v1.2.3",
            (gh_state_dir / "release-upload-tag.txt").read_text(encoding="utf-8").strip(),
        )
        self.assertEqual(
            "apache/buildish-example",
            (gh_state_dir / "release-upload-repo.txt").read_text(encoding="utf-8").strip(),
        )
        self.assertEqual(
            "true",
            (gh_state_dir / "release-upload-clobber.txt").read_text(encoding="utf-8").strip(),
        )
        summary_text = manifest_path.with_suffix(".summary.md").read_text(encoding="utf-8")
        self.assertIn("Attach GitHub Release assets", summary_text)
        self.assertIn("buildish-example.zip.sha512", summary_text)
        self.assertIn("buildish-example.zip.asc", summary_text)

    def test_finalize_draft_github_release_command_publishes_existing_draft(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "finalize-draft-github-release.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc0", "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        expected_commit = git_rev_parse(clone_dir, "v1.2.3-rc0^{commit}")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3",
                    "name": "Apache Buildish Example 1.2.3",
                    "body": "\n".join(
                        [
                            "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "RC tag: v1.2.3-rc0",
                            f"Resolved source ref: {expected_commit}",
                        ]
                    ),
                    "assets": [
                        {"id": 201, "name": "rc-vote-manifest.json"},
                        {"id": 202, "name": "rc-vote-manifest.json.asc"},
                        {"id": 203, "name": "keep-me.txt"},
                    ],
                }
            ],
            update_release_response={
                "id": 42,
                "draft": False,
                "tag_name": "v1.2.3",
                "name": "Apache Buildish Example 1.2.3",
                "html_url": "https://github.com/apache/buildish-example/releases/tag/v1.2.3",
            },
        )
        completed = run_cli(
            [
                "finalize-draft-github-release",
                "--component-config",
                str(config_path),
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("42", manifest["release_id"])
        self.assertEqual("v1.2.3", manifest["release_tag"])
        self.assertEqual("published-draft", manifest["finalize_mode"])
        self.assertEqual("rc-vote-manifest.json,rc-vote-manifest.json.asc", manifest["deleted_asset_names"])
        update_request = json.loads(
            (gh_state_dir / "update-release-request.json").read_text(encoding="utf-8")
        )
        self.assertFalse(update_request["draft"])
        self.assertFalse(update_request["prerelease"])
        self.assertEqual("v1.2.3", update_request["tag_name"])
        self.assertEqual(expected_commit, update_request["target_commitish"])
        self.assertEqual("Apache Buildish Example 1.2.3", update_request["name"])
        self.assertEqual(
            [
                "repos/apache/buildish-example/releases/assets/201",
                "repos/apache/buildish-example/releases/assets/202",
            ],
            (gh_state_dir / "deleted-asset-endpoints.log").read_text(encoding="utf-8").splitlines(),
        )
        self.assertIn(
            "Finalize draft GitHub Release",
            manifest_path.with_suffix(".summary.md").read_text(encoding="utf-8"),
        )

    def test_record_artifact_generic_file_command_writes_registration_bundle(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
        github_output_path = sandbox_dir / "record-artifact.outputs"
        component_id = "buildish-example"
        artifact_id = "bootstrap-zip"
        artifact_file_path = sandbox_dir / "buildish-example-bootstrap.zip"
        artifact_bytes = b"bootstrap payload\n"
        artifact_file_path.write_bytes(artifact_bytes)
        expected_sha512 = hashlib.sha512(artifact_bytes).hexdigest()
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )

        completed = run_cli(
            [
                "record-artifact",
                "--component-config",
                str(config_path),
                "--kind",
                "generic-file",
                "--artifact-id",
                artifact_id,
                "--role",
                "bootstrap-convenience-archive",
                "--file",
                str(artifact_file_path),
                "--uri",
                "https://github.com/apache/buildish-example/releases/download/v1.2.3-rc0/buildish-example-bootstrap.zip",
                "--sha512-uri",
                "https://github.com/apache/buildish-example/releases/download/v1.2.3-rc0/buildish-example-bootstrap.zip.sha512",
                "--artifact-origin",
                "source-commit",
                "--git-commit-sha",
                "0123456789abcdef0123456789abcdef01234567",
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path, extra_env={"GITHUB_OUTPUT": str(github_output_path)}),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        expected_manifest_path = (
            sandbox_dir
            / "build"
            / "release-artifacts"
            / component_id
            / "secondary-artifacts"
            / artifact_id
            / "artifact-manifest.json"
        )
        self.assertEqual(str(expected_manifest_path), completed.stdout.strip())
        action_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(component_id, action_manifest["component"])
        self.assertEqual("record-artifact", action_manifest["action"])
        self.assertEqual(artifact_id, action_manifest["artifact_id"])
        self.assertEqual("generic-file", action_manifest["kind"])
        self.assertEqual(str(expected_manifest_path), action_manifest["artifact_manifest_path"])
        self.assertEqual(str(expected_manifest_path.parent), action_manifest["artifact_bundle_dir"])
        self.assertEqual([], action_manifest["inventory_paths"])

        payload = json.loads(expected_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [
                {
                    "artifact_id": artifact_id,
                    "kind": "generic-file",
                    "role": "bootstrap-convenience-archive",
                    "filename": "buildish-example-bootstrap.zip",
                    "uri": "https://github.com/apache/buildish-example/releases/download/v1.2.3-rc0/buildish-example-bootstrap.zip",
                    "artifact_origin": "source-commit",
                    "git_commit_sha": "0123456789abcdef0123456789abcdef01234567",
                    "checksums": {
                        "sha512": {
                            "value": expected_sha512,
                            "uri": "https://github.com/apache/buildish-example/releases/download/v1.2.3-rc0/buildish-example-bootstrap.zip.sha512",
                        }
                    },
                    "signatures": [],
                }
            ],
            payload["secondary_artifacts"],
        )
        github_outputs = _read_simple_github_outputs(github_output_path)
        self.assertEqual(artifact_id, github_outputs["artifact_id"])
        self.assertEqual("generic-file", github_outputs["artifact_kind"])
        self.assertEqual(str(expected_manifest_path), github_outputs["artifact_manifest_path"])
        self.assertEqual(str(expected_manifest_path.parent), github_outputs["artifact_bundle_dir"])

    def test_record_artifact_generic_file_rejects_mismatched_explicit_sha512(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
        artifact_file_path = sandbox_dir / "buildish-example-bootstrap.zip"
        artifact_file_path.write_bytes(b"bootstrap payload\n")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )

        completed = run_cli(
            [
                "record-artifact",
                "--component-config",
                str(config_path),
                "--kind",
                "generic-file",
                "--artifact-id",
                "bootstrap-zip",
                "--file",
                str(artifact_file_path),
                "--uri",
                "https://github.com/apache/buildish-example/releases/download/v1.2.3-rc0/buildish-example-bootstrap.zip",
                "--sha512",
                "0" * 128,
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "generic-file --sha512 does not match the bytes of --file",
            completed.stderr,
        )

    def test_record_artifact_oci_image_command_writes_manifest_bundle(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
        github_output_path = sandbox_dir / "record-artifact.outputs"
        component_id = "buildish-example"
        artifact_id = "ghcr-main-image"
        digest = "SHA256:" + ("A1" * 32)
        amd64_digest = "sha256:" + ("b2" * 32)
        arm64_digest = "sha256:" + ("c3" * 32)
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )

        completed = run_cli(
            [
                "record-artifact",
                "--component-config",
                str(config_path),
                "--kind",
                "oci-image",
                "--artifact-id",
                artifact_id,
                "--role",
                "container-image",
                "--registry",
                "ghcr.io",
                "--repository",
                "apache/buildish-example",
                "--digest",
                digest,
                "--platform-digest",
                f"linux/amd64={amd64_digest}",
                "--platform-digest",
                f"linux/arm64={arm64_digest}",
                "--artifact-origin",
                "source-commit",
                "--git-commit-sha",
                "0123456789abcdef0123456789abcdef01234567",
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path, extra_env={"GITHUB_OUTPUT": str(github_output_path)}),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        expected_bundle_dir = (
            sandbox_dir
            / "build"
            / "release-artifacts"
            / component_id
            / "secondary-artifacts"
            / artifact_id
        )
        expected_manifest_path = expected_bundle_dir / "artifact-manifest.json"
        self.assertEqual(str(expected_manifest_path), completed.stdout.strip())
        action_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(component_id, action_manifest["component"])
        self.assertEqual("record-artifact", action_manifest["action"])
        self.assertEqual(artifact_id, action_manifest["artifact_id"])
        self.assertEqual("oci-image", action_manifest["kind"])
        self.assertEqual(str(expected_manifest_path), action_manifest["artifact_manifest_path"])
        self.assertEqual(str(expected_bundle_dir), action_manifest["artifact_bundle_dir"])
        self.assertEqual([], action_manifest["inventory_paths"])

        payload = json.loads(expected_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [
                {
                    "artifact_id": artifact_id,
                    "kind": "oci-image",
                    "role": "container-image",
                    "uri": f"oci://ghcr.io/apache/buildish-example@{digest.lower()}",
                    "registry": "ghcr.io",
                    "repository": "apache/buildish-example",
                    "digest": digest.lower(),
                    "platform_digests": [
                        {
                            "platform": "linux/amd64",
                            "digest": amd64_digest,
                        },
                        {
                            "platform": "linux/arm64",
                            "digest": arm64_digest,
                        },
                    ],
                    "artifact_origin": "source-commit",
                    "git_commit_sha": "0123456789abcdef0123456789abcdef01234567",
                }
            ],
            payload["secondary_artifacts"],
        )
        github_outputs = _read_simple_github_outputs(github_output_path)
        self.assertEqual(artifact_id, github_outputs["artifact_id"])
        self.assertEqual("oci-image", github_outputs["artifact_kind"])
        self.assertEqual(str(expected_manifest_path), github_outputs["artifact_manifest_path"])
        self.assertEqual(str(expected_bundle_dir), github_outputs["artifact_bundle_dir"])

    def test_record_artifact_oci_image_command_derives_manifest_bundle_from_multiplatform_image_ref(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
        github_output_path = sandbox_dir / "record-artifact.outputs"
        docker_path, docker_state_dir = create_fake_docker_launcher(sandbox_dir)
        component_id = "buildish-example"
        artifact_id = "ghcr-main-image"
        top_level_digest = "sha256:" + ("d4" * 32)
        amd64_digest = "sha256:" + ("a1" * 32)
        arm64_digest = "sha256:" + ("b2" * 32)
        (docker_state_dir / "imagetools-inspect-response.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 2,
                    "mediaType": "application/vnd.oci.image.index.v1+json",
                    "digest": top_level_digest,
                    "size": 855,
                    "manifests": [
                        {
                            "mediaType": "application/vnd.oci.image.manifest.v1+json",
                            "digest": amd64_digest,
                            "size": 673,
                            "platform": {"architecture": "amd64", "os": "linux"},
                        },
                        {
                            "mediaType": "application/vnd.oci.image.manifest.v1+json",
                            "digest": arm64_digest,
                            "size": 677,
                            "platform": {"architecture": "arm64", "os": "linux", "variant": "v8"},
                        },
                        {
                            "mediaType": "application/vnd.oci.image.manifest.v1+json",
                            "digest": "sha256:" + ("c3" * 32),
                            "size": 839,
                            "annotations": {"vnd.docker.reference.type": "attestation-manifest"},
                            "platform": {"architecture": "unknown", "os": "unknown"},
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )

        completed = run_cli(
            [
                "record-artifact",
                "--component-config",
                str(config_path),
                "--kind",
                "oci-image",
                "--artifact-id",
                artifact_id,
                "--role",
                "container-image",
                "--image-ref",
                "ghcr.io/apache/buildish-example:1.2.3",
                "--artifact-origin",
                "source-commit",
                "--git-commit-sha",
                "0123456789abcdef0123456789abcdef01234567",
            ],
            cwd=sandbox_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_DOCKER_STATE_DIR": str(docker_state_dir), "GITHUB_OUTPUT": str(github_output_path)},
                prepend_dirs=(docker_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        expected_bundle_dir = (
            sandbox_dir
            / "build"
            / "release-artifacts"
            / component_id
            / "secondary-artifacts"
            / artifact_id
        )
        expected_manifest_path = expected_bundle_dir / "artifact-manifest.json"
        self.assertEqual(str(expected_manifest_path), completed.stdout.strip())
        payload = json.loads(expected_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [
                {
                    "artifact_id": artifact_id,
                    "kind": "oci-image",
                    "role": "container-image",
                    "uri": f"oci://ghcr.io/apache/buildish-example@{top_level_digest}",
                    "registry": "ghcr.io",
                    "repository": "apache/buildish-example",
                    "digest": top_level_digest,
                    "platform_digests": [
                        {
                            "platform": "linux/amd64",
                            "digest": amd64_digest,
                        },
                        {
                            "platform": "linux/arm64/v8",
                            "digest": arm64_digest,
                        },
                    ],
                    "artifact_origin": "source-commit",
                    "git_commit_sha": "0123456789abcdef0123456789abcdef01234567",
                }
            ],
            payload["secondary_artifacts"],
        )
        self.assertEqual(
            ["ghcr.io/apache/buildish-example:1.2.3|{{json .Manifest}}"],
            (docker_state_dir / "imagetools-inspect.log").read_text(encoding="utf-8").splitlines(),
        )

    def test_record_artifact_oci_image_command_derives_manifest_bundle_from_single_platform_image_ref(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
        docker_path, docker_state_dir = create_fake_docker_launcher(sandbox_dir)
        top_level_digest = "sha256:" + ("e5" * 32)
        (docker_state_dir / "imagetools-inspect-response.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 2,
                    "mediaType": "application/vnd.oci.image.manifest.v1+json",
                    "digest": top_level_digest,
                    "size": 1054,
                    "config": {"mediaType": "application/vnd.oci.image.config.v1+json"},
                    "layers": [],
                }
            ),
            encoding="utf-8",
        )
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )

        completed = run_cli(
            [
                "record-artifact",
                "--component-config",
                str(config_path),
                "--kind",
                "oci-image",
                "--artifact-id",
                "dockerhub-single-platform",
                "--image-ref",
                "apache/buildish-example:1.2.3",
            ],
            cwd=sandbox_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_DOCKER_STATE_DIR": str(docker_state_dir)},
                prepend_dirs=(docker_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        expected_manifest_path = (
            sandbox_dir
            / "build"
            / "release-artifacts"
            / "buildish-example"
            / "secondary-artifacts"
            / "dockerhub-single-platform"
            / "artifact-manifest.json"
        )
        payload = json.loads(expected_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [
                {
                    "artifact_id": "dockerhub-single-platform",
                    "kind": "oci-image",
                    "uri": f"oci://docker.io/apache/buildish-example@{top_level_digest}",
                    "registry": "docker.io",
                    "repository": "apache/buildish-example",
                    "digest": top_level_digest,
                }
            ],
            payload["secondary_artifacts"],
        )

    def test_record_artifact_oci_image_rejects_image_ref_mixed_with_manual_fields(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )

        completed = run_cli(
            [
                "record-artifact",
                "--component-config",
                str(config_path),
                "--kind",
                "oci-image",
                "--artifact-id",
                "ghcr-main-image",
                "--image-ref",
                "ghcr.io/apache/buildish-example:1.2.3",
                "--digest",
                "sha256:" + ("0f" * 32),
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "oci-image --image-ref cannot be combined with --registry, --repository, --digest, or --platform-digest",
            completed.stderr,
        )

    def test_record_artifact_oci_image_rejects_invalid_digest(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )

        completed = run_cli(
            [
                "record-artifact",
                "--component-config",
                str(config_path),
                "--kind",
                "oci-image",
                "--artifact-id",
                "ghcr-main-image",
                "--registry",
                "ghcr.io",
                "--repository",
                "apache/buildish-example",
                "--digest",
                "not-a-digest",
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "oci-image --digest must be an OCI content digest like sha256:<hex>",
            completed.stderr,
        )

    def test_record_artifact_python_distribution_command_writes_manifest_bundle(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
        github_output_path = sandbox_dir / "record-artifact.outputs"
        artifact_file_path = sandbox_dir / "dist" / "example-1.2.3-py3-none-any.whl"
        artifact_file_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_file_path.write_bytes(b"wheel payload\n")
        expected_sha256 = hashlib.sha256(artifact_file_path.read_bytes()).hexdigest()
        component_id = "buildish-example"
        artifact_id = "pypi-wheel"
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )

        completed = run_cli(
            [
                "record-artifact",
                "--component-config",
                str(config_path),
                "--kind",
                "python-distribution",
                "--artifact-id",
                artifact_id,
                "--role",
                "wheel",
                "--file",
                str(artifact_file_path),
                "--uri",
                "https://test.pypi.org/packages/example-1.2.3-py3-none-any.whl",
                "--index-url",
                "https://test.pypi.org/simple/",
                "--project-name",
                "example",
                "--package-version",
                "1.2.3",
                "--sha256-uri",
                "https://test.pypi.org/packages/example-1.2.3-py3-none-any.whl.sha256",
                "--attestation-repository",
                "apache/buildish-example",
                "--artifact-origin",
                "source-commit",
                "--git-commit-sha",
                "0123456789abcdef0123456789abcdef01234567",
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path, extra_env={"GITHUB_OUTPUT": str(github_output_path)}),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        expected_bundle_dir = (
            sandbox_dir
            / "build"
            / "release-artifacts"
            / component_id
            / "secondary-artifacts"
            / artifact_id
        )
        expected_manifest_path = expected_bundle_dir / "artifact-manifest.json"
        self.assertEqual(str(expected_manifest_path), completed.stdout.strip())
        action_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(component_id, action_manifest["component"])
        self.assertEqual("record-artifact", action_manifest["action"])
        self.assertEqual(artifact_id, action_manifest["artifact_id"])
        self.assertEqual("python-distribution", action_manifest["kind"])
        self.assertEqual(str(expected_manifest_path), action_manifest["artifact_manifest_path"])
        self.assertEqual(str(expected_bundle_dir), action_manifest["artifact_bundle_dir"])
        self.assertEqual([], action_manifest["inventory_paths"])

        payload = json.loads(expected_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [
                {
                    "artifact_id": artifact_id,
                    "kind": "python-distribution",
                    "role": "wheel",
                    "filename": "example-1.2.3-py3-none-any.whl",
                    "uri": "https://test.pypi.org/packages/example-1.2.3-py3-none-any.whl",
                    "index_url": "https://test.pypi.org/simple/",
                    "project_name": "example",
                    "version": "1.2.3",
                    "artifact_origin": "source-commit",
                    "git_commit_sha": "0123456789abcdef0123456789abcdef01234567",
                    "checksums": {
                        "sha256": {
                            "value": expected_sha256,
                            "uri": "https://test.pypi.org/packages/example-1.2.3-py3-none-any.whl.sha256",
                        }
                    },
                    "authenticity": {
                        "scheme": "pypi-attestation",
                        "repository": "apache/buildish-example",
                    },
                }
            ],
            payload["secondary_artifacts"],
        )
        github_outputs = _read_simple_github_outputs(github_output_path)
        self.assertEqual(artifact_id, github_outputs["artifact_id"])
        self.assertEqual("python-distribution", github_outputs["artifact_kind"])
        self.assertEqual(str(expected_manifest_path), github_outputs["artifact_manifest_path"])
        self.assertEqual(str(expected_bundle_dir), github_outputs["artifact_bundle_dir"])

    def test_record_artifact_python_distribution_rejects_mismatched_explicit_sha256(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
        artifact_file_path = sandbox_dir / "dist" / "example-1.2.3-py3-none-any.whl"
        artifact_file_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_file_path.write_bytes(b"wheel payload\n")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )

        completed = run_cli(
            [
                "record-artifact",
                "--component-config",
                str(config_path),
                "--kind",
                "python-distribution",
                "--artifact-id",
                "pypi-wheel",
                "--file",
                str(artifact_file_path),
                "--uri",
                "https://test.pypi.org/packages/example-1.2.3-py3-none-any.whl",
                "--index-url",
                "https://test.pypi.org/simple/",
                "--project-name",
                "example",
                "--package-version",
                "1.2.3",
                "--sha256",
                "0" * 64,
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "python-distribution --sha256 does not match the bytes of --file",
            completed.stderr,
        )

    def test_record_artifact_maven_repository_command_writes_inventory_bundle(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
        github_output_path = sandbox_dir / "record-artifact.outputs"
        component_id = "buildish-example"
        artifact_id = "maven-staging-main"
        staging_repository_id = "orgapacheexample-1234"
        repository_root = sandbox_dir / staging_repository_id
        expected_sha512_by_path, expected_sizes_by_path = _write_test_maven_repository(repository_root)
        base_url = f"{repository_root.as_uri()}/"
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )

        completed = run_cli(
            [
                "record-artifact",
                "--component-config",
                str(config_path),
                "--kind",
                "maven-repository",
                "--artifact-id",
                artifact_id,
                "--role",
                "maven-staging",
                "--base-url",
                base_url,
                "--staging-repository-id",
                staging_repository_id,
                "--inventory-workers",
                "1",
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path, extra_env={"GITHUB_OUTPUT": str(github_output_path)}),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        expected_bundle_dir = (
            sandbox_dir
            / "build"
            / "release-artifacts"
            / component_id
            / "secondary-artifacts"
            / artifact_id
        )
        expected_manifest_path = expected_bundle_dir / "artifact-manifest.json"
        expected_inventory_path = expected_bundle_dir / f"{artifact_id}-inventory.json"
        expected_inventory_sha512 = hashlib.sha512(expected_inventory_path.read_bytes()).hexdigest()
        self.assertEqual(str(expected_manifest_path), completed.stdout.strip())
        action_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(component_id, action_manifest["component"])
        self.assertEqual("record-artifact", action_manifest["action"])
        self.assertEqual(artifact_id, action_manifest["artifact_id"])
        self.assertEqual("maven-repository", action_manifest["kind"])
        self.assertEqual(str(expected_manifest_path), action_manifest["artifact_manifest_path"])
        self.assertEqual(str(expected_bundle_dir), action_manifest["artifact_bundle_dir"])
        self.assertEqual([str(expected_inventory_path)], action_manifest["inventory_paths"])

        payload = json.loads(expected_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [
                {
                    "artifact_id": artifact_id,
                    "kind": "maven-repository",
                    "role": "maven-staging",
                    "staging_repository_id": staging_repository_id,
                    "base_url": base_url,
                    "inventory": {
                        "filename": f"{artifact_id}-inventory.json",
                        "sha512": expected_inventory_sha512,
                        "entry_count": len(expected_sha512_by_path),
                        "total_size_bytes": sum(expected_sizes_by_path.values()),
                    },
                }
            ],
            payload["secondary_artifacts"],
        )
        inventory_payload = json.loads(expected_inventory_path.read_text(encoding="utf-8"))
        self.assertEqual("1", inventory_payload["schema_version"])
        self.assertEqual("maven-repository", inventory_payload["inventory_type"])
        self.assertEqual(artifact_id, inventory_payload["artifact_id"])
        self.assertEqual(staging_repository_id, inventory_payload["staging_repository_id"])
        self.assertEqual(base_url, inventory_payload["base_url"])
        inventory_entries = {entry["path"]: entry for entry in inventory_payload["entries"]}
        self.assertEqual(sorted(expected_sha512_by_path), sorted(inventory_entries))
        for relative_path, expected_sha512 in expected_sha512_by_path.items():
            self.assertEqual(expected_sha512, inventory_entries[relative_path]["sha512"])
            self.assertEqual(expected_sizes_by_path[relative_path], inventory_entries[relative_path]["size_bytes"])

        github_outputs = _read_simple_github_outputs(github_output_path)
        self.assertEqual(artifact_id, github_outputs["artifact_id"])
        self.assertEqual("maven-repository", github_outputs["artifact_kind"])
        self.assertEqual(str(expected_manifest_path), github_outputs["artifact_manifest_path"])
        self.assertEqual(str(expected_bundle_dir), github_outputs["artifact_bundle_dir"])

    def test_record_artifact_maven_repository_command_reports_progress_when_enabled(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
        component_id = "buildish-example"
        artifact_id = "maven-staging-main"
        staging_repository_id = "orgapacheexample-1234"
        repository_root = sandbox_dir / staging_repository_id
        _write_test_maven_repository(repository_root)
        base_url = f"{repository_root.as_uri()}/"
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )

        completed = run_cli(
            [
                "record-artifact",
                "--component-config",
                str(config_path),
                "--progress",
                "on",
                "--kind",
                "maven-repository",
                "--artifact-id",
                artifact_id,
                "--base-url",
                base_url,
                "--staging-repository-id",
                staging_repository_id,
                "--inventory-workers",
                "1",
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path),
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        self.assertIn("progress: enumerating maven repository from ", completed.stderr)
        self.assertIn("progress: building maven repository inventory: 0/", completed.stderr)
        self.assertIn("progress: wrote maven repository inventory: ", completed.stderr)

    def test_finalize_rc_vote_materials_command_stages_manifest_and_mirrors_it(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for RC vote-manifest signing")
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        _repo_dir, repo_url, working_copy_dir = init_svn_repo_and_checkout(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        source_manifest_path = sandbox_dir / "build-source-rc.json"
        rc_tag_manifest_path = sandbox_dir / "create-rc-materialization-tag.json"
        record_artifact_manifest_path = sandbox_dir / "record-artifact.json"
        record_artifact_outputs_path = sandbox_dir / "record-artifact.outputs"
        finalize_manifest_path = sandbox_dir / "finalize-rc-vote-materials.json"
        client = AsfSvnClient()
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        keys_path = working_copy_dir / "dist" / "release" / "incubator" / "buildish" / "KEYS"
        source_home = sandbox_dir / "gpg-source"
        source_home.mkdir(parents=True, exist_ok=True)
        source_home.chmod(0o700)

        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=dev_base_url,
            release_base_url=release_base_url,
        )
        client.mkdir_url(dev_base_url, "create dev component path")
        client.mkdir_url(release_base_url, "create release component path")

        subprocess.run(
            [
                "gpg",
                "--batch",
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                "",
                "--quick-gen-key",
                "Release Tooling Tests <release-tooling-tests@example.invalid>",
                "ed25519",
                "sign",
                "1d",
            ],
            env={**os.environ, "GNUPGHOME": str(source_home)},
            check=True,
            capture_output=True,
            text=True,
        )
        public_key = subprocess.run(
            [
                "gpg",
                "--armor",
                "--export",
                "Release Tooling Tests <release-tooling-tests@example.invalid>",
            ],
            env={**os.environ, "GNUPGHOME": str(source_home)},
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        secret_key = subprocess.run(
            [
                "gpg",
                "--armor",
                "--export-secret-keys",
                "Release Tooling Tests <release-tooling-tests@example.invalid>",
            ],
            env={**os.environ, "GNUPGHOME": str(source_home)},
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        keys_path.write_text(public_key, encoding="utf-8")
        subprocess.run(["svn", "add", str(keys_path)], check=True)
        subprocess.run(["svn", "commit", "-m", "add KEYS", str(working_copy_dir)], check=True)
        bootstrap_asset_path = sandbox_dir / "buildish-example-bootstrap.zip"
        bootstrap_asset_path.write_bytes(b"bootstrap payload\n")
        expected_secondary_commit = git_rev_parse(
            clone_dir, "refs/remotes/origin/release/1.2.x^{commit}"
        )

        completed = run_cli(
            [
                "record-artifact",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "--kind",
                "generic-file",
                "--artifact-id",
                "bootstrap-zip",
                "--role",
                "bootstrap-convenience-archive",
                "--file",
                str(bootstrap_asset_path),
                "--uri",
                "https://github.com/apache/buildish-example/releases/download/v1.2.3/buildish-example-bootstrap.zip",
                "--sha512-uri",
                "https://github.com/apache/buildish-example/releases/download/v1.2.3/buildish-example-bootstrap.zip.sha512",
                "--artifact-origin",
                "source-commit",
                "--git-commit-sha",
                expected_secondary_commit,
            ],
            cwd=clone_dir,
            env=cli_env(
                record_artifact_manifest_path,
                extra_env={"GITHUB_OUTPUT": str(record_artifact_outputs_path)},
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        secondary_manifest_path = Path(
            _read_simple_github_outputs(record_artifact_outputs_path)["artifact_manifest_path"]
        )

        completed = run_cli(
            [
                "build-source-rc",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                source_manifest_path,
                extra_env={"BUILDISH_GPG_PRIVATE_KEY": secret_key},
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        completed = run_cli(
            [
                "create-rc-materialization-tag",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(rc_tag_manifest_path),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)

        set_github_origin_url(clone_dir, "apache/buildish-example")
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3-rc0",
                    "name": "Apache Buildish Example 1.2.3",
                    "html_url": "https://github.com/apache/buildish-example/releases/tag/v1.2.3-rc0",
                    "assets": [],
                }
            ],
        )
        completed = run_cli(
            [
                "finalize-rc-vote-materials",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "--secondary-artifact-manifest",
                str(secondary_manifest_path),
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                finalize_manifest_path,
                extra_env={
                    "BUILDISH_GPG_PRIVATE_KEY": secret_key,
                    "FAKE_GH_STATE_DIR": str(gh_state_dir),
                },
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(finalize_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("v1.2.3-rc0", manifest["rc_tag"])
        self.assertEqual(
            f"{dev_base_url}/1.2.3-rc0/rc-vote-manifest.json",
            manifest["authoritative_manifest_url"],
        )
        self.assertIn("rc-vote-manifest.json.asc", manifest["mirrored_asset_names"])
        self.assertTrue(manifest["gpg_fingerprint"])
        self.assertEqual(
            [
                "rc-vote-manifest.json",
                "rc-vote-manifest.json.asc",
                "rc-vote-manifest.json.sha512",
            ],
            sorted(
                entry
                for entry in client.list_entries(f"{dev_base_url}/1.2.3-rc0")
                if entry.startswith("rc-vote-manifest.json")
            ),
        )
        staged_manifest = json.loads(
            subprocess.run(
                [
                    "svn",
                    "cat",
                    f"{dev_base_url}/1.2.3-rc0/rc-vote-manifest.json",
                ],
                check=True,
                text=True,
                capture_output=True,
            ).stdout
        )
        self.assertEqual("rc-vote", staged_manifest["manifest_type"])
        self.assertEqual(component_id, staged_manifest["component_id"])
        self.assertEqual("v1.2.3-rc0", staged_manifest["rc_tag"])
        self.assertEqual(
            "bootstrap-zip",
            staged_manifest["vote_materials"]["secondary_artifacts"][0]["artifact_id"],
        )
        self.assertEqual(
            "generic-file",
            staged_manifest["vote_materials"]["secondary_artifacts"][0]["kind"],
        )
        self.assertEqual(
            "https://github.com/apache/buildish-example/releases/download/v1.2.3/buildish-example-bootstrap.zip",
            staged_manifest["vote_materials"]["secondary_artifacts"][0]["uri"],
        )
        self.assertEqual(
            "https://github.com/apache/buildish-example/releases/tag/v1.2.3-rc0",
            staged_manifest["draft_github_release"]["url"],
        )
        self.assertEqual("v1.2.3-rc0", staged_manifest["draft_github_release"]["tag"])
        self.assertEqual(
            [
                str(clone_dir / "build" / "release-artifacts" / component_id / "rc-vote-manifest.json"),
                str(clone_dir / "build" / "release-artifacts" / component_id / "rc-vote-manifest.json.sha512"),
                str(clone_dir / "build" / "release-artifacts" / component_id / "rc-vote-manifest.json.asc"),
            ],
            (gh_state_dir / "release-upload-files.log").read_text(encoding="utf-8").splitlines(),
        )
        self.assertEqual(
            "v1.2.3-rc0",
            (gh_state_dir / "release-upload-tag.txt").read_text(encoding="utf-8").strip(),
        )
        summary_text = finalize_manifest_path.with_suffix(".summary.md").read_text(encoding="utf-8")
        self.assertIn("Finalize RC vote materials for version 1.2.3", summary_text)
        self.assertIn("### Technical details", summary_text)
        self.assertIn("### RC vote manifest", summary_text)
        self.assertIn('"manifest_type": "rc-vote"', summary_text)
        self.assertIn("Project vote subject", summary_text)
        self.assertIn("Please vote in the next 72 hours.", summary_text)
        self.assertIn(f"{release_base_url.rsplit('/', 1)[0]}/KEYS", summary_text)

    def test_finalize_rc_vote_materials_command_stages_maven_repository_inventory(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for RC vote-manifest signing")
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        _repo_dir, repo_url, working_copy_dir = init_svn_repo_and_checkout(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        source_manifest_path = sandbox_dir / "build-source-rc.json"
        rc_tag_manifest_path = sandbox_dir / "create-rc-materialization-tag.json"
        record_artifact_manifest_path = sandbox_dir / "record-artifact.json"
        record_artifact_outputs_path = sandbox_dir / "record-artifact.outputs"
        finalize_manifest_path = sandbox_dir / "finalize-rc-vote-materials.json"
        client = AsfSvnClient()
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        keys_path = working_copy_dir / "dist" / "release" / "incubator" / "buildish" / "KEYS"
        source_home = sandbox_dir / "gpg-source"
        source_home.mkdir(parents=True, exist_ok=True)
        source_home.chmod(0o700)
        staging_repository_id = "orgapacheexample-1234"
        repository_root = sandbox_dir / staging_repository_id
        _write_test_maven_repository(repository_root)
        base_url = f"{repository_root.as_uri()}/"

        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=dev_base_url,
            release_base_url=release_base_url,
        )
        client.mkdir_url(dev_base_url, "create dev component path")
        client.mkdir_url(release_base_url, "create release component path")

        subprocess.run(
            [
                "gpg",
                "--batch",
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                "",
                "--quick-gen-key",
                "Release Tooling Tests <release-tooling-tests@example.invalid>",
                "ed25519",
                "sign",
                "1d",
            ],
            env={**os.environ, "GNUPGHOME": str(source_home)},
            check=True,
            capture_output=True,
            text=True,
        )
        public_key = subprocess.run(
            [
                "gpg",
                "--armor",
                "--export",
                "Release Tooling Tests <release-tooling-tests@example.invalid>",
            ],
            env={**os.environ, "GNUPGHOME": str(source_home)},
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        secret_key = subprocess.run(
            [
                "gpg",
                "--armor",
                "--export-secret-keys",
                "Release Tooling Tests <release-tooling-tests@example.invalid>",
            ],
            env={**os.environ, "GNUPGHOME": str(source_home)},
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        keys_path.write_text(public_key, encoding="utf-8")
        subprocess.run(["svn", "add", str(keys_path)], check=True)
        subprocess.run(["svn", "commit", "-m", "add KEYS", str(working_copy_dir)], check=True)

        completed = run_cli(
            [
                "record-artifact",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "--kind",
                "maven-repository",
                "--artifact-id",
                "maven-staging-main",
                "--role",
                "maven-staging",
                "--base-url",
                base_url,
                "--staging-repository-id",
                staging_repository_id,
                "--inventory-workers",
                "1",
            ],
            cwd=clone_dir,
            env=cli_env(
                record_artifact_manifest_path,
                extra_env={"GITHUB_OUTPUT": str(record_artifact_outputs_path)},
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        secondary_manifest_path = Path(
            _read_simple_github_outputs(record_artifact_outputs_path)["artifact_manifest_path"]
        )
        local_inventory_path = secondary_manifest_path.parent / "maven-staging-main-inventory.json"

        completed = run_cli(
            [
                "build-source-rc",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                source_manifest_path,
                extra_env={"BUILDISH_GPG_PRIVATE_KEY": secret_key},
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        completed = run_cli(
            [
                "create-rc-materialization-tag",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(rc_tag_manifest_path),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)

        set_github_origin_url(clone_dir, "apache/buildish-example")
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3-rc0",
                    "name": "Apache Buildish Example 1.2.3",
                    "html_url": "https://github.com/apache/buildish-example/releases/tag/v1.2.3-rc0",
                    "assets": [],
                }
            ],
        )
        completed = run_cli(
            [
                "finalize-rc-vote-materials",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "--secondary-artifact-manifest",
                str(secondary_manifest_path),
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                finalize_manifest_path,
                extra_env={
                    "BUILDISH_GPG_PRIVATE_KEY": secret_key,
                    "FAKE_GH_STATE_DIR": str(gh_state_dir),
                },
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        staged_manifest = json.loads(
            subprocess.run(
                [
                    "svn",
                    "cat",
                    f"{dev_base_url}/1.2.3-rc0/rc-vote-manifest.json",
                ],
                check=True,
                text=True,
                capture_output=True,
            ).stdout
        )
        secondary_artifact = staged_manifest["vote_materials"]["secondary_artifacts"][0]
        self.assertEqual("maven-repository", secondary_artifact["kind"])
        self.assertEqual("maven-staging-main", secondary_artifact["artifact_id"])
        self.assertEqual(staging_repository_id, secondary_artifact["staging_repository_id"])
        self.assertEqual(base_url, secondary_artifact["base_url"])
        self.assertEqual("maven-staging-main-inventory.json", secondary_artifact["inventory"]["filename"])
        self.assertEqual(
            f"{dev_base_url}/1.2.3-rc0/maven-staging-main-inventory.json",
            secondary_artifact["inventory"]["uri"],
        )
        self.assertEqual(
            hashlib.sha512(local_inventory_path.read_bytes()).hexdigest(),
            secondary_artifact["inventory"]["sha512"],
        )
        self.assertIn(
            "maven-staging-main-inventory.json",
            client.list_entries(f"{dev_base_url}/1.2.3-rc0"),
        )
        staged_inventory = json.loads(
            subprocess.run(
                [
                    "svn",
                    "cat",
                    f"{dev_base_url}/1.2.3-rc0/maven-staging-main-inventory.json",
                ],
                check=True,
                text=True,
                capture_output=True,
            ).stdout
        )
        self.assertEqual(
            json.loads(local_inventory_path.read_text(encoding="utf-8")),
            staged_inventory,
        )
        uploaded_paths = (gh_state_dir / "release-upload-files.log").read_text(encoding="utf-8").splitlines()
        self.assertIn(str(local_inventory_path), uploaded_paths)

    def test_finalize_rc_vote_materials_rejects_staged_source_artifact_drift(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for RC vote-manifest signing")
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        _repo_dir, repo_url, working_copy_dir = init_svn_repo_and_checkout(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        source_manifest_path = sandbox_dir / "build-source-rc.json"
        rc_tag_manifest_path = sandbox_dir / "create-rc-materialization-tag.json"
        finalize_manifest_path = sandbox_dir / "finalize-rc-vote-materials.json"
        client = AsfSvnClient()
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        keys_path = working_copy_dir / "dist" / "release" / "incubator" / "buildish" / "KEYS"
        source_home = sandbox_dir / "gpg-source"
        source_home.mkdir(parents=True, exist_ok=True)
        source_home.chmod(0o700)

        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=dev_base_url,
            release_base_url=release_base_url,
        )
        client.mkdir_url(dev_base_url, "create dev component path")
        client.mkdir_url(release_base_url, "create release component path")

        subprocess.run(
            [
                "gpg",
                "--batch",
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                "",
                "--quick-gen-key",
                "Release Tooling Tests <release-tooling-tests@example.invalid>",
                "ed25519",
                "sign",
                "1d",
            ],
            env={**os.environ, "GNUPGHOME": str(source_home)},
            check=True,
            capture_output=True,
            text=True,
        )
        public_key = subprocess.run(
            [
                "gpg",
                "--armor",
                "--export",
                "Release Tooling Tests <release-tooling-tests@example.invalid>",
            ],
            env={**os.environ, "GNUPGHOME": str(source_home)},
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        secret_key = subprocess.run(
            [
                "gpg",
                "--armor",
                "--export-secret-keys",
                "Release Tooling Tests <release-tooling-tests@example.invalid>",
            ],
            env={**os.environ, "GNUPGHOME": str(source_home)},
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        keys_path.write_text(public_key, encoding="utf-8")
        subprocess.run(["svn", "add", str(keys_path)], check=True)
        subprocess.run(["svn", "commit", "-m", "add KEYS", str(working_copy_dir)], check=True)

        completed = run_cli(
            [
                "build-source-rc",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                source_manifest_path,
                extra_env={"BUILDISH_GPG_PRIVATE_KEY": secret_key},
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        completed = run_cli(
            [
                "create-rc-materialization-tag",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(rc_tag_manifest_path),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)

        subprocess.run(["svn", "update", str(working_copy_dir)], check=True, capture_output=True, text=True)
        drifted_artifact = (
            working_copy_dir
            / "dist"
            / "dev"
            / "incubator"
            / "buildish"
            / component_id
            / "1.2.3-rc0"
            / "apache-buildish-example-1.2.3-incubating-src.tar.gz"
        )
        drifted_artifact.write_bytes(b"drifted source payload\n")
        subprocess.run(["svn", "commit", "-m", "drift staged artifact", str(working_copy_dir)], check=True)

        set_github_origin_url(clone_dir, "apache/buildish-example")
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3-rc0",
                    "name": "Apache Buildish Example 1.2.3",
                    "html_url": "https://github.com/apache/buildish-example/releases/tag/v1.2.3-rc0",
                    "body": "\n".join(
                        [
                            "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "RC tag: v1.2.3-rc0",
                            f"Resolved source ref: {git_rev_parse(clone_dir, 'v1.2.3-rc0^{commit}')}",
                        ]
                    ),
                    "assets": [],
                }
            ],
        )
        completed = run_cli(
            [
                "finalize-rc-vote-materials",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                finalize_manifest_path,
                extra_env={
                    "BUILDISH_GPG_PRIVATE_KEY": secret_key,
                    "FAKE_GH_STATE_DIR": str(gh_state_dir),
                },
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "staged source artifact .sha512 sidecar does not match the staged source artifact bytes",
            completed.stderr,
        )

    def test_create_release_branch_command_applies_changes_when_requested(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "create-release-branch.json"
        git_create_branch(origin_dir, "release/1.x")
        fetch_git_origin_refs(clone_dir)
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        completed = run_cli(
            [
                "create-release-branch",
                "--component-config",
                str(config_path),
                "--apply",
                "1.2.x",
                "release/1.x",
            ],
            cwd=clone_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("release/1.2.x", manifest["release_branch"])
        created_commit = git_rev_parse(clone_dir, "refs/heads/release/1.2.x^{commit}")
        source_commit = git_rev_parse(clone_dir, "refs/remotes/origin/release/1.x^{commit}")
        self.assertEqual(source_commit, created_commit)

    def test_publish_atr_candidate_command_uploads_staged_candidate_files(self) -> None:
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        _repo_dir, repo_url, working_copy_dir = init_svn_repo_and_checkout(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "publish-atr-candidate.json"
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc0")
        fetch_git_origin_refs(clone_dir)
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=dev_base_url,
            release_base_url=release_base_url,
            atr_lines=(
                "atr:",
                "  enabled: true",
                "  base_url: https://release-test.apache.org",
                "  committee: buildish",
                "  product_line: buildish-example",
                "  strict_checking: false",
                "  source_artifact_paths:",
                '    - "**/*-src.tar.gz"',
            ),
        )
        AsfSvnClient().mkdir_url(dev_base_url, "create dev component path")
        AsfSvnClient().mkdir_url(release_base_url, "create release component path")
        artifact_sha512 = self._stage_source_release_files(
            sandbox_dir,
            working_copy_dir,
            component_id=component_id,
            version="1.2.3",
            rc_number=0,
        )
        self._stage_rc_vote_manifest_files(
            working_copy_dir,
            component_id=component_id,
            version="1.2.3",
            rc_number=0,
            repo_url=repo_url,
            artifact_sha512=artifact_sha512,
        )
        atr_path, atr_state_dir = create_fake_atr_launcher(sandbox_dir)
        completed = run_cli(
            [
                "publish-atr-candidate",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "--wait-for-checks",
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={
                    "BUILDISH_ATR_ASF_UID": "wave",
                    "BUILDISH_ATR_PAT": "secret-pat",
                    "FAKE_ATR_STATE_DIR": str(atr_state_dir),
                    "FAKE_ATR_STATUS_OUTPUT": "Total checks: 6\n  success: 6\n",
                },
                prepend_dirs=(atr_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("buildish-example", manifest["atr_project"])
        self.assertEqual("created", manifest["atr_release_mode"])
        self.assertEqual("00007", manifest["atr_latest_revision"])
        self.assertEqual("true", manifest["waited_for_checks"])
        self.assertEqual("6", manifest["atr_total_checks"])
        self.assertEqual(
            [
                "apache-buildish-example-1.2.3-incubating-src.tar.gz",
                "apache-buildish-example-1.2.3-incubating-src.tar.gz.sha512",
                "apache-buildish-example-1.2.3-incubating-src.tar.gz.asc",
                "rc-vote-manifest.json",
                "rc-vote-manifest.json.sha512",
                "rc-vote-manifest.json.asc",
            ],
            (atr_state_dir / "upload-paths.log").read_text(encoding="utf-8").splitlines(),
        )
        self.assertIn(
            "release-test.apache.org",
            (atr_state_dir / "seen-hosts.log").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "wave",
            (atr_state_dir / "seen-asf-uids.log").read_text(encoding="utf-8"),
        )
        summary_text = manifest_path.with_suffix(".summary.md").read_text(encoding="utf-8")
        self.assertIn("Publish ATR candidate", summary_text)
        self.assertIn("Total checks: 6", summary_text)

    def test_report_atr_checks_command_is_advisory_when_strict_checking_is_disabled(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "report-atr-checks.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc0")
        fetch_git_origin_refs(clone_dir)
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
            atr_lines=(
                "atr:",
                "  enabled: true",
                "  base_url: https://release-test.apache.org",
                "  committee: buildish",
                "  product_line: buildish-example",
                "  strict_checking: false",
            ),
        )
        atr_path, atr_state_dir = create_fake_atr_launcher(sandbox_dir)
        (atr_state_dir / "state.json").write_text(
            json.dumps(
                {
                    "releases": {
                        "buildish-example/1.2.3": {
                            "project": "buildish-example",
                            "version": "1.2.3",
                            "phase": "release_candidate_draft",
                            "latest_revision_number": "00007",
                            "next_revision": 8,
                            "uploads": [],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        completed = run_cli(
            [
                "report-atr-checks",
                "--component-config",
                str(config_path),
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={
                    "BUILDISH_ATR_ASF_UID": "wave",
                    "BUILDISH_ATR_PAT": "secret-pat",
                    "FAKE_ATR_STATE_DIR": str(atr_state_dir),
                    "FAKE_ATR_STATUS_OUTPUT": "Total checks: 3\n  failure: 1\n  warning: 1\n  success: 1\n",
                },
                prepend_dirs=(atr_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("00007", manifest["atr_reported_revision"])
        self.assertEqual("1", manifest["atr_failure_count"])
        self.assertEqual("false", manifest["would_block_release"])

    def test_report_atr_checks_command_fails_when_strict_checking_is_enabled(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "report-atr-checks.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc0")
        fetch_git_origin_refs(clone_dir)
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
            atr_lines=(
                "atr:",
                "  enabled: true",
                "  base_url: https://release-test.apache.org",
                "  committee: buildish",
                "  product_line: buildish-example",
                "  strict_checking: true",
            ),
        )
        atr_path, atr_state_dir = create_fake_atr_launcher(sandbox_dir)
        (atr_state_dir / "state.json").write_text(
            json.dumps(
                {
                    "releases": {
                        "buildish-example/1.2.3": {
                            "project": "buildish-example",
                            "version": "1.2.3",
                            "phase": "release_candidate_draft",
                            "latest_revision_number": "00007",
                            "next_revision": 8,
                            "uploads": [],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        completed = run_cli(
            [
                "report-atr-checks",
                "--component-config",
                str(config_path),
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={
                    "BUILDISH_ATR_ASF_UID": "wave",
                    "BUILDISH_ATR_PAT": "secret-pat",
                    "FAKE_ATR_STATE_DIR": str(atr_state_dir),
                    "FAKE_ATR_STATUS_OUTPUT": "Total checks: 3\n  failure: 1\n  warning: 1\n  success: 1\n",
                },
                prepend_dirs=(atr_path.parent,),
            ),
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn("ATR strict checking is enabled", completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("true", manifest["would_block_release"])
        summary_text = manifest_path.with_suffix(".summary.md").read_text(encoding="utf-8")
        self.assertIn("Report ATR checks", summary_text)
        self.assertIn("failure: 1", summary_text)
