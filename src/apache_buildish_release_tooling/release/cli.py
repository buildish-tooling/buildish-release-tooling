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

"""CLI entrypoint for buildish-release-tooling."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from apache_buildish_release_tooling.release.artifact_registration import (
    registered_artifact_kinds,
)
from apache_buildish_release_tooling.release import commands

CommandHandler = Callable[[argparse.Namespace], Path | None]
Subparsers = argparse._SubParsersAction


def _common_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--component-config",
        dest="component_config",
        required=True,
        help="YAML component configuration path.",
    )
    parser.add_argument(
        "--allow-non-production-release-targets",
        action="store_true",
        help="Allow file:// and http:// ASF dist target URLs for local harness-style test runs.",
    )
    parser.add_argument(
        "--progress",
        choices=("auto", "on", "off"),
        default="auto",
        help="Progress reporting mode for long-running operations. Defaults to auto, which reports progress on interactive terminals only.",
    )
    return parser


def _add_command_parser(
    subparsers: Subparsers,
    common: argparse.ArgumentParser,
    name: str,
    *,
    help_text: str,
    handler: CommandHandler,
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(name, parents=[common], help=help_text)
    parser.set_defaults(handler=handler)
    return parser


def _add_version_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("version")


def _add_optional_source_sha_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source_sha", nargs="?")


def _add_version_and_optional_source_sha_arguments(parser: argparse.ArgumentParser) -> None:
    _add_version_argument(parser)
    _add_optional_source_sha_argument(parser)


def _add_rc_tag_argument(parser: argparse.ArgumentParser, help_text: str) -> None:
    parser.add_argument("--rc-tag", dest="rc_tag", help=help_text)


def _add_selected_rc_tag_argument(parser: argparse.ArgumentParser, help_text: str) -> None:
    parser.add_argument("--selected-rc-tag", dest="selected_rc_tag", help=help_text)


def _register_source_selection_commands(
    subparsers: Subparsers,
    common: argparse.ArgumentParser,
) -> None:
    create_release_branch = _add_command_parser(
        subparsers,
        common,
        "create-release-branch",
        help_text="Create or plan a release branch.",
        handler=commands.run_create_release_branch,
    )
    create_release_branch.add_argument(
        "--apply",
        dest="apply_changes",
        action="store_true",
        help="Create the release branch instead of only writing the plan manifest and summary.",
    )
    create_release_branch.add_argument("release_line")
    create_release_branch.add_argument("source_ref", nargs="?", default="main")

    verify_source_ref_checks = _add_command_parser(
        subparsers,
        common,
        "verify-source-ref-checks",
        help_text="Verify GitHub checks on the resolved source ref.",
        handler=commands.run_verify_source_ref_checks,
    )
    _add_version_and_optional_source_sha_arguments(verify_source_ref_checks)

    prepare_rc = _add_command_parser(
        subparsers,
        common,
        "prepare-rc",
        help_text="Resolve shared RC state and emit vote summaries.",
        handler=commands.run_prepare_rc,
    )
    _add_version_and_optional_source_sha_arguments(prepare_rc)

    cleanup_dev_svn_rcs = _add_command_parser(
        subparsers,
        common,
        "cleanup-dev-svn-rcs",
        help_text="Delete pre-existing RC directories for one version from ASF SVN dev dist.",
        handler=commands.run_cleanup_dev_svn_rcs,
    )
    _add_version_argument(cleanup_dev_svn_rcs)

    create_source_artifact = _add_command_parser(
        subparsers,
        common,
        "create-source-artifact",
        help_text="Build a reproducible source artifact from Git.",
        handler=commands.run_create_source_artifact,
    )
    _add_version_and_optional_source_sha_arguments(create_source_artifact)

    build_source_rc = _add_command_parser(
        subparsers,
        common,
        "build-source-rc",
        help_text="Build, sign, and stage a source RC.",
        handler=commands.run_build_source_rc,
    )
    _add_rc_tag_argument(
        build_source_rc,
        "Exact RC tag to use for this run. Required to keep later reruns on the same RC within one workflow.",
    )
    _add_version_and_optional_source_sha_arguments(build_source_rc)


def _register_materialization_commands(
    subparsers: Subparsers,
    common: argparse.ArgumentParser,
) -> None:
    materialize_rc_git_content = _add_command_parser(
        subparsers,
        common,
        "materialize-rc-git-content",
        help_text="Build release-only Git content in a detached worktree and emit one materialized commit.",
        handler=commands.run_materialize_rc_git_content,
    )
    _add_rc_tag_argument(
        materialize_rc_git_content,
        "Exact RC tag whose detached materialization commit is being prepared.",
    )
    materialize_rc_git_content.add_argument(
        "--materialized-path",
        dest="materialized_paths",
        action="append",
        default=[],
        help=(
            "Repository-relative file or directory path to stage with "
            "`git add --force`. Repeat for multiple paths."
        ),
    )
    materialize_rc_git_content.add_argument(
        "--materialized-ref-name",
        dest="materialized_ref_name",
        help=(
            "Optional temporary remote ref name override. When omitted, the "
            "tooling generates one and uses it to anchor the detached "
            "materialization commit between jobs."
        ),
    )
    materialize_rc_git_content.add_argument(
        "--run-command",
        dest="run_command",
        required=True,
        help=(
            "POSIX shell command executed inside the detached worktree before "
            "staging the materialized paths."
        ),
    )
    _add_version_and_optional_source_sha_arguments(materialize_rc_git_content)

    create_rc_materialization_tag = _add_command_parser(
        subparsers,
        common,
        "create-rc-materialization-tag",
        help_text="Create the RC tag on the source commit or on a detached materialization commit.",
        handler=commands.run_create_rc_materialization_tag,
    )
    _add_rc_tag_argument(create_rc_materialization_tag, "Exact RC tag to create or reuse for this run.")
    create_rc_materialization_tag.add_argument(
        "--target-commit",
        dest="target_commit",
        help="Detached materialization commit SHA to tag for components that release generated Git content.",
    )
    create_rc_materialization_tag.add_argument(
        "--cleanup-materialized-ref-name",
        dest="cleanup_materialized_ref_name",
        help="Optional temporary remote ref name to delete after RC tag creation.",
    )
    _add_version_and_optional_source_sha_arguments(create_rc_materialization_tag)

    finalize_rc_vote_materials = _add_command_parser(
        subparsers,
        common,
        "finalize-rc-vote-materials",
        help_text="Build, sign, stage, and mirror the authoritative RC vote-manifest.",
        handler=commands.run_finalize_rc_vote_materials,
    )
    finalize_rc_vote_materials.add_argument(
        "--secondary-artifact-manifest",
        dest="secondary_artifact_manifests",
        action="append",
        default=[],
        help="JSON manifest containing generic secondary_artifacts entries to include in the RC vote-manifest.",
    )
    _add_rc_tag_argument(
        finalize_rc_vote_materials,
        "Exact RC tag whose vote-manifest should be generated.",
    )
    _add_version_and_optional_source_sha_arguments(finalize_rc_vote_materials)


def _register_artifact_registration_commands(
    subparsers: Subparsers,
    common: argparse.ArgumentParser,
) -> None:
    record_artifact = _add_command_parser(
        subparsers,
        common,
        "record-artifact",
        help_text="Write one typed secondary-artifact registration fragment for later RC finalization.",
        handler=commands.run_record_artifact,
    )
    record_artifact.add_argument(
        "--kind",
        required=True,
        choices=registered_artifact_kinds(),
        help="Artifact kind to register, for example generic-file.",
    )
    record_artifact.add_argument(
        "--artifact-id",
        required=True,
        help="Stable artifact identifier used inside the RC vote-manifest.",
    )
    record_artifact.add_argument(
        "--role",
        help="Optional artifact role label such as bootstrap-convenience-archive.",
    )
    record_artifact.add_argument(
        "--output-path",
        dest="output_path",
        help="Exact JSON fragment path to write. Mutually exclusive with --output-dir.",
    )
    record_artifact.add_argument(
        "--output-dir",
        dest="output_dir",
        help="Bundle directory to write. Defaults under build/release-artifacts/<component>/secondary-artifacts/<artifact-id>/.",
    )
    record_artifact.add_argument(
        "--file",
        dest="file",
        help="Optional local artifact file used to derive the filename and compute SHA512.",
    )
    record_artifact.add_argument(
        "--filename",
        dest="filename",
        help="Published artifact filename override when it differs from --file or cannot be derived from other kind-specific metadata.",
    )
    record_artifact.add_argument(
        "--uri",
        help="Published or staged artifact URI recorded in the vote-manifest. Some kinds such as npm-package can derive this when omitted.",
    )
    record_artifact.add_argument(
        "--base-url",
        dest="base_url",
        help="Repository base URL for collection-style kinds such as maven-repository. Defaults to the canonical repository.apache.org staging URL for maven-repository when omitted.",
    )
    record_artifact.add_argument(
        "--staging-repository-id",
        dest="staging_repository_id",
        help="Nexus staging repository ID for the maven-repository kind.",
    )
    record_artifact.add_argument(
        "--inventory-workers",
        dest="inventory_workers",
        type=int,
        help="Worker count for collection-style inventory discovery and fetches. Defaults to 16 for maven-repository.",
    )
    record_artifact.add_argument(
        "--sha512",
        dest="sha512",
        help="Explicit SHA512 digest. When omitted and --file is provided, compute it from the file.",
    )
    record_artifact.add_argument(
        "--sha512-uri",
        dest="sha512_uri",
        help="Optional SHA512 sidecar URI for the published artifact.",
    )
    record_artifact.add_argument(
        "--sha256",
        dest="sha256",
        help="Explicit SHA256 digest. When omitted and --file is provided, compute it from the file.",
    )
    record_artifact.add_argument(
        "--sha256-uri",
        dest="sha256_uri",
        help="Optional SHA256 sidecar or registry checksum URI for the published artifact.",
    )
    record_artifact.add_argument(
        "--integrity",
        dest="integrity",
        help="Subresource Integrity value for kinds such as npm-package, for example sha512-<base64>.",
    )
    record_artifact.add_argument(
        "--index-url",
        dest="index_url",
        help="Python package index URL for the python-distribution kind.",
    )
    record_artifact.add_argument(
        "--registry-url",
        dest="registry_url",
        help="Package registry base URL for the npm-package kind. Used to derive the canonical tarball URI when --uri is omitted.",
    )
    record_artifact.add_argument(
        "--registry",
        dest="registry",
        help="OCI registry host for the oci-image kind.",
    )
    record_artifact.add_argument(
        "--repository",
        dest="repository",
        help="Repository path within an OCI registry for the oci-image kind.",
    )
    record_artifact.add_argument(
        "--digest",
        dest="digest",
        help="Immutable OCI content digest for the oci-image kind, for example sha256:<hex>.",
    )
    record_artifact.add_argument(
        "--image-ref",
        dest="image_ref",
        help="Existing OCI image reference to inspect via docker buildx imagetools for the oci-image kind.",
    )
    record_artifact.add_argument(
        "--platform-digest",
        dest="platform_digests",
        action="append",
        help="Repeatable <platform>=<digest> mapping for multi-platform OCI images.",
    )
    record_artifact.add_argument(
        "--project-name",
        "--package-name",
        dest="project_name",
        help="Published project or package name for typed package-distribution kinds such as python-distribution or npm-package.",
    )
    record_artifact.add_argument(
        "--package-version",
        dest="package_version",
        help="Published package version for typed package-distribution kinds.",
    )
    record_artifact.add_argument(
        "--attestation-repository",
        dest="attestation_repository",
        help="Expected repository identity for ecosystems that publish attestations, such as PyPI.",
    )
    record_artifact.add_argument(
        "--artifact-origin",
        dest="artifact_origin",
        help="Optional artifact-origin label such as source-commit or release-mirror. Defaults to source-commit when --git-commit-sha is provided.",
    )
    record_artifact.add_argument(
        "--git-commit-sha",
        dest="git_commit_sha",
        help="Optional Git commit SHA associated with the artifact origin.",
    )


def _register_publication_commands(
    subparsers: Subparsers,
    common: argparse.ArgumentParser,
) -> None:
    publish_atr_candidate = _add_command_parser(
        subparsers,
        common,
        "publish-atr-candidate",
        help_text="Publish the staged RC source bundle and vote-manifest files to ATR.",
        handler=commands.run_publish_atr_candidate,
    )
    publish_atr_candidate.add_argument(
        "--wait-for-checks",
        action="store_true",
        help="Wait for ATR's initial automated checks and include a summary snapshot.",
    )
    publish_atr_candidate.add_argument(
        "--check-timeout-seconds",
        dest="check_timeout_seconds",
        type=int,
        default=60,
        help="Maximum time to wait for ATR checks when --wait-for-checks is enabled.",
    )
    publish_atr_candidate.add_argument(
        "--check-interval-ms",
        dest="check_interval_ms",
        type=int,
        default=500,
        help="Polling interval in milliseconds when waiting for ATR checks.",
    )
    _add_rc_tag_argument(
        publish_atr_candidate,
        "Exact RC tag whose staged candidate should be mirrored into ATR.",
    )
    _add_version_and_optional_source_sha_arguments(publish_atr_candidate)

    report_atr_checks = _add_command_parser(
        subparsers,
        common,
        "report-atr-checks",
        help_text="Fetch and summarize ATR checks for one candidate release.",
        handler=commands.run_report_atr_checks,
    )
    report_atr_checks.add_argument(
        "--revision",
        dest="revision",
        help="Exact ATR revision number to inspect. Defaults to the latest ATR revision.",
    )
    report_atr_checks.add_argument(
        "--verbose-atr-output",
        action="store_true",
        help="Include ATR's verbose failure and warning details in the reported status snapshot.",
    )
    _add_rc_tag_argument(
        report_atr_checks,
        "Exact RC tag whose ATR candidate status should be reported.",
    )
    _add_version_and_optional_source_sha_arguments(report_atr_checks)

    publish_source_release_svn = _add_command_parser(
        subparsers,
        common,
        "publish-source-release-svn",
        help_text="Promote the latest RC source directory from ASF dev dist into release dist.",
        handler=commands.run_publish_source_release_svn,
    )
    _add_selected_rc_tag_argument(
        publish_source_release_svn,
        "Exact RC tag that this release-version workflow run is allowed to publish.",
    )
    _add_version_argument(publish_source_release_svn)

    prune_older_line_releases = _add_command_parser(
        subparsers,
        common,
        "prune-older-line-releases",
        help_text="Delete older same-line releases from ASF release dist.",
        handler=commands.run_prune_older_line_releases,
    )
    _add_version_argument(prune_older_line_releases)

    create_final_tag = _add_command_parser(
        subparsers,
        common,
        "create-final-tag",
        help_text="Create the immutable exact final Git tag for a version.",
        handler=commands.run_create_final_tag,
    )
    _add_selected_rc_tag_argument(
        create_final_tag,
        "Exact RC tag that this release-version workflow run is allowed to finalize.",
    )
    _add_version_argument(create_final_tag)

    finalize_draft_github_release = _add_command_parser(
        subparsers,
        common,
        "finalize-draft-github-release",
        help_text="Publish the existing draft GitHub Release for a final version.",
        handler=commands.run_finalize_draft_github_release,
    )
    _add_selected_rc_tag_argument(
        finalize_draft_github_release,
        "Exact RC tag that this release-version workflow run is allowed to publish.",
    )
    _add_version_argument(finalize_draft_github_release)

    sync_draft_github_release = _add_command_parser(
        subparsers,
        common,
        "sync-draft-github-release",
        help_text="Create or recreate the draft GitHub Release placeholder for one version.",
        handler=commands.run_sync_draft_github_release,
    )
    _add_rc_tag_argument(
        sync_draft_github_release,
        "Exact RC tag to record in the draft GitHub Release for this run.",
    )
    _add_version_and_optional_source_sha_arguments(sync_draft_github_release)


def _register_release_metadata_commands(
    subparsers: Subparsers,
    common: argparse.ArgumentParser,
) -> None:
    update_moving_tags = _add_command_parser(
        subparsers,
        common,
        "update-moving-tags",
        help_text="Move Git tag-backed moving aliases such as GitHub Action major/minor tags.",
        handler=commands.run_update_moving_tags,
    )
    _add_version_argument(update_moving_tags)

    update_moving_image_aliases = _add_command_parser(
        subparsers,
        common,
        "update-moving-image-aliases",
        help_text="Resolve the moving container-image aliases for a version.",
        handler=commands.run_update_moving_image_aliases,
    )
    _add_version_argument(update_moving_image_aliases)

    publish_dockerhub_moving_tags = _add_command_parser(
        subparsers,
        common,
        "publish-dockerhub-moving-tags",
        help_text="Publish Docker Hub moving aliases that point at an already-pushed exact image.",
        handler=commands.run_publish_dockerhub_moving_tags,
    )
    _add_version_argument(publish_dockerhub_moving_tags)
    publish_dockerhub_moving_tags.add_argument("source_image")

    attach_github_release_assets = _add_command_parser(
        subparsers,
        common,
        "attach-github-release-assets",
        help_text="Attach convenience assets and optional sidecars to a GitHub Release.",
        handler=commands.run_attach_github_release_assets,
    )
    attach_github_release_assets.add_argument(
        "--sign",
        action="store_true",
        help="Generate and attach detached ASCII-armored signatures for each asset.",
    )
    attach_github_release_assets.add_argument(
        "--checksum",
        dest="checksum_algorithms",
        action="append",
        choices=("sha256", "sha512"),
        default=[],
        help="Generate and attach checksum sidecars for each asset.",
    )
    _add_version_argument(attach_github_release_assets)
    attach_github_release_assets.add_argument("assets", nargs="+")

    release_version = _add_command_parser(
        subparsers,
        common,
        "release-version",
        help_text="Resolve final release state and alias plans.",
        handler=commands.run_release_version,
    )
    _add_version_argument(release_version)


def _register_verification_commands(subparsers: Subparsers) -> None:
    verify_rc = subparsers.add_parser(
        "verify-rc",
        help="Verify one signed RC vote manifest plus its staged source artifact.",
    )
    verify_rc.set_defaults(handler=commands.run_verify_rc)
    verify_rc.add_argument(
        "--component-config",
        dest="component_config",
        help="Optional YAML component configuration path used to cross-check the explicit KEYS URL.",
    )
    verify_rc.add_argument(
        "--allow-non-production-release-targets",
        action="store_true",
        help="Allow file:// and http:// manifest, KEYS, source-artifact, and source-repository URLs for local harness-style test runs.",
    )
    verify_rc.add_argument(
        "--progress",
        choices=("auto", "on", "off"),
        default="auto",
        help="Progress reporting mode for long-running verification steps. Defaults to auto, which reports progress on interactive terminals only.",
    )
    verify_rc.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help=(
            "Color mode for the human stderr transcript. Defaults to auto, which only colors interactive terminals "
            "and respects NO_COLOR, CLICOLOR=0, CLICOLOR_FORCE=1, and TERM=dumb."
        ),
    )
    verify_rc.add_argument(
        "--work-dir",
        dest="work_dir",
        help="Optional working directory for downloads, cloned source state, and generated reports.",
    )
    verify_rc.add_argument(
        "--report-json",
        dest="report_json",
        help="Optional machine-readable verification report path.",
    )
    verify_rc.add_argument(
        "--report-md",
        dest="report_md",
        help="Optional Markdown verification report path.",
    )
    verify_rc.add_argument(
        "--log-path",
        dest="log_path",
        help="Optional combined transcript and low-level command log path.",
    )
    verify_rc.add_argument(
        "--verbose",
        action="store_true",
        help="Also emit low-level command traces and captured subprocess output to stderr while still writing them to the log file.",
    )
    verify_rc.add_argument("rc_vote_manifest_url")
    verify_rc.add_argument("keys_url")


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argparse parser for the tool."""

    parser = argparse.ArgumentParser(prog="buildish-release-tooling")
    common = _common_parser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    _register_source_selection_commands(subparsers, common)
    _register_materialization_commands(subparsers, common)
    _register_artifact_registration_commands(subparsers, common)
    _register_publication_commands(subparsers, common)
    _register_release_metadata_commands(subparsers, common)
    _register_verification_commands(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, dispatch the selected command, and report failures."""

    parser = build_parser()
    args = parser.parse_args(argv)
    handler: CommandHandler = args.handler
    try:
        result = handler(args)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"{exc}\n")
        return 1
    if result is not None:
        sys.stdout.write(f"{result}\n")
    return 0
