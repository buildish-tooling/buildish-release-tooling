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

"""Helpers for the signed RC vote-manifest artifact."""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from apache_buildish_release_tooling.release.git_repo import GitRepository
from apache_buildish_release_tooling.release.github_checks import resolve_repository_slug
from apache_buildish_release_tooling.release.contracts import (
    AuthoritativeManifestReference,
    DraftGithubRelease,
    IncubatorDisclaimer,
    GithubWorkflowProvenance,
    ManifestProvenance,
    ManifestTrustRoots,
    ManifestVerificationMetadataStrict,
    ReproducibilitySelector,
    Sha512ChecksumPayload,
    Sha512Checksums,
    SignatureReference,
    SourceArtifactContract,
    ToolingProvenance,
    VoteMaterialsStrict,
    AnySecondaryArtifact,
    AsfKeysTrustRoot,
    RcVoteManifestV1,
)
from apache_buildish_release_tooling.release.models import ComponentConfig, PrepareRcState
from apache_buildish_release_tooling.release.release_state import derive_specific_release_line

DEFAULT_URI_READ_TIMEOUT_SECONDS = 60.0


def _tooling_repo_root() -> Path:
    """Resolve the checked-out repository root of `buildish-release-tooling`."""

    return Path(__file__).resolve().parents[2]


def origin_repository_metadata(repo: GitRepository) -> tuple[str, str]:
    """Resolve repository slug and normalized HTTPS URL from the `origin` remote."""

    try:
        repository_slug = resolve_repository_slug(repo.path)
        return repository_slug, f"https://github.com/{repository_slug}"
    except ValueError:
        try:
            remote_url = repo.remote_url()
        except ValueError:
            return repo.path.name, repo.path.as_uri()
        normalized_url = remote_url.removesuffix(".git")
        parsed = urlparse(normalized_url)
        if parsed.scheme and parsed.netloc:
            repository_slug = parsed.path.removeprefix("/")
            return repository_slug, normalized_url
        return repo.path.name, repo.path.as_uri()


def _tooling_git_ref(repo: GitRepository) -> tuple[str | None, str | None]:
    """Resolve the most descriptive Git ref and optional released version for tooling provenance."""

    head_tags = sorted(tag for tag in repo.tags_pointing_at("HEAD") if tag.startswith("v"))
    if head_tags:
        tag_name = head_tags[0]
        return f"refs/tags/{tag_name}", tag_name.removeprefix("v")
    symbolic_ref = repo.current_symbolic_ref()
    return symbolic_ref, None


def tooling_provenance() -> ToolingProvenance:
    """Build provenance metadata for the checked-out release-tooling source tree."""

    repo = GitRepository.from_current_worktree(_tooling_repo_root())
    repository, repository_url = origin_repository_metadata(repo)
    git_ref, version = _tooling_git_ref(repo)
    return ToolingProvenance(
        repository=repository,
        repository_url=repository_url,
        git_commit_sha=repo.current_head_commit(),
        git_ref=git_ref,
        version=version,
    )


def github_workflow_provenance(default_repository: str) -> GithubWorkflowProvenance | None:
    """Build GitHub Actions workflow provenance when running inside GitHub Actions."""

    repository = os.environ.get("GITHUB_REPOSITORY") or default_repository
    run_id = os.environ.get("GITHUB_RUN_ID")
    if not run_id:
        return None
    server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    run_url = (
        f"{server_url.rstrip('/')}/{repository}/actions/runs/{run_id}"
        if repository
        else None
    )
    run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT")
    return GithubWorkflowProvenance(
        repository=repository,
        workflow=os.environ.get("GITHUB_WORKFLOW", ""),
        workflow_ref=os.environ.get("GITHUB_WORKFLOW_REF", ""),
        run_id=int(run_id),
        run_attempt=int(run_attempt) if run_attempt and run_attempt.isdigit() else None,
        run_url=run_url,
    )


def created_at_utc() -> str:
    """Return the current UTC timestamp formatted for manifest provenance."""

    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def derive_asf_keys_uri(release_base_url: str) -> str:
    """Derive the KEYS URL shared by all Buildish components from one component release base."""

    release_parent = release_base_url.rstrip("/").rsplit("/", 1)[0]
    if release_parent.startswith("https://dist.apache.org/repos/dist/release/"):
        release_parent = release_parent.replace(
            "https://dist.apache.org/repos/dist/release/",
            "https://downloads.apache.org/",
            1,
        )
    return f"{release_parent}/KEYS"


