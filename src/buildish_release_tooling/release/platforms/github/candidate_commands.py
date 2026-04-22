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

"""GitHub release-candidate command handlers."""

from __future__ import annotations

import hashlib
from argparse import Namespace
from io import BytesIO
from pathlib import Path
from typing import Literal

from buildish_release_tooling.release.commands._shared import (
    _context,
    _create_or_reuse_annotated_tag,
    _manifest_path,
)
from buildish_release_tooling.release.config import (
    require_candidate_config,
    require_github_authoritative_publication,
)
from buildish_release_tooling.release.core.manifests import ManifestDigestReference
from buildish_release_tooling.release.core.models import TagIdentity
from buildish_release_tooling.release.core.state import CandidateReleaseState
from buildish_release_tooling.release.git_repo import GitRepository
from buildish_release_tooling.release.manifest import write_manifest
from buildish_release_tooling.release.manifests import CandidateManifestV1
from buildish_release_tooling.release.platforms.github.candidate import (
    CANDIDATE_MANIFEST_ASSET_NAME,
    candidate_release_name,
    candidate_state_with_local_artifacts,
    missing_candidate_release_assets,
    validate_candidate_release,
)
from buildish_release_tooling.release.platforms.github.checks import (
    resolve_repository_slug,
)
from buildish_release_tooling.release.platforms.github.direct import (
    observed_release_assets,
    validate_local_release_assets,
)
from buildish_release_tooling.release.platforms.github.manifests import (
    AttachGitHubCandidateManifestResult,
    CreateGitHubCandidateTagResult,
    FinalizeGitHubCandidateResult,
    GitHubCandidatePublication,
    StageGitHubCandidateResult,
    VerifyGitHubCandidateResult,
)
from buildish_release_tooling.release.platforms.github.refs import (
    resolve_annotated_tag_target_commit,
)
from buildish_release_tooling.release.platforms.github.releases import (
    create_draft_release,
    download_release_asset_text,
    list_releases,
    release_by_tag,
    release_by_tag_or_none,
    update_release,
    upload_release_assets,
)
from buildish_release_tooling.release.platforms.github.text import (
    render_candidate_release_body,
)
from buildish_release_tooling.release.summary import SummaryWriter
from buildish_release_tooling.release.source_artifact import checksum
from buildish_release_tooling.shared.parsing import (
    DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    read_pydantic_json_file_bounded,
)
from buildish_release_tooling.shared.io import copy_stream_to_path


def _load_candidate_state(path_text: str) -> CandidateReleaseState:
    return read_pydantic_json_file_bounded(
        CandidateReleaseState,
        Path(path_text),
        max_bytes=DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    )


def _validated_candidate_context(
    args: Namespace,
    state: CandidateReleaseState,
) -> tuple[GitRepository, str]:
    context = _context(args)
    if context.release_config.lifecycle.mode != "candidate":
        raise ValueError("GitHub candidate commands require lifecycle.mode candidate")
    if state.release.component.id != context.release_config.component.id:
        raise ValueError(
            "candidate state component does not match release configuration"
        )
    target = require_github_authoritative_publication(context.release_config)
    repo = GitRepository.from_current_worktree()
    repository = target.repository or resolve_repository_slug(repo.path)
    return repo, repository


def _validate_candidate_tags(
    state: CandidateReleaseState,
    repo: GitRepository,
    repository: str,
) -> None:
    local_target = (
        repo.resolve_commit(state.candidate.tag.name)
        if repo.tag_exists(state.candidate.tag.name)
        else None
    )
    if local_target != state.source.commit_sha:
        if local_target is None:
            raise ValueError(
                f"candidate tag does not exist: {state.candidate.tag.name}"
            )
        raise ValueError(
            "local candidate tag target does not match candidate source commit"
        )
    remote_target = resolve_annotated_tag_target_commit(
        repository,
        tag_name=state.candidate.tag.name,
    )
    if remote_target != state.source.commit_sha:
        raise ValueError(
            "GitHub candidate tag target does not match candidate source commit"
        )


