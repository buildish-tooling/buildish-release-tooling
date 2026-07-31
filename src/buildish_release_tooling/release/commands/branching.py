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

"""Branch creation and source-ref verification commands."""

from __future__ import annotations

import re
from argparse import Namespace
from pathlib import Path

from buildish_release_tooling.release.config import (
    require_github_authoritative_publication,
)
from buildish_release_tooling.release.direct_release import selected_source_ref
from buildish_release_tooling.release.git_repo import GitRepository
from buildish_release_tooling.release.platforms.github.checks import (
    assert_ref_ready,
    fetch_check_runs_json,
    fetch_statuses_json,
    resolve_repository_slug,
)
from buildish_release_tooling.release.manifest import write_manifest
from buildish_release_tooling.release.command_manifests import (
    CreateReleaseBranchManifest,
)
from buildish_release_tooling.release.summary import SummaryWriter

from buildish_release_tooling.release.commands._shared import (
    _context,
    _manifest_path,
    _summary_code,
)


def run_create_release_branch(args: Namespace) -> Path:
    """Run the `create-release-branch` command."""

    context = _context(args)
    release_line = args.release_line
    source_ref = args.source_ref
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?\.x", release_line):
        raise ValueError("release_line must look like 1.x or 1.2.x")
    repo = GitRepository.from_current_worktree()
    manifest_path = _manifest_path(
        context.release_config.component.id, "create-release-branch"
    )
    summary = SummaryWriter.from_environment()
    write_manifest(
        manifest_path,
        CreateReleaseBranchManifest(
            component=context.release_config.component.id,
            release_line=release_line,
            release_branch=f"release/{release_line}",
            source_ref=source_ref,
        ),
    )
    summary.append_heading("Create release branch")
    summary.append_plaintext_block(
        "Planned branch creation", f"release/{release_line} <- {source_ref}"
    )
    summary.append_plaintext_block("Git repository", str(repo.path))
    if args.apply_changes:
        repo.create_branch(f"release/{release_line}", source_ref)
        summary.append_plaintext_block(
            "Applied Git branch creation",
            f"Created release/{release_line} from {source_ref}",
        )
    return manifest_path


def run_verify_source_ref_checks(args: Namespace) -> None:
    """Run the hard GitHub-check gate for one exact selected source revision."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version = args.version
    requested_source_ref = args.source_sha
    source_ref = selected_source_ref(
        repo,
        context.release_config,
        version,
        requested_source_ref,
    )
    source_commit = repo.resolve_commit(source_ref)
    target = require_github_authoritative_publication(context.release_config)
    repository_slug = target.repository or resolve_repository_slug(repo.path)
    source_checks = context.release_config.source.checks
    required_checks = source_checks.required if source_checks is not None else []
    check_runs_payload = fetch_check_runs_json(repository_slug, source_commit)
    statuses_payload = fetch_statuses_json(repository_slug, source_commit)
    total_checks = assert_ref_ready(
        check_runs_payload,
        statuses_payload,
        required_checks,
    )
    summary = SummaryWriter.from_environment()
    summary.append_heading(f"Verify GitHub checks for source ref {version}")
    summary.append_key_value_table(
        "Technical details",
        [
            ("Component", _summary_code(context.release_config.component.id)),
            ("Version", _summary_code(version)),
            ("Repository", _summary_code(repository_slug)),
            (
                "Requested source ref",
                _summary_code(requested_source_ref or "<configured>"),
            ),
            ("Resolved source ref", _summary_code(source_ref)),
            ("Resolved source commit", _summary_code(source_commit)),
            ("Required GitHub checks observed", str(total_checks)),
        ],
    )
    summary.append_key_value_table(
        "Gate policy",
        [
            ("Source-check platform", _summary_code("github")),
            (
                "Required GitHub checks",
                _summary_code(", ".join(required_checks) or "<none>"),
            ),
        ],
    )
    summary.append_plaintext_block(
        "Outcome",
        "All configured GitHub checks on the resolved source commit are successful or skipped. "
        f"The release gate accepted {total_checks} named checks for {source_commit}.",
    )
