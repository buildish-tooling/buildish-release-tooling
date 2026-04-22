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

"""Provider-neutral lifecycle state commands."""

from __future__ import annotations

import hashlib
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from buildish_release_tooling.release.candidate_release import (
    resolve_candidate_release_state,
    resolve_promotion_state,
)
from buildish_release_tooling.release.config import (
    require_asf_profile,
    require_vote_materials,
)
from buildish_release_tooling.release.core.manifests import (
    AuthenticityReference,
    ByteIdenticalPromotionEvidence,
    ManifestDigestReference,
    PromotionEvidence,
    PromotedCandidateReference,
    SameSourceRevisionPromotionEvidence,
)
from buildish_release_tooling.release.git_repo import GitRepository
from buildish_release_tooling.release.manifest import write_manifest
from buildish_release_tooling.release.manifests import (
    CandidateManifestV1,
    ReleaseManifestV1,
    VotePackageV1,
)
from buildish_release_tooling.release.core.models import (
    PublicationReference,
    ToolingInvocationProvenance,
)
from buildish_release_tooling.release.core.state import (
    CandidateReleaseState,
    DirectReleaseState,
    PromotionState,
)
from buildish_release_tooling.release.foundations.asf.manifests import AsfVoteExtension
from buildish_release_tooling.release.platforms.github.candidate import (
    CANDIDATE_MANIFEST_ASSET_NAME,
)
from buildish_release_tooling.release.platforms.github.manifests import (
    GitHubCandidatePublication,
    PublishGitHubFinalReleaseResult,
    StageGitHubCandidateResult,
)
from buildish_release_tooling.release.summary import SummaryWriter
from buildish_release_tooling.shared.io import read_text_file_bounded
from buildish_release_tooling.shared.parsing import (
    DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    read_json_object_file_bounded,
    read_pydantic_json_file_bounded,
)

from buildish_release_tooling.release.commands._shared import _context, _manifest_path


def run_resolve_candidate(args: Namespace) -> Path:
    """Resolve and emit exact provider-neutral state for one release candidate."""

    context = _context(args)
    state = resolve_candidate_release_state(
        GitRepository.from_current_worktree(),
        context.release_config,
        args.version,
        args.source_ref,
        args.candidate_label,
    )
    result_path = _manifest_path(state.release.component.id, "resolve-candidate")
    write_manifest(result_path, state, exclude_none=True)
    summary = SummaryWriter.from_environment()
    summary.append_heading("Resolve release candidate")
    summary.append_plaintext_block("Version", state.release.version)
    summary.append_plaintext_block("Candidate", state.candidate.tag.name)
    summary.append_plaintext_block("Source ref", state.source.source_ref or "<none>")
    summary.append_plaintext_block("Source commit", state.source.commit_sha)
    return result_path


def run_create_candidate_manifest(args: Namespace) -> Path:
    """Create the durable provider-composed manifest for one staged candidate."""

    context = _context(args)
    if context.release_config.lifecycle.mode != "candidate":
        raise ValueError("create-candidate-manifest requires lifecycle.mode candidate")
    state = read_pydantic_json_file_bounded(
        CandidateReleaseState,
        Path(args.candidate_state),
        max_bytes=DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    )
    stage = read_pydantic_json_file_bounded(
        StageGitHubCandidateResult,
        Path(args.stage_result),
        max_bytes=DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    )
    if state.release.component.id != context.release_config.component.id:
        raise ValueError("candidate state component does not match release configuration")
    if stage.component != state.release.component.id or stage.version != state.release.version:
        raise ValueError("candidate stage result release does not match candidate state")
    if stage.candidate != state.candidate or stage.source_commit != state.source.commit_sha:
        raise ValueError("candidate stage result identity does not match candidate state")
    expected_asset_names = {artifact.logical_name for artifact in stage.artifacts}
    publication_assets = [
        asset
        for asset in stage.publication.assets
        if asset.name != CANDIDATE_MANIFEST_ASSET_NAME
    ]
    if len(publication_assets) != len(stage.publication.assets):
        raise ValueError("candidate manifest already exists; reuse its exact published bytes")
    if {asset.name for asset in publication_assets} != expected_asset_names:
        raise ValueError("candidate publication assets do not match staged artifact inventory")
    for artifact in stage.artifacts:
        asset = next(
            item for item in publication_assets if item.name == artifact.logical_name
        )
        if asset.size_bytes != artifact.size_bytes:
            raise ValueError("candidate publication asset size does not match artifact inventory")
        if asset.digest != f"sha256:{artifact.digests.get('sha256', '')}":
            raise ValueError("candidate publication digest does not match artifact inventory")
    created_at = datetime.fromtimestamp(state.source_date_epoch, tz=UTC).isoformat().replace(
        "+00:00", "Z"
    )
    manifest = CandidateManifestV1(
        release=state.release,
        candidate=state.candidate,
        source=state.source,
        candidate_tag=state.candidate.tag,
        source_date_epoch=state.source_date_epoch,
        artifacts=stage.artifacts,
        verification_results=state.verification_results,
        publications=[
            PublicationReference(
                target_kind="github-release-candidate",
                uri=stage.publication.release_url,
                immutable_id=str(stage.publication.release_id),
            )
        ],
        tooling=state.tooling or ToolingInvocationProvenance(),
        created_at=created_at,
        extensions=[stage.publication],
    )
    result_path = _manifest_path(state.release.component.id, "create-candidate-manifest")
    write_manifest(result_path, manifest, exclude_none=True)
    summary = SummaryWriter.from_environment()
    summary.append_heading("Create candidate manifest")
    summary.append_plaintext_block("Candidate", state.candidate.tag.name)
    summary.append_plaintext_block("GitHub Release", stage.publication.release_url)
    summary.append_plaintext_block("Candidate manifest", str(result_path))
    return result_path


