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

"""Direct GitHub final-release command handlers."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Literal

from buildish_release_tooling.release.commands._shared import _context, _manifest_path
from buildish_release_tooling.release.config import require_github_authoritative_publication
from buildish_release_tooling.release.core.state import DirectReleaseState
from buildish_release_tooling.release.direct_release import resolve_direct_release_state
from buildish_release_tooling.release.git_repo import GitRepository
from buildish_release_tooling.release.manifest import write_manifest
from buildish_release_tooling.release.platforms.github.checks import resolve_repository_slug
from buildish_release_tooling.release.platforms.github.direct import (
    direct_release_name,
    missing_final_release_assets,
    observe_final_release,
    validate_final_release,
    validate_final_tag,
    validate_local_release_assets,
)
from buildish_release_tooling.release.platforms.github.manifests import (
    PublishGitHubFinalReleaseResult,
    ReadGitHubFinalReleaseResult,
    StageGitHubFinalReleaseResult,
    VerifyGitHubFinalReleaseResult,
)
from buildish_release_tooling.release.platforms.github.refs import (
    resolve_annotated_tag_target_commit,
)
from buildish_release_tooling.release.platforms.github.releases import (
    create_draft_release,
    list_releases,
    release_by_tag,
    release_by_tag_or_none,
    update_release,
    upload_release_assets,
)
from buildish_release_tooling.release.platforms.github.text import (
    render_direct_final_release_body,
)
from buildish_release_tooling.release.summary import SummaryWriter
from buildish_release_tooling.shared.parsing import (
    DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    read_pydantic_json_file_bounded,
)


def _load_direct_state(path_text: str) -> DirectReleaseState:
    return read_pydantic_json_file_bounded(
        DirectReleaseState,
        Path(path_text),
        max_bytes=DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    )


def _validated_inputs(
    args: Namespace,
) -> tuple[DirectReleaseState, GitRepository, str, str]:
    context = _context(args)
    if context.release_config.lifecycle.mode != "direct":
        raise ValueError("direct GitHub final-release commands require lifecycle.mode direct")
    state = _load_direct_state(args.release_state)
    if state.release.component.id != context.release_config.component.id:
        raise ValueError("direct-release state component does not match release configuration")
    if state.final_tag.name != context.release_config.versioning.final_tag_template.format(
        version=state.release.version
    ):
        raise ValueError("direct-release state final tag does not match release configuration")
    target = require_github_authoritative_publication(context.release_config)
    repo = GitRepository.from_current_worktree()
    repository = target.repository or resolve_repository_slug(repo.path)
    tag_target = (
        repo.resolve_commit(state.final_tag.name)
        if repo.tag_exists(state.final_tag.name)
        else None
    )
    validate_final_tag(state, tag_target)
    validate_final_tag(
        state,
        resolve_annotated_tag_target_commit(
            repository,
            tag_name=state.final_tag.name,
        ),
    )
    return state, repo, repository, render_direct_final_release_body(state)


def _release_payload(repository: str, tag_name: str) -> dict[str, object]:
    return release_by_tag(list_releases(repository), tag_name=tag_name)


def _append_result_summary(
    heading: str,
    *,
    outcome: str,
    state: DirectReleaseState,
    repository: str,
    release_url: str,
) -> None:
    summary = SummaryWriter.from_environment()
    summary.append_heading(heading)
    summary.append_plaintext_block("Outcome", outcome)
    summary.append_plaintext_block("GitHub repository", repository)
    summary.append_plaintext_block("Final tag", state.final_tag.name)
    summary.append_plaintext_block("Source commit", state.source.commit_sha)
    summary.append_plaintext_block("GitHub Release", release_url)


def run_resolve_direct_release(args: Namespace) -> Path:
    """Resolve and emit exact provider-neutral state for one direct release."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    state = resolve_direct_release_state(
        repo,
        context.release_config,
        args.version,
        args.source_ref,
    )
    result_path = _manifest_path(state.release.component.id, "resolve-direct-release")
    write_manifest(result_path, state, exclude_none=True)
    summary = SummaryWriter.from_environment()
    summary.append_heading("Resolve direct release")
    summary.append_plaintext_block("Version", state.release.version)
    summary.append_plaintext_block("Source ref", state.source.source_ref or "<none>")
    summary.append_plaintext_block("Source commit", state.source.commit_sha)
    summary.append_plaintext_block("Final tag", state.final_tag.name)
    return result_path