def _append_summary(
    heading: str,
    *,
    outcome: str,
    state: CandidateReleaseState,
    repository: str,
    release_url: str | None = None,
) -> None:
    summary = SummaryWriter.from_environment()
    summary.append_heading(heading)
    summary.append_plaintext_block("Outcome", outcome)
    summary.append_plaintext_block("Candidate", state.candidate.tag.name)
    summary.append_plaintext_block("Source commit", state.source.commit_sha)
    summary.append_plaintext_block("GitHub repository", repository)
    if release_url is not None:
        summary.append_plaintext_block("GitHub Release", release_url)


def run_create_candidate_tag(args: Namespace) -> Path:
    """Create or revalidate one immutable annotated candidate tag."""

    state = _load_candidate_state(args.candidate_state)
    repo, repository = _validated_candidate_context(args, state)
    message = (
        f"Release candidate {state.release.component.display_name} "
        f"{state.release.version} ({state.candidate.label}{state.candidate.number})"
    )
    mode, _created_ref = _create_or_reuse_annotated_tag(
        repo=repo,
        repository_slug=repository,
        tag_name=state.candidate.tag.name,
        target_commit=state.source.commit_sha,
        message=message,
        allow_update=False,
    )
    if not repo.tag_exists(state.candidate.tag.name):
        repo.create_annotated_tag(
            state.candidate.tag.name,
            state.source.commit_sha,
            message,
        )
    _validate_candidate_tags(state, repo, repository)
    outcome: Literal["created", "already-complete"] = (
        "already-complete" if mode == "already-present" else "created"
    )
    result = CreateGitHubCandidateTagResult(
        component=state.release.component.id,
        version=state.release.version,
        candidate=state.candidate,
        source_commit=state.source.commit_sha,
        outcome=outcome,
    )
    result_path = _manifest_path(state.release.component.id, result.action)
    write_manifest(result_path, result)
    _append_summary(
        "Create candidate tag",
        outcome=outcome,
        state=state,
        repository=repository,
    )
    return result_path


def run_stage_github_candidate(args: Namespace) -> Path:
    """Create or complete an exact draft candidate release without overwrites."""

    initial_state = _load_candidate_state(args.candidate_state)
    repo, repository = _validated_candidate_context(args, initial_state)
    _validate_candidate_tags(initial_state, repo, repository)
    paths = [Path(path) for path in args.assets]
    state = candidate_state_with_local_artifacts(initial_state, paths)
    validate_local_release_assets(state, paths)
    releases = list_releases(repository)
    existing = release_by_tag_or_none(releases, tag_name=state.candidate.tag.name)
    created = existing is None
    body = render_candidate_release_body(state, state.artifacts)
    if existing is None:
        release_payload = create_draft_release(
            repository,
            tag_name=state.candidate.tag.name,
            target_commitish=state.source.commit_sha,
            release_name=candidate_release_name(state),
            release_body=body,
        )
    else:
        release_payload = existing
    missing_names = missing_candidate_release_assets(state, release_payload)
    if missing_names:
        if release_payload.get("draft") is not True:
            raise ValueError("published GitHub candidate is missing expected assets")
        paths_by_name = {path.name: path for path in paths}
        upload_release_assets(
            repository,
            tag_name=state.candidate.tag.name,
            asset_paths=[paths_by_name[name] for name in missing_names],
            clobber=False,
        )
        release_payload = release_by_tag(
            list_releases(repository),
            tag_name=state.candidate.tag.name,
        )
    publication = validate_candidate_release(
        state,
        repository,
        release_payload,
        allow_attached_manifest=True,
    )
    outcome: Literal["created", "completed", "already-complete"] = (
        "created" if created else ("completed" if missing_names else "already-complete")
    )
    result = StageGitHubCandidateResult(
        component=state.release.component.id,
        version=state.release.version,
        candidate=state.candidate,
        source_commit=state.source.commit_sha,
        artifacts=state.artifacts,
        publication=publication,
        outcome=outcome,
    )
    result_path = _manifest_path(state.release.component.id, result.action)
    write_manifest(result_path, result)
    _append_summary(
        "Stage GitHub candidate",
        outcome=outcome,
        state=state,
        repository=repository,
        release_url=publication.release_url,
    )
    return result_path


