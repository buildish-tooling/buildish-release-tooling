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

"""Helpers for the signed RC vote-manifest artifact."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import IO
from urllib.parse import ParseResult, unquote, urlparse

from buildish_release_tooling.shared.downloader import DownloadSession
from buildish_release_tooling.shared.io import (
    CopiedResource,
    copy_stream_to_path,
    hash_file,
    hash_stream,
    read_bytes_bounded,
    read_text_bounded,
)
from buildish_release_tooling.release.git_repo import GitRepository
from buildish_release_tooling.release.platforms.github.checks import resolve_repository_slug
from buildish_release_tooling.release.contracts import (
    AuthoritativeManifestReference,
    DraftGitHubRelease,
    IncubatorDisclaimer,
    GitHubWorkflowProvenance,
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
from buildish_release_tooling.release.config import ReleaseConfig, require_asf_profile
from buildish_release_tooling.release.core.state import CandidateReleaseState
from buildish_release_tooling.release.core.naming import derive_specific_release_line

DEFAULT_URI_READ_TIMEOUT_SECONDS = 60.0
DEFAULT_SVN_CAT_TIMEOUT_SECONDS = 60.0
DEFAULT_URI_READ_MAX_BYTES = 25 * 1024 * 1024
DEFAULT_URI_DOWNLOAD_MAX_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_MANIFEST_MAX_BYTES = 25 * 1024 * 1024
DEFAULT_KEYS_MAX_BYTES = 25 * 1024 * 1024
DEFAULT_SIGNATURE_MAX_BYTES = 1024 * 1024
DEFAULT_CHECKSUM_SIDECAR_MAX_BYTES = 1024 * 1024


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


def github_workflow_provenance(default_repository: str) -> GitHubWorkflowProvenance | None:
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
    return GitHubWorkflowProvenance(
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


def read_uri_bytes(
    uri: str,
    *,
    max_bytes: int = DEFAULT_URI_READ_MAX_BYTES,
    download_session: DownloadSession | None = None,
) -> bytes:
    """Read bytes from a `file://`, `http://`, or `https://` URI."""

    parsed = urlparse(uri)
    if parsed.scheme == "file":
        local_path = _local_file_uri_path(parsed, uri)
        if local_path.exists():
            with local_path.open("rb") as handle:
                return read_bytes_bounded(handle, max_bytes=max_bytes)
        with tempfile.TemporaryFile() as stdout_file:
            _svn_cat_to_file(uri, stdout_file)
            stdout_file.seek(0)
            return read_bytes_bounded(stdout_file, max_bytes=max_bytes)
    if parsed.scheme in {"http", "https"}:
        if download_session is not None:
            return download_session.read_bytes(uri, max_bytes=max_bytes)
        with DownloadSession.non_production(timeout=DEFAULT_URI_READ_TIMEOUT_SECONDS) as session:
            return session.read_bytes(uri, max_bytes=max_bytes)
    raise ValueError(f"unsupported URI scheme: {uri}")


def read_uri_text(
    uri: str,
    *,
    max_bytes: int = DEFAULT_URI_READ_MAX_BYTES,
    download_session: DownloadSession | None = None,
) -> str:
    """Read UTF-8 text from a supported URI."""

    parsed = urlparse(uri)
    if parsed.scheme == "file":
        local_path = _local_file_uri_path(parsed, uri)
        if local_path.exists():
            with local_path.open("rb") as handle:
                return read_text_bounded(handle, max_bytes=max_bytes)
        with tempfile.TemporaryFile() as stdout_file:
            _svn_cat_to_file(uri, stdout_file)
            stdout_file.seek(0)
            return read_text_bounded(stdout_file, max_bytes=max_bytes)
    if parsed.scheme in {"http", "https"}:
        if download_session is not None:
            return download_session.read_text(uri, max_bytes=max_bytes)
        with DownloadSession.non_production(timeout=DEFAULT_URI_READ_TIMEOUT_SECONDS) as session:
            return session.read_text(uri, max_bytes=max_bytes)
    raise ValueError(f"unsupported URI scheme: {uri}")


def download_uri_to_path(
    uri: str,
    destination: Path,
    *,
    max_bytes: int = DEFAULT_URI_DOWNLOAD_MAX_BYTES,
    download_session: DownloadSession | None = None,
) -> CopiedResource:
    """Download a supported URI to disk while enforcing a maximum size."""

    parsed = urlparse(uri)
    if parsed.scheme == "file":
        local_path = _local_file_uri_path(parsed, uri)
        if local_path.exists():
            with local_path.open("rb") as handle:
                return copy_stream_to_path(handle, destination, max_bytes=max_bytes)
        with tempfile.TemporaryFile() as stdout_file:
            _svn_cat_to_file(uri, stdout_file)
            stdout_file.seek(0)
            return copy_stream_to_path(stdout_file, destination, max_bytes=max_bytes)
    if parsed.scheme in {"http", "https"}:
        if download_session is not None:
            downloaded = download_session.download_to_path(uri, destination, max_bytes=max_bytes)
        else:
            with DownloadSession.non_production(timeout=DEFAULT_URI_READ_TIMEOUT_SECONDS) as session:
                downloaded = session.download_to_path(uri, destination, max_bytes=max_bytes)
        return CopiedResource(
            path=downloaded.path,
            size_bytes=downloaded.size_bytes,
            hashes=downloaded.hashes,
        )
    raise ValueError(f"unsupported URI scheme: {uri}")


def uri_sha512(uri: str, *, download_session: DownloadSession | None = None) -> str:
    """Compute the SHA512 digest for a supported URI without loading it all."""

    parsed = urlparse(uri)
    if parsed.scheme == "file":
        local_path = _local_file_uri_path(parsed, uri)
        if local_path.exists():
            return hash_file(local_path, algorithm="sha512")
        with tempfile.TemporaryFile() as stdout_file:
            _svn_cat_to_file(uri, stdout_file)
            stdout_file.seek(0)
            return hash_stream(stdout_file, algorithm="sha512")
    if parsed.scheme in {"http", "https"}:
        if download_session is not None:
            return download_session.hash_uri(uri, algorithm="sha512")
        with DownloadSession.non_production(timeout=DEFAULT_URI_READ_TIMEOUT_SECONDS) as session:
            return session.hash_uri(uri, algorithm="sha512")
    raise ValueError(f"unsupported URI scheme: {uri}")


def _local_file_uri_path(parsed_uri: ParseResult, uri: str) -> Path:
    if parsed_uri.netloc not in {"", "localhost"}:
        raise ValueError(f"file URI must not include a non-local authority: {uri}")
    return Path(unquote(parsed_uri.path))


def _svn_cat_to_file(uri: str, stdout_file: IO[bytes]) -> None:
    with tempfile.TemporaryFile() as stderr_file:
        try:
            completed = subprocess.run(
                ["svn", "cat", uri],
                check=True,
                stdout=stdout_file,
                stderr=stderr_file,
                timeout=DEFAULT_SVN_CAT_TIMEOUT_SECONDS,
            )
        except subprocess.CalledProcessError as exc:
            stderr_file.seek(0)
            stderr_text = read_text_bounded(
                stderr_file,
                max_bytes=DEFAULT_URI_READ_MAX_BYTES,
                errors="replace",
            ).strip()
            detail = stderr_text or f"svn cat returned exit status {exc.returncode}"
            raise ValueError(f"file URI could not be read: {uri}: {detail}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ValueError(f"file URI could not be read before timeout: {uri}") from exc
        if completed.returncode != 0:
            raise ValueError(f"file URI could not be read: {uri}: svn cat returned exit status {completed.returncode}")


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
    component_config: ReleaseConfig,
    state: CandidateReleaseState,
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
    staging_url = state.candidate_publication_uri.rstrip("/")
    source_artifact_url = f"{staging_url}/{state.source_artifact_name}"
    manifest_url = f"{staging_url}/{manifest_filename}"
    materialized_commit_sha: str | None = None
    if component_config.tags.final_mode == "detached-materialization-commit":
        materialized_commit_sha = rc_tag_target_commit
    source_reproducibility = (
        component_config.verification.source.reproducibility
        if component_config.verification is not None and component_config.verification.source is not None
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
        component_id=component_config.component.id,
        version=state.final_tag.removeprefix("v"),
        release_line=derive_specific_release_line(state.final_tag.removeprefix("v")),
        release_branch=state.resolved_release_branch,
        source_repository_url=source_repository_url,
        source_commit_sha=state.resolved_source_ref,
        source_date_epoch=state.source_date_epoch,
        rc_tag=state.rc_tag,
        final_tag=state.final_tag,
        final_tag_mode=component_config.tags.final_mode,
        provenance=provenance,
        trust_roots=trust_root_metadata(require_asf_profile(component_config).keys_url),
        draft_github_release=DraftGitHubRelease(
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
