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

"""Branch creation and source-ref verification commands."""

from __future__ import annotations

import re
from argparse import Namespace
from pathlib import Path

from apache_buildish_release_tooling.git_repo import GitRepository
from apache_buildish_release_tooling.github_checks import (
    assert_ref_ready,
    fetch_check_runs_json,
    fetch_statuses_json,
    resolve_repository_slug,
)
from apache_buildish_release_tooling.manifest import write_manifest
from apache_buildish_release_tooling.prepare_rc_state import resolve_prepare_rc_state
from apache_buildish_release_tooling.summary import SummaryWriter

from apache_buildish_release_tooling.commands._shared import (
    _context,
    _manifest_path,
    _summary_code,
    _summary_optional_code,
)


def run_create_release_branch(args: Namespace) -> Path:
    """Run the `create-release-branch` command."""

    context = _context(args)
    release_line = args.release_line
    source_ref = args.source_ref
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?\.x", release_line):
        raise ValueError("release_line must look like 1.x or 1.2.x")
    repo = GitRepository.from_current_worktree()
    manifest_path = _manifest_path(context.component_config.component_id, "create-release-branch")
    summary = SummaryWriter.from_environment()
    write_manifest(
        manifest_path,
        {
            "component": context.component_config.component_id,
            "action": "create-release-branch",
            "release_line": release_line,
            "release_branch": f"release/{release_line}",
            "source_ref": source_ref,
        },
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
    """Run the hard GitHub-check gate for `Prepare RC`."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version = args.version
    source_sha = args.source_sha
    state = resolve_prepare_rc_state(repo, context.component_config, version, source_sha)
    repository_slug = resolve_repository_slug(repo.path)
    check_runs_payload = fetch_check_runs_json(repository_slug, state.resolved_source_ref)
    statuses_payload = fetch_statuses_json(repository_slug, state.resolved_source_ref)
    total_checks = assert_ref_ready(
        check_runs_payload,
        statuses_payload,
        context.component_config.release_branch_ci_required,
    )
    summary = SummaryWriter.from_environment()
    summary.append_heading(f"Verify GitHub checks for source ref {version}")
    summary.append_key_value_table(
        "Technical details",
        [
            ("Component", _summary_code(context.component_config.component_id)),
            ("Version", _summary_code(version)),
            ("Repository", _summary_code(repository_slug)),
            ("Resolved release branch", _summary_code(state.resolved_release_branch)),
            ("Resolved source commit", _summary_code(state.resolved_source_ref)),
            ("Requested source SHA", _summary_optional_code(source_sha)),
            ("RC tag", _summary_code(state.rc_tag)),
            ("Final tag", _summary_code(state.final_tag)),
            ("GitHub checks found", str(total_checks)),
        ],
    )
    summary.append_key_value_table(
        "Gate policy",
        [
            (
                "Prepare RC runs component tests",
                str(context.component_config.prepare_rc_runs_tests).lower(),
            ),
            (
                "Release-branch CI required",
                str(context.component_config.release_branch_ci_required).lower(),
            ),
        ],
    )
    summary.append_plaintext_block(
        "Outcome",
        "All GitHub checks on the resolved source commit are successful or skipped. "
        f"The release gate accepted {total_checks} check entries for {state.resolved_source_ref}.",
    )