def _validate_manifest_for_state(
    manifest: CandidateManifestV1,
    state: CandidateReleaseState,
) -> None:
    if manifest.release != state.release:
        raise ValueError("candidate manifest release does not match candidate state")
    if manifest.candidate != state.candidate or manifest.source != state.source:
        raise ValueError("candidate manifest identity does not match candidate state")
    if manifest.candidate_tag != state.candidate.tag:
        raise ValueError("candidate manifest tag does not match candidate state")


def _manifest_reference(
    manifest_path: Path,
    *,
    release_url: str,
) -> ManifestDigestReference:
    if manifest_path.name != CANDIDATE_MANIFEST_ASSET_NAME:
        raise ValueError(
            f"candidate manifest must be named {CANDIDATE_MANIFEST_ASSET_NAME}"
        )
    return ManifestDigestReference(
        uri=f"{release_url}#{CANDIDATE_MANIFEST_ASSET_NAME}",
        algorithm="sha256",
        digest=checksum(manifest_path, "sha256"),
    )


def _validate_manifest_publication(
    manifest: CandidateManifestV1,
    publication: GitHubCandidatePublication,
) -> None:
    extensions = [
        extension
        for extension in manifest.extensions
        if isinstance(extension, GitHubCandidatePublication)
    ]
    if len(extensions) != 1:
        raise ValueError(
            "candidate manifest requires exactly one GitHub candidate publication"
        )
    build_assets = [
        asset
        for asset in publication.assets
        if asset.name != CANDIDATE_MANIFEST_ASSET_NAME
    ]
    extension = extensions[0]
    if (
        extension.repository != publication.repository
        or extension.release_id != publication.release_id
        or extension.release_url != publication.release_url
        or extension.tag != publication.tag
        or extension.assets != build_assets
    ):
        raise ValueError(
            "candidate manifest GitHub publication does not match observed release"
        )
    matching_references = [
        reference
        for reference in manifest.publications
        if reference.target_kind == "github-release-candidate"
    ]
    if len(matching_references) != 1:
        raise ValueError(
            "candidate manifest requires one neutral GitHub publication reference"
        )
    reference = matching_references[0]
    if reference.uri != publication.release_url or reference.immutable_id != str(
        publication.release_id
    ):
        raise ValueError(
            "candidate manifest publication reference does not match observed release"
        )