def run_resolve_promotion(args: Namespace) -> Path:
    """Bind one exact candidate manifest and tag into promotion state."""

    context = _context(args)
    manifest_path = Path(args.candidate_manifest)
    manifest_bytes = read_text_file_bounded(
        manifest_path,
        max_bytes=DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    ).encode("utf-8")
    actual_digest = hashlib.sha256(manifest_bytes).hexdigest()
    expected_digest = args.candidate_manifest_digest.lower()
    if actual_digest != expected_digest:
        raise ValueError("candidate manifest bytes do not match selected SHA-256 digest")
    manifest = CandidateManifestV1.model_validate_json(manifest_bytes)
    state = resolve_promotion_state(
        context.release_config,
        manifest,
        version=args.version,
        candidate_tag=args.candidate_tag,
        candidate_manifest_digest=expected_digest,
    )
    result_path = _manifest_path(state.release.component.id, "resolve-promotion")
    write_manifest(result_path, state, exclude_none=True)
    summary = SummaryWriter.from_environment()
    summary.append_heading("Resolve candidate promotion")
    summary.append_plaintext_block("Version", state.release.version)
    summary.append_plaintext_block("Selected candidate", state.candidate.tag.name)
    summary.append_plaintext_block("Candidate manifest SHA-256", expected_digest)
    summary.append_plaintext_block("Final tag", state.final_tag.name)
    return result_path


def _candidate_manifest_reference(
    manifest: CandidateManifestV1,
    *,
    digest: str,
) -> ManifestDigestReference:
    github_extensions = [
        extension
        for extension in manifest.extensions
        if isinstance(extension, GitHubCandidatePublication)
    ]
    if len(github_extensions) != 1:
        raise ValueError(
            "candidate manifest requires exactly one GitHub candidate publication"
        )
    return ManifestDigestReference(
        uri=(
            f"{github_extensions[0].release_url}#"
            f"{CANDIDATE_MANIFEST_ASSET_NAME}"
        ),
        algorithm="sha256",
        digest=digest,
    )


def run_create_vote_package(args: Namespace) -> Path:
    """Create optional generic or ASF-profile vote materials over one candidate."""

    context = _context(args)
    vote_config = require_vote_materials(context.release_config)
    if args.profile != vote_config.profile:
        raise ValueError("requested vote profile does not match release configuration")
    manifest_path = Path(args.candidate_manifest)
    manifest_bytes = read_text_file_bounded(
        manifest_path,
        max_bytes=DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    ).encode("utf-8")
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    manifest = CandidateManifestV1.model_validate_json(manifest_bytes)
    if manifest.release.component.id != context.release_config.component.id:
        raise ValueError("candidate manifest component does not match release configuration")
    reference = _candidate_manifest_reference(manifest, digest=manifest_digest)
    candidate_label = f"{manifest.candidate.label}{manifest.candidate.number}"
    release_name = f"{vote_config.release_name} {manifest.release.version}"
    verification_instructions = (
        f"{vote_config.instructions.strip()}\n\n"
        f"Verification guide: {vote_config.verification_guide_url}"
    )
    opening_lines = [
        f"Please vote on {release_name} ({candidate_label}).",
        "",
        f"Candidate tag: {manifest.candidate.tag.name}",
        f"Candidate manifest: {reference.uri}",
        f"Candidate manifest SHA-256: {reference.digest}",
        "",
        verification_instructions,
        "",
        "[ ] +1 Release this candidate",
        "[ ] +0 No opinion",
        "[ ] -1 Do not release this candidate because...",
    ]
    result_lines = [
        f"Vote result for {release_name} ({candidate_label}):",
        "",
        "+1: <count and voters>",
        "+0: <count and voters>",
        "-1: <count, voters, and reasons>",
        "",
        "Outcome: <external vote authority records the result>",
    ]
    extensions: list[AsfVoteExtension] = []
    if vote_config.profile == "asf":
        asf_profile = require_asf_profile(context.release_config)
        style: Literal["pmc", "ppmc-ipmc"] = (
            "ppmc-ipmc" if asf_profile.is_incubating else "pmc"
        )
        opening_lines.extend(
            [
                "",
                "ASF vote counting, binding status, minimum duration, and veto handling ",
                "are evaluated by the applicable ASF project or Incubator process.",
            ]
        )
        extensions.append(
            AsfVoteExtension(
                style=style,
                keys=AuthenticityReference(
                    kind="openpgp-keyring",
                    uri=asf_profile.keys_url,
                ),
            )
        )
    vote_package = VotePackageV1(
        subject=f"[VOTE] {release_name} ({candidate_label})",
        profile_selector=vote_config.profile,
        candidate_manifest=reference,
        embedded_candidate_manifest=manifest,
        verification_instructions=verification_instructions,
        opening_template="\n".join(opening_lines),
        result_template="\n".join(result_lines),
        extensions=extensions,
        created_at=manifest.created_at,
    )
    result_path = _manifest_path(manifest.release.component.id, "create-vote-package")
    write_manifest(result_path, vote_package, exclude_none=True)
    summary = SummaryWriter.from_environment()
    summary.append_heading("Create vote package")
    summary.append_plaintext_block("Candidate", manifest.candidate.tag.name)
    summary.append_plaintext_block("Vote profile", vote_config.profile)
    summary.append_plaintext_block("Candidate manifest SHA-256", manifest_digest)
    return result_path


