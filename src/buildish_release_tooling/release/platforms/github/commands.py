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
from buildish_release_tooling.release.config import (
    require_github_authoritative_publication,
)
from buildish_release_tooling.release.core.manifests import ManifestDigestReference
from buildish_release_tooling.release.core.state import (
    DirectReleaseState,
    PromotionState,
)
from buildish_release_tooling.release.direct_release import resolve_direct_release_state
from buildish_release_tooling.release.git_repo import GitRepository
from buildish_release_tooling.release.manifest import write_manifest
from buildish_release_tooling.release.manifests import ReleaseManifestV1
from buildish_release_tooling.release.platforms.github.checks import (
    resolve_repository_slug,
)
from buildish_release_tooling.release.platforms.github.direct import (
    direct_release_name,
    FINAL_RELEASE_MANIFEST_ASSET_NAME,
    FinalReleaseState,
    missing_final_release_assets,
    observe_final_release,
    observed_release_assets,
    validate_final_release,
    validate_final_tag,
    validate_local_release_assets,
)
from buildish_release_tooling.release.platforms.github.manifests import (
    AttachGitHubReleaseManifestResult,
    GitHubFinalPublication,
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
from buildish_release_tooling.release.source_artifact import checksum
from buildish_release_tooling.shared.parsing import (
    DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    read_json_object_file_bounded,
    read_pydantic_json_file_bounded,
)


def _load_final_release_state(path_text: str) -> FinalReleaseState:
    path = Path(path_text)
    payload = read_json_object_file_bounded(
        path,
        max_bytes=DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    )
    if "candidate_manifest_digest" in payload:
        return PromotionState.model_validate(payload)
    return DirectReleaseState.model_validate(payload)


def _validated_inputs(
    args: Namespace,
) -> tuple[FinalReleaseState, GitRepository, str, str]:
    context = _context(args)
    state = _load_final_release_state(args.release_state)
    expected_lifecycle = "candidate" if isinstance(state, PromotionState) else "direct"
    if context.release_config.lifecycle.mode != expected_lifecycle:
        raise ValueError(
            "final-release state lifecycle does not match release configuration"
        )
    if state.release.component.id != context.release_config.component.id:
        raise ValueError(
            "direct-release state component does not match release configuration"
        )
    if (
        state.final_tag.name
        != context.release_config.versioning.final_tag_template.format(
            version=state.release.version
        )
    ):
        raise ValueError(
            "direct-release state final tag does not match release configuration"
        )
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
    state: FinalReleaseState,
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
        allow_attached_manifest=True,
    )
    if missing_names:
        if release_payload.get("draft") is not True:
            raise ValueError(
                "published GitHub final release is missing expected assets"
            )
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
        allow_attached_manifest=True,
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
        allow_attached_manifest=True,
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
        allow_attached_manifest=True,
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
            allow_attached_manifest=True,
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


def _validate_release_manifest(
    manifest: ReleaseManifestV1,
    state: FinalReleaseState,
    publication: GitHubFinalPublication,
) -> None:
    if (
        manifest.release != state.release
        or manifest.source != state.source
        or manifest.final_tag != state.final_tag
        or manifest.artifacts != state.artifacts
        or manifest.verification_results != state.verification_results
    ):
        raise ValueError("release manifest identity does not match final-release state")
    if isinstance(state, DirectReleaseState):
        if manifest.promoted_candidate is not None or manifest.promotion_evidence:
            raise ValueError(
                "direct release manifest must not contain candidate promotion data"
            )
    else:
        promoted = manifest.promoted_candidate
        if (
            promoted is None
            or promoted.candidate != state.candidate
            or promoted.manifest.digest != state.candidate_manifest_digest
        ):
            raise ValueError(
                "release manifest promoted candidate does not match promotion state"
            )
    extensions = [
        extension
        for extension in manifest.extensions
        if isinstance(extension, GitHubFinalPublication)
    ]
    if len(extensions) != 1 or extensions[0] != publication:
        raise ValueError(
            "release manifest GitHub publication does not match observed release"
        )
    references = [
        reference
        for reference in manifest.publications
        if reference.target_kind == "github-release-final"
    ]
    if len(references) != 1:
        raise ValueError(
            "release manifest requires one GitHub final publication reference"
        )
    reference = references[0]
    if reference.uri != publication.release_url or reference.immutable_id != str(
        publication.release_id
    ):
        raise ValueError(
            "release manifest publication reference does not match observed release"
        )


def run_attach_github_release_manifest(args: Namespace) -> Path:
    """Attach and revalidate one exact final release manifest without clobbering."""

    state, _repo, repository, expected_body = _validated_inputs(args)
    manifest_path = Path(args.release_manifest)
    if manifest_path.name != FINAL_RELEASE_MANIFEST_ASSET_NAME:
        raise ValueError(
            f"release manifest must be named {FINAL_RELEASE_MANIFEST_ASSET_NAME}"
        )
    manifest = read_pydantic_json_file_bounded(
        ReleaseManifestV1,
        manifest_path,
        max_bytes=DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    )
    release_payload = _release_payload(repository, state.final_tag.name)
    publication = validate_final_release(
        state,
        repository,
        release_payload,
        expected_body=expected_body,
        allow_attached_manifest=True,
    )
    if publication.draft:
        raise ValueError(
            "GitHub final release must be published before attaching its manifest"
        )
    _validate_release_manifest(manifest, state, publication)
    digest = checksum(manifest_path, "sha256")
    reference = ManifestDigestReference(
        uri=f"{publication.release_url}#{FINAL_RELEASE_MANIFEST_ASSET_NAME}",
        algorithm="sha256",
        digest=digest,
    )
    manifest_asset = observed_release_assets(release_payload).get(
        FINAL_RELEASE_MANIFEST_ASSET_NAME
    )
    attached = manifest_asset is not None
    if manifest_asset is None:
        upload_release_assets(
            repository,
            tag_name=state.final_tag.name,
            asset_paths=[manifest_path],
            clobber=False,
        )
        release_payload = _release_payload(repository, state.final_tag.name)
        manifest_asset = observed_release_assets(release_payload).get(
            FINAL_RELEASE_MANIFEST_ASSET_NAME
        )
    if manifest_asset is None:
        raise ValueError("GitHub final release manifest is absent after upload")
    if manifest_asset.size_bytes != manifest_path.stat().st_size:
        raise ValueError("GitHub final release manifest asset size mismatch")
    if manifest_asset.digest != f"sha256:{digest}":
        raise ValueError("GitHub final release manifest asset sha256 mismatch")
    publication = validate_final_release(
        state,
        repository,
        release_payload,
        expected_body=expected_body,
        allow_attached_manifest=True,
    )
    outcome: Literal["attached", "already-complete"] = (
        "already-complete" if attached else "attached"
    )
    result = AttachGitHubReleaseManifestResult(
        component=state.release.component.id,
        version=state.release.version,
        release_manifest=reference,
        publication=publication,
        outcome=outcome,
    )
    result_path = _manifest_path(state.release.component.id, result.action)
    write_manifest(result_path, result)
    _append_result_summary(
        "Attach GitHub release manifest",
        outcome=outcome,
        state=state,
        repository=repository,
        release_url=publication.release_url,
    )
    return result_path