def run_read_github_final_release(args: Namespace) -> Path:
    """Read one exact-tag GitHub final release without applying desired-state policy."""

    state, _repo, repository, _expected_body = _validated_inputs(args)
    publication = observe_final_release(
        state,
        repository,
        _release_payload(repository, state.final_tag.name),
    )
    result = ReadGitHubFinalReleaseResult(
        component=state.release.component.id,
        version=state.release.version,
        source_commit=state.source.commit_sha,
        publication=publication,
    )
    result_path = _manifest_path(state.release.component.id, result.action)
    write_manifest(result_path, result)
    _append_result_summary(
        "Read GitHub final release",
        outcome=result.outcome,
        state=state,
        repository=repository,
        release_url=publication.release_url,
    )
    return result_path


def run_stage_github_final_release(args: Namespace) -> Path:
    """Create or complete an exact draft GitHub final release without overwrites."""

    state, _repo, repository, expected_body = _validated_inputs(args)
    local_assets = validate_local_release_assets(
        state,
        [Path(path) for path in args.assets],
    )
    existing = release_by_tag_or_none(
        list_releases(repository),
        tag_name=state.final_tag.name,
    )
    created = existing is None
    if existing is None:
        release_payload = create_draft_release(
            repository,
            tag_name=state.final_tag.name,
            target_commitish=state.source.commit_sha,
            release_name=direct_release_name(state),
            release_body=expected_body,
        )
    else:
        release_payload = existing
    missing_names = missing_final_release_assets(
        state,
        release_payload,
        expected_body=expected_body,
    )
    if missing_names:
        if release_payload.get("draft") is not True:
            raise ValueError("published GitHub final release is missing expected assets")
        paths_by_name = {path.name: path for path in local_assets}
        upload_release_assets(
            repository,
            tag_name=state.final_tag.name,
            asset_paths=[paths_by_name[name] for name in missing_names],
            clobber=False,
        )
        release_payload = _release_payload(repository, state.final_tag.name)
    publication = validate_final_release(
        state,
        repository,
        release_payload,
        expected_body=expected_body,
    )
    outcome: Literal["created", "completed", "already-complete"] = (
        "created" if created else ("completed" if missing_names else "already-complete")
    )
    result = StageGitHubFinalReleaseResult(
        component=state.release.component.id,
        version=state.release.version,
        source_commit=state.source.commit_sha,
        publication=publication,
        outcome=outcome,
    )
    result_path = _manifest_path(state.release.component.id, result.action)
    write_manifest(result_path, result)
    _append_result_summary(
        "Stage GitHub final release",
        outcome=result.outcome,
        state=state,
        repository=repository,
        release_url=publication.release_url,
    )
    return result_path


def run_verify_github_final_release(args: Namespace) -> Path:
    """Verify exact GitHub metadata and assets for one direct final release."""

    state, _repo, repository, expected_body = _validated_inputs(args)
    publication = validate_final_release(
        state,
        repository,
        _release_payload(repository, state.final_tag.name),
        expected_body=expected_body,
    )
    result = VerifyGitHubFinalReleaseResult(
        component=state.release.component.id,
        version=state.release.version,
        source_commit=state.source.commit_sha,
        publication=publication,
    )
    result_path = _manifest_path(state.release.component.id, result.action)
    write_manifest(result_path, result)
    _append_result_summary(
        "Verify GitHub final release",
        outcome=result.outcome,
        state=state,
        repository=repository,
        release_url=publication.release_url,
    )
    return result_path


def run_publish_github_final_release(args: Namespace) -> Path:
    """Publish an exact verified GitHub final release or validate an identical rerun."""

    state, _repo, repository, expected_body = _validated_inputs(args)
    release_payload = _release_payload(repository, state.final_tag.name)
    publication = validate_final_release(
        state,
        repository,
        release_payload,
        expected_body=expected_body,
    )
    if publication.draft:
        update_release(
            repository,
            publication.release_id,
            payload={
                "tag_name": state.final_tag.name,
                "target_commitish": state.source.commit_sha,
                "name": direct_release_name(state),
                "body": expected_body,
                "draft": False,
                "prerelease": False,
            },
        )
        publication = validate_final_release(
            state,
            repository,
            _release_payload(repository, state.final_tag.name),
            expected_body=expected_body,
        )
        if publication.draft:
            raise ValueError("GitHub final release remained a draft after publication")
        outcome: Literal["published", "already-complete"] = "published"
    else:
        outcome = "already-complete"
    result = PublishGitHubFinalReleaseResult(
        component=state.release.component.id,
        version=state.release.version,
        source_commit=state.source.commit_sha,
        publication=publication,
        outcome=outcome,
    )
    result_path = _manifest_path(state.release.component.id, result.action)
    write_manifest(result_path, result)
    _append_result_summary(
        "Publish GitHub final release",
        outcome=result.outcome,
        state=state,
        repository=repository,
        release_url=publication.release_url,
    )
    return result_path