def _load_final_state(path: Path) -> DirectReleaseState | PromotionState:
    payload = read_json_object_file_bounded(
        path,
        max_bytes=DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    )
    if "candidate_manifest_digest" in payload:
        return PromotionState.model_validate(payload)
    return DirectReleaseState.model_validate(payload)


def run_create_release_manifest(args: Namespace) -> Path:
    """Create a stable final manifest for a direct release or exact promotion."""

    context = _context(args)
    state = _load_final_state(Path(args.release_state))
    publication_result = read_pydantic_json_file_bounded(
        PublishGitHubFinalReleaseResult,
        Path(args.publication_result),
        max_bytes=DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    )
    if state.release.component.id != context.release_config.component.id:
        raise ValueError("final-release state component does not match configuration")
    if (
        publication_result.component != state.release.component.id
        or publication_result.version != state.release.version
        or publication_result.source_commit != state.source.commit_sha
    ):
        raise ValueError("final publication result does not match final-release state")
    promoted_candidate = None
    promotion_evidence: list[PromotionEvidence] = []
    if isinstance(state, PromotionState):
        candidate_publications = [
            publication
            for publication in state.publications
            if publication.target_kind == "github-release-candidate"
        ]
        if len(candidate_publications) != 1:
            raise ValueError(
                "promotion state requires one GitHub candidate publication reference"
            )
        promoted_candidate = PromotedCandidateReference(
            candidate=state.candidate,
            manifest=ManifestDigestReference(
                uri=(
                    f"{candidate_publications[0].uri}#"
                    f"{CANDIDATE_MANIFEST_ASSET_NAME}"
                ),
                algorithm="sha256",
                digest=state.candidate_manifest_digest,
            ),
        )
        promotion_evidence.extend(
            ByteIdenticalPromotionEvidence(
                artifact_name=artifact.logical_name,
                candidate_digests=artifact.digests,
                final_digests=artifact.digests,
            )
            for artifact in state.artifacts
        )
        if not state.artifacts:
            promotion_evidence.append(
                SameSourceRevisionPromotionEvidence(
                    artifact_name="platform-generated-source-snapshot",
                    candidate_tag=state.candidate.tag.name,
                    final_tag=state.final_tag.name,
                    source_commit_sha=state.source.commit_sha,
                )
            )
    created_at = datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    manifest = ReleaseManifestV1(
        release=state.release,
        source=state.source,
        final_tag=state.final_tag,
        artifacts=state.artifacts,
        publications=[
            PublicationReference(
                target_kind="github-release-final",
                uri=publication_result.publication.release_url,
                immutable_id=str(publication_result.publication.release_id),
            )
        ],
        verification_results=state.verification_results,
        promoted_candidate=promoted_candidate,
        promotion_evidence=promotion_evidence,
        tooling=state.tooling or ToolingInvocationProvenance(),
        created_at=created_at,
        extensions=[publication_result.publication],
    )
    result_path = _manifest_path(state.release.component.id, "create-release-manifest")
    write_manifest(result_path, manifest, exclude_none=True)
    summary = SummaryWriter.from_environment()
    summary.append_heading("Create release manifest")
    summary.append_plaintext_block("Version", state.release.version)
    summary.append_plaintext_block("Final tag", state.final_tag.name)
    summary.append_plaintext_block(
        "Promoted candidate",
        state.candidate.tag.name if isinstance(state, PromotionState) else "<none>",
    )
    return result_path