def read_uri_bytes(uri: str) -> bytes:
    """Read bytes from a `file://`, `http://`, or `https://` URI."""

    parsed = urlparse(uri)
    if parsed.scheme == "file":
        local_path = Path(parsed.path)
        if local_path.exists():
            return local_path.read_bytes()
        try:
            completed = subprocess.run(
                ["svn", "cat", uri],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr_text = exc.stderr.decode("utf-8", errors="replace").strip()
            detail = stderr_text or f"svn cat returned exit status {exc.returncode}"
            raise ValueError(f"file URI could not be read: {uri}: {detail}") from exc
        return completed.stdout
    if parsed.scheme in {"http", "https"}:
        with urlopen(uri, timeout=DEFAULT_URI_READ_TIMEOUT_SECONDS) as response:  # noqa: S310
            return response.read()
    raise ValueError(f"unsupported URI scheme: {uri}")


def read_uri_text(uri: str) -> str:
    """Read UTF-8 text from a supported URI."""

    return read_uri_bytes(uri).decode("utf-8")


def trust_root_metadata(keys_uri: str) -> ManifestTrustRoots:
    """Build the KEYS trust-root block for one explicit ASF KEYS URI."""

    keys_payload = read_uri_bytes(keys_uri)
    return ManifestTrustRoots(
        asf_keys=AsfKeysTrustRoot(
            uri=keys_uri,
            known_length_bytes=len(keys_payload),
            known_prefix_sha512=hashlib.sha512(keys_payload).hexdigest(),
        )
    )


def build_rc_vote_manifest(
    *,
    component_config: ComponentConfig,
    state: PrepareRcState,
    repository_slug: str,
    source_repository_url: str,
    draft_release_tag: str,
    draft_release_url: str,
    rc_tag_target_commit: str,
    source_artifact_sha512: str,
    incubator_disclaimer: IncubatorDisclaimer | None,
    secondary_artifacts: Sequence[AnySecondaryArtifact],
) -> RcVoteManifestV1:
    """Build the machine-readable RC inventory staged for vote."""

    manifest_filename = "rc-vote-manifest.json"
    staging_url = state.staging_url.rstrip("/")
    source_artifact_url = f"{staging_url}/{state.source_artifact_name}"
    manifest_url = f"{staging_url}/{manifest_filename}"
    materialized_commit_sha: str | None = None
    if component_config.final_tag_mode == "detached-materialization-commit":
        materialized_commit_sha = rc_tag_target_commit
    source_reproducibility = (
        component_config.verify_rc.source.reproducibility
        if component_config.verify_rc is not None and component_config.verify_rc.source is not None
        else None
    )
    source_artifact_payload = SourceArtifactContract(
        filename=state.source_artifact_name,
        uri=source_artifact_url,
        artifact_origin="source-commit",
        git_commit_sha=state.resolved_source_ref,
        reproducibility=(
            ReproducibilitySelector(profile_id=source_reproducibility.profile_id)
            if source_reproducibility is not None
            else None
        ),
        checksums=Sha512Checksums(
            sha512=Sha512ChecksumPayload(
                value=source_artifact_sha512,
                uri=f"{source_artifact_url}.sha512",
            )
        ),
        signatures=[SignatureReference(uri=f"{source_artifact_url}.asc")],
    )
    provenance = ManifestProvenance(
        created_at=created_at_utc(),
        tooling=tooling_provenance(),
        github=github_workflow_provenance(repository_slug),
    )
    return RcVoteManifestV1(
        component_id=component_config.component_id,
        version=state.final_tag.removeprefix("v"),
        release_line=derive_specific_release_line(state.final_tag.removeprefix("v")),
        release_branch=state.resolved_release_branch,
        source_repository_url=source_repository_url,
        source_commit_sha=state.resolved_source_ref,
        source_date_epoch=state.source_date_epoch,
        rc_tag=state.rc_tag,
        final_tag=state.final_tag,
        final_tag_mode=component_config.final_tag_mode,
        provenance=provenance,
        trust_roots=trust_root_metadata(component_config.asf_keys_url),
        draft_github_release=DraftGithubRelease(
            repository=repository_slug,
            tag=draft_release_tag,
            url=draft_release_url,
        ),
        incubator_disclaimer=incubator_disclaimer,
        vote_materials=VoteMaterialsStrict(
            source_artifacts=[source_artifact_payload],
            secondary_artifacts=list(secondary_artifacts),
        ),
        verification=ManifestVerificationMetadataStrict(
            staging_svn_url=f"{staging_url}/",
            authoritative_manifest=AuthoritativeManifestReference(
                uri=manifest_url,
                checksum_uris={"sha512": f"{manifest_url}.sha512"},
                signatures=[SignatureReference(uri=f"{manifest_url}.asc")],
            ),
        ),
        materialized_commit_sha=materialized_commit_sha,
    )
