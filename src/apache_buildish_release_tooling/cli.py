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

from apache_buildish_release_tooling import commands

CommandHandler = Callable[[argparse.Namespace], Path | None]


def _common_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--component-config",
        dest="component_config",
        required=True,
        help="YAML component configuration path.",
    )
    return parser


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argparse parser for the tool."""

    parser = argparse.ArgumentParser(prog="buildish-release-tooling")
    common = _common_parser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_release_branch = subparsers.add_parser(
        "create-release-branch", parents=[common], help="Create or plan a release branch."
    )
    create_release_branch.add_argument(
        "--apply",
        dest="apply_changes",
        action="store_true",
        help="Create the release branch instead of only writing the plan manifest and summary.",
    )
    create_release_branch.add_argument("release_line")
    create_release_branch.add_argument("source_ref", nargs="?", default="main")
    create_release_branch.set_defaults(handler=commands.run_create_release_branch)

    verify_source_ref_checks = subparsers.add_parser(
        "verify-source-ref-checks",
        parents=[common],
        help="Verify GitHub checks on the resolved source ref.",
    )
    verify_source_ref_checks.add_argument("version")
    verify_source_ref_checks.add_argument("source_sha", nargs="?")
    verify_source_ref_checks.set_defaults(handler=commands.run_verify_source_ref_checks)

    prepare_rc = subparsers.add_parser(
        "prepare-rc", parents=[common], help="Resolve shared RC state and emit vote summaries."
    )
    prepare_rc.add_argument("version")
    prepare_rc.add_argument("source_sha", nargs="?")
    prepare_rc.set_defaults(handler=commands.run_prepare_rc)

    cleanup_dev_svn_rcs = subparsers.add_parser(
        "cleanup-dev-svn-rcs",
        parents=[common],
        help="Delete pre-existing RC directories for one version from ASF SVN dev dist.",
    )
    cleanup_dev_svn_rcs.add_argument("version")
    cleanup_dev_svn_rcs.set_defaults(handler=commands.run_cleanup_dev_svn_rcs)

    create_source_artifact = subparsers.add_parser(
        "create-source-artifact",
        parents=[common],
        help="Build a reproducible source artifact from Git.",
    )
    create_source_artifact.add_argument("version")
    create_source_artifact.add_argument("source_sha", nargs="?")
    create_source_artifact.set_defaults(handler=commands.run_create_source_artifact)

    build_source_rc = subparsers.add_parser(
        "build-source-rc",
        parents=[common],
        help="Build, sign, and stage a source RC.",
    )
    build_source_rc.add_argument(
        "--rc-tag",
        dest="rc_tag",
        help="Exact RC tag to use for this run. Required to keep later reruns on the same RC within one workflow.",
    )
    build_source_rc.add_argument("version")
    build_source_rc.add_argument("source_sha", nargs="?")
    build_source_rc.set_defaults(handler=commands.run_build_source_rc)

    materialize_rc_git_content = subparsers.add_parser(
        "materialize-rc-git-content",
        parents=[common],
        help=(
            "Build release-only Git content in a detached worktree and emit one "
            "materialized commit."
        ),
    )
    materialize_rc_git_content.add_argument(
        "--rc-tag",
        dest="rc_tag",
        help="Exact RC tag whose detached materialization commit is being prepared.",
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
    materialize_rc_git_content.add_argument("version")
    materialize_rc_git_content.add_argument("source_sha", nargs="?")
    materialize_rc_git_content.set_defaults(handler=commands.run_materialize_rc_git_content)

    create_rc_materialization_tag = subparsers.add_parser(
        "create-rc-materialization-tag",
        parents=[common],
        help="Create the RC tag on the source commit or on a detached materialization commit.",
    )
    create_rc_materialization_tag.add_argument(
        "--rc-tag",
        dest="rc_tag",
        help="Exact RC tag to create or reuse for this run.",
    )
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
    create_rc_materialization_tag.add_argument("version")
    create_rc_materialization_tag.add_argument("source_sha", nargs="?")
    create_rc_materialization_tag.set_defaults(handler=commands.run_create_rc_materialization_tag)

    publish_source_release_svn = subparsers.add_parser(
        "publish-source-release-svn",
        parents=[common],
        help="Promote the latest RC source directory from ASF dev dist into release dist.",
    )
    publish_source_release_svn.add_argument(
        "--selected-rc-tag",
        dest="selected_rc_tag",
        help="Exact RC tag that this release-version workflow run is allowed to publish.",
    )
    publish_source_release_svn.add_argument("version")
    publish_source_release_svn.set_defaults(handler=commands.run_publish_source_release_svn)

    prune_older_line_releases = subparsers.add_parser(
        "prune-older-line-releases",
        parents=[common],
        help="Delete older same-line releases from ASF release dist.",
    )
    prune_older_line_releases.add_argument("version")
    prune_older_line_releases.set_defaults(handler=commands.run_prune_older_line_releases)

    create_final_tag = subparsers.add_parser(
        "create-final-tag",
        parents=[common],
        help="Create the immutable exact final Git tag for a version.",
    )
    create_final_tag.add_argument(
        "--selected-rc-tag",
        dest="selected_rc_tag",
        help="Exact RC tag that this release-version workflow run is allowed to finalize.",
    )
    create_final_tag.add_argument("version")
    create_final_tag.set_defaults(handler=commands.run_create_final_tag)

    update_moving_tags = subparsers.add_parser(
        "update-moving-tags",
        parents=[common],
        help="Move Git tag-backed moving aliases such as GitHub Action major/minor tags.",
    )
    update_moving_tags.add_argument("version")
    update_moving_tags.set_defaults(handler=commands.run_update_moving_tags)

    update_moving_image_aliases = subparsers.add_parser(
        "update-moving-image-aliases",
        parents=[common],
        help="Resolve the moving container-image aliases for a version.",
    )
    update_moving_image_aliases.add_argument("version")
    update_moving_image_aliases.set_defaults(handler=commands.run_update_moving_image_aliases)

    publish_dockerhub_moving_tags = subparsers.add_parser(
        "publish-dockerhub-moving-tags",
        parents=[common],
        help="Publish Docker Hub moving aliases that point at an already-pushed exact image.",
    )
    publish_dockerhub_moving_tags.add_argument("version")
    publish_dockerhub_moving_tags.add_argument("source_image")
    publish_dockerhub_moving_tags.set_defaults(handler=commands.run_publish_dockerhub_moving_tags)

    attach_github_release_assets = subparsers.add_parser(
        "attach-github-release-assets",
        parents=[common],
        help="Attach convenience assets and optional sidecars to a GitHub Release.",
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
    attach_github_release_assets.add_argument("version")
    attach_github_release_assets.add_argument("assets", nargs="+")
    attach_github_release_assets.set_defaults(handler=commands.run_attach_github_release_assets)

    finalize_draft_github_release = subparsers.add_parser(
        "finalize-draft-github-release",
        parents=[common],
        help="Publish the existing draft GitHub Release for a final version.",
    )
    finalize_draft_github_release.add_argument(
        "--selected-rc-tag",
        dest="selected_rc_tag",
        help="Exact RC tag that this release-version workflow run is allowed to publish.",
    )
    finalize_draft_github_release.add_argument("version")
    finalize_draft_github_release.set_defaults(handler=commands.run_finalize_draft_github_release)

    sync_draft_github_release = subparsers.add_parser(
        "sync-draft-github-release",
        parents=[common],
        help="Create or recreate the draft GitHub Release placeholder for one version.",
    )
    sync_draft_github_release.add_argument(
        "--rc-tag",
        dest="rc_tag",
        help="Exact RC tag to record in the draft GitHub Release for this run.",
    )
    sync_draft_github_release.add_argument("version")
    sync_draft_github_release.add_argument("source_sha", nargs="?")
    sync_draft_github_release.set_defaults(handler=commands.run_sync_draft_github_release)

    finalize_rc_vote_materials = subparsers.add_parser(
        "finalize-rc-vote-materials",
        parents=[common],
        help="Build, sign, stage, and mirror the authoritative RC vote-manifest.",
    )
    finalize_rc_vote_materials.add_argument(
        "--secondary-artifact-manifest",
        dest="secondary_artifact_manifests",
        action="append",
        default=[],
        help="JSON manifest containing generic secondary_artifacts entries to include in the RC vote-manifest.",
    )
    finalize_rc_vote_materials.add_argument(
        "--rc-tag",
        dest="rc_tag",
        help="Exact RC tag whose vote-manifest should be generated.",
    )
    finalize_rc_vote_materials.add_argument("version")
    finalize_rc_vote_materials.add_argument("source_sha", nargs="?")
    finalize_rc_vote_materials.set_defaults(handler=commands.run_finalize_rc_vote_materials)

    release_version = subparsers.add_parser(
        "release-version",
        parents=[common],
        help="Resolve final release state and alias plans.",
    )
    release_version.add_argument("version")
    release_version.set_defaults(handler=commands.run_release_version)

    verify_rc = subparsers.add_parser(
        "verify-rc", parents=[common], help="Emit authoritative RC verification instructions."
    )
    verify_rc.add_argument("version")
    verify_rc.set_defaults(handler=commands.run_verify_rc)

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