def run_attach_github_candidate_manifest(args: Namespace) -> Path:
    """Attach and revalidate one exact candidate manifest without clobbering."""

    state = _load_candidate_state(args.candidate_state)
    repo, repository = _validated_candidate_context(args, state)
    _validate_candidate_tags(state, repo, repository)
    manifest_path = Path(args.candidate_manifest)
    manifest = read_pydantic_json_file_bounded(
        CandidateManifestV1,
        manifest_path,
        max_bytes=DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    )
    _validate_manifest_for_state(manifest, state)
    state = state.model_copy(update={"artifacts": manifest.artifacts})
    release_payload = release_by_tag(
        list_releases(repository),
        tag_name=state.candidate.tag.name,
    )
    publication = validate_candidate_release(
        state,
        repository,
        release_payload,
        allow_attached_manifest=True,
    )
    _validate_manifest_publication(manifest, publication)
    reference = _manifest_reference(
        manifest_path,
        release_url=publication.release_url,
    )
    observed = observed_release_assets(release_payload)
    manifest_asset = observed.get(CANDIDATE_MANIFEST_ASSET_NAME)
    attached = manifest_asset is not None
    if manifest_asset is not None:
        if manifest_asset.size_bytes != manifest_path.stat().st_size:
            raise ValueError("GitHub candidate manifest asset size mismatch")
        if manifest_asset.digest != f"sha256:{reference.digest}":
            raise ValueError("GitHub candidate manifest asset sha256 mismatch")
    else:
        if not publication.draft:
            raise ValueError(
                "published GitHub candidate is missing its durable manifest"
            )
        upload_release_assets(
            repository,
            tag_name=state.candidate.tag.name,
            asset_paths=[manifest_path],
            clobber=False,
        )
        release_payload = release_by_tag(
            list_releases(repository),
            tag_name=state.candidate.tag.name,
        )
        publication = validate_candidate_release(
            state,
            repository,
            release_payload,
            allow_attached_manifest=True,
        )
        manifest_asset = observed_release_assets(release_payload).get(
            CANDIDATE_MANIFEST_ASSET_NAME
        )
        if manifest_asset is None:
            raise ValueError("GitHub candidate manifest is absent after upload")
        if manifest_asset.size_bytes != manifest_path.stat().st_size:
            raise ValueError(
                "GitHub candidate manifest asset size mismatch after upload"
            )
        if manifest_asset.digest != f"sha256:{reference.digest}":
            raise ValueError(
                "GitHub candidate manifest asset sha256 mismatch after upload"
            )
    outcome: Literal["attached", "already-complete"] = (
        "already-complete" if attached else "attached"
    )
    result = AttachGitHubCandidateManifestResult(
        component=state.release.component.id,
        version=state.release.version,
        candidate=state.candidate,
        candidate_manifest=reference,
        publication=publication,
        outcome=outcome,
    )
    result_path = _manifest_path(state.release.component.id, result.action)
    write_manifest(result_path, result)
    _append_summary(
        "Attach GitHub candidate manifest",
        outcome=outcome,
        state=state,
        repository=repository,
        release_url=publication.release_url,
    )
    return result_path


def _verified_remote_candidate(
    args: Namespace,
) -> tuple[
    CandidateManifestV1,
    CandidateReleaseState,
    GitHubCandidatePublication,
    ManifestDigestReference,
    str,
    str,
]:
    context = _context(args)
    if context.release_config.lifecycle.mode != "candidate":
        raise ValueError("GitHub candidate commands require lifecycle.mode candidate")
    target = require_github_authoritative_publication(context.release_config)
    repo = GitRepository.from_current_worktree()
    repository = target.repository or resolve_repository_slug(repo.path)
    release_payload = release_by_tag(
        list_releases(repository),
        tag_name=args.candidate_tag,
    )
    assets = observed_release_assets(release_payload)
    manifest_asset = assets.get(CANDIDATE_MANIFEST_ASSET_NAME)
    if manifest_asset is None:
        raise ValueError("GitHub candidate does not contain candidate-manifest.json")
    expected_digest = args.candidate_manifest_digest.lower()
    if manifest_asset.digest != f"sha256:{expected_digest}":
        raise ValueError(
            "GitHub candidate manifest digest does not match selected digest"
        )
    manifest_text = download_release_asset_text(repository, manifest_asset.asset_id)
    if len(manifest_text.encode("utf-8")) > DEFAULT_MANIFEST_PARSE_MAX_BYTES:
        raise ValueError("downloaded candidate manifest exceeds the maximum size")
    actual_digest = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
    if actual_digest != expected_digest:
        raise ValueError(
            "downloaded candidate manifest digest does not match selected digest"
        )
    manifest = CandidateManifestV1.model_validate_json(manifest_text)
    if manifest.release.component.id != context.release_config.component.id:
        raise ValueError(
            "candidate manifest component does not match release configuration"
        )
    if manifest.candidate.tag.name != args.candidate_tag:
        raise ValueError("candidate manifest does not match selected candidate tag")
    if manifest.source_date_epoch is None:
        raise ValueError("candidate manifest requires source_date_epoch for promotion")
    state = CandidateReleaseState(
        release=manifest.release,
        source=manifest.source,
        source_date_epoch=manifest.source_date_epoch,
        candidate=manifest.candidate,
        final_tag_identity=TagIdentity(
            name=context.release_config.versioning.final_tag_template.format(
                version=manifest.release.version
            ),
            target_commit=manifest.source.commit_sha,
            purpose="final",
        ),
        artifacts=manifest.artifacts,
        verification_results=manifest.verification_results,
        publications=manifest.publications,
        tooling=manifest.tooling,
    )
    _validate_candidate_tags(state, repo, repository)
    publication = validate_candidate_release(
        state,
        repository,
        release_payload,
        allow_attached_manifest=True,
    )
    _validate_manifest_publication(manifest, publication)
    reference = ManifestDigestReference(
        uri=f"{publication.release_url}#{CANDIDATE_MANIFEST_ASSET_NAME}",
        algorithm="sha256",
        digest=expected_digest,
    )
    return manifest, state, publication, reference, repository, manifest_text


