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
"""Shared support for release command integration tests.

This module intentionally contains only reusable helpers, shared fixtures, and names re-exported for
split command test modules. The actual test bodies live in the command-group files under
`tests/release/commands/`.
"""

from __future__ import annotations

import base64
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
    checkout_svn_repo,
    cli_env,
    clone_git_origin,
    cleanup_sandbox,
    copy_test_tree,
    command_available,
    create_build_test_sandbox,
    create_fake_gpg_launcher,
    create_fake_atr_launcher,
    create_fake_docker_launcher,
    create_fake_gh_launcher,
    fetch_git_origin_refs,
    git_create_annotated_tag,
    git_create_branch,
    git_rev_parse,
    init_git_origin_and_clone,
    init_git_origin_repo,
    init_svn_repo,
    init_svn_repo_and_checkout,
    run_quiet,
    run_cli,
    set_github_origin_url,
)

__all__ = [
    "Any",
    "AsfSvnClient",
    "Mapping",
    "Path",
    "ReleaseCommandsIntegrationTestSupport",
    "Sequence",
    "_read_simple_github_outputs",
    "_write_test_maven_repository",
    "base64",
    "cast",
    "checkout_svn_repo",
    "cleanup_sandbox",
    "cli_env",
    "clone_git_origin",
    "copy_test_tree",
    "command_available",
    "create_build_test_sandbox",
    "create_fake_gpg_launcher",
    "create_fake_atr_launcher",
    "create_fake_docker_launcher",
    "create_fake_gh_launcher",
    "delete_remote_ref_best_effort",
    "fetch_git_origin_refs",
    "git_create_annotated_tag",
    "git_create_branch",
    "git_rev_parse",
    "hashlib",
    "init_git_origin_and_clone",
    "init_git_origin_repo",
    "init_svn_repo",
    "init_svn_repo_and_checkout",
    "json",
    "mock",
    "os",
    "push_remote_ref",
    "re",
    "run_quiet",
    "run_cli",
    "set_github_origin_url",
    "subprocess",
    "unittest",
]

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

class ReleaseCommandsIntegrationTestSupport(unittest.TestCase):
    """Shared sandbox helpers for release command integration tests."""

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
        project_status: str = "tlp",
        incubator_disclaimer_file: str = "DISCLAIMER",
        candidate_start_number: int = 0,
        asf_keys_url: str | None = None,
        atr_lines: tuple[str, ...] = (),
        verify_rc_lines: tuple[str, ...] = (),
    ) -> None:
        """Write a minimal component configuration used by CLI integration tests."""

        config_path.write_text(
            "\n".join(
                [
                    f"component_id: {component_id}",
                    f"source_artifact_prefix: apache-{component_id}",
                    f"asf_dist_dev_base: {dev_base_url}",
                    f"asf_dist_release_base: {release_base_url}",
                    f"asf_keys_url: {asf_keys_url or release_base_url.rsplit('/', 1)[0] + '/KEYS'}",
                    f"moving_tags_enabled: {'true' if moving_tags_enabled else 'false'}",
                    f"latest_tag_enabled: {'true' if latest_tag_enabled else 'false'}",
                    "secondary_targets:",
                    *[f"  - {target}" for target in secondary_targets],
                    f"final_tag_mode: {final_tag_mode}",
                    f"vote_release_name: {vote_release_name}",
                    f"project_status: {project_status}",
                    f"incubator_disclaimer_file: {incubator_disclaimer_file}",
                    f"candidate_start_number: {candidate_start_number}",
                    "release_verification_guide_url: https://buildish.apache.org/buildish-example/release-verification/",
                    "verify_rc_instructions: verify",
                    "prepare_rc_runs_tests: false",
                    "release_branch_ci_required: true",
                    *atr_lines,
                    *verify_rc_lines,
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
        run_quiet(["svn", "update", str(working_copy_dir)], check=True)
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
        run_quiet(
            ["svn", "add", "--force", str(target_dir)],
            check=True,
        )
        for source_path, destination_name in (
            (artifact_path, artifact_name),
            (sha512_path, f"{artifact_name}.sha512"),
            (asc_path, f"{artifact_name}.asc"),
        ):
            destination_path = target_dir / destination_name
            destination_path.write_bytes(source_path.read_bytes())
            run_quiet(
                ["svn", "add", "--force", str(destination_path)],
                check=True,
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
                "source_repository_url": "https://github.com/apache/buildish-example",
                "source_commit_sha": "0123456789abcdef0123456789abcdef01234567",
                "source_date_epoch": 1714132800,
                "rc_tag": f"v{version}-rc{rc_number}",
                "final_tag": f"v{version}",
                "final_tag_mode": "rc-source-commit",
                "provenance": {
                    "created_at": "2026-04-26T12:00:00Z",
                    "tooling": {
                        "repository": "apache/buildish-release-tooling",
                        "repository_url": "https://github.com/apache/buildish-release-tooling",
                        "git_commit_sha": "fedcba9876543210fedcba9876543210fedcba98",
                    },
                },
                "trust_roots": {
                    "asf_keys": {
                        "uri": f"{repo_url}/dist/release/incubator/buildish/KEYS",
                        "known_length_bytes": 9,
                        "known_prefix_sha512": "a" * 128,
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
        run_quiet(
            ["svn", "add", "--force", str(manifest_dir)],
            check=True,
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
            run_quiet(["svn", "add", "--force", str(path)], check=True)
        keys_path = (
            working_copy_dir / "dist" / "release" / "incubator" / "buildish" / "KEYS"
        )
        keys_path.write_text("test KEYS\n", encoding="utf-8")
        run_quiet(["svn", "add", "--parents", "--force", str(keys_path)], check=True)
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
        run_quiet(["git", "-C", str(origin_dir), "checkout", "release/1.2.x"], check=True)
        (origin_dir / ".gitignore").write_text("/dist/\n", encoding="utf-8")
        run_quiet(["git", "-C", str(origin_dir), "add", ".gitignore"], check=True)
        run_quiet(["git", "-C", str(origin_dir), "commit", "-m", "ignore dist"], check=True)
        run_quiet(["git", "-C", str(origin_dir), "checkout", "main"], check=True)
        fetch_git_origin_refs(clone_dir)
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
            final_tag_mode="detached-materialization-commit",
        )
        return sandbox_dir, origin_dir, clone_dir, config_path