def run_verify_github_candidate(args: Namespace) -> Path:
    """Verify one candidate tag, release, asset set, and durable manifest."""

    (
        _manifest,
        state,
        publication,
        reference,
        repository,
        manifest_text,
    ) = _verified_remote_candidate(args)
    output_path_text = getattr(args, "candidate_manifest_output", None)
    if output_path_text:
        output_path = Path(output_path_text)
        copy_stream_to_path(
            BytesIO(manifest_text.encode("utf-8")),
            output_path,
            algorithms=("sha256",),
            max_bytes=DEFAULT_MANIFEST_PARSE_MAX_BYTES,
        )
    result = VerifyGitHubCandidateResult(
        component=state.release.component.id,
        version=state.release.version,
        candidate=state.candidate,
        candidate_manifest=reference,
        publication=publication,
    )
    result_path = _manifest_path(state.release.component.id, result.action)
    write_manifest(result_path, result)
    _append_summary(
        "Verify GitHub candidate",
        outcome=result.outcome,
        state=state,
        repository=repository,
        release_url=publication.release_url,
    )
    return result_path


def run_finalize_github_candidate(args: Namespace) -> Path:
    """Apply configured candidate visibility after exact manifest verification."""

    _manifest, state, publication, reference, repository, _manifest_text = (
        _verified_remote_candidate(args)
    )
    candidate_config = require_candidate_config(_context(args).release_config)
    if candidate_config.visibility == "draft":
        if not publication.draft:
            raise ValueError("configured draft candidate has already been published")
        outcome: Literal["published", "retained-draft", "already-complete"] = (
            "retained-draft"
        )
    elif publication.draft:
        update_release(
            repository,
            publication.release_id,
            payload={
                "tag_name": state.candidate.tag.name,
                "target_commitish": state.source.commit_sha,
                "name": candidate_release_name(state),
                "body": render_candidate_release_body(state, state.artifacts),
                "draft": False,
                "prerelease": True,
            },
        )
        release_payload = release_by_tag(
            list_releases(repository),
            tag_name=state.candidate.tag.name,
        )
        publication = validate_candidate_release(
            state,
            repository,
            release_payload,
            allow_attached_manifest=True,
        )
        if publication.draft or not publication.prerelease:
            raise ValueError(
                "GitHub candidate visibility did not converge after publication"
            )
        outcome = "published"
    else:
        outcome = "already-complete"
    result = FinalizeGitHubCandidateResult(
        component=state.release.component.id,
        version=state.release.version,
        candidate=state.candidate,
        candidate_manifest=reference,
        publication=publication,
        outcome=outcome,
    )
    result_path = _manifest_path(state.release.component.id, result.action)
    write_manifest(result_path, result)
    _append_summary(
        "Finalize GitHub candidate",
        outcome=outcome,
        state=state,
        repository=repository,
        release_url=publication.release_url,
    )
    return result_path
