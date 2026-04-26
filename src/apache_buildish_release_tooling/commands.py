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

"""Command handlers and orchestration helpers for the `buildish-release-tooling` CLI.

This module is the top-level workflow layer for the production CLI:

- `cli.py` parses the command line and dispatches here
- helper modules perform low-level Git, SVN, GitHub, GPG, and artifact work
- this module composes those helpers into release actions, manifests, and summaries

Keep protocol-specific details in the dedicated adapter modules when possible. The command layer
should mainly express release flow, validation order, and output contracts.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import tempfile
from argparse import Namespace
from collections.abc import Iterator
from collections.abc import Iterable
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apache_buildish_release_tooling.asf_svn import AsfSvnClient, url_join
from apache_buildish_release_tooling.config import (
    load_component_config,
    validate_release_target_base_urls,
)
from apache_buildish_release_tooling.dockerhub import parse_image_reference, publish_moving_aliases
from apache_buildish_release_tooling.email_templates import (
    render_announce_email,
    render_incubator_rc_vote_email,
    render_project_rc_vote_email,
    render_project_vote_result_email,
)
from apache_buildish_release_tooling.git_repo import GitRepository
from apache_buildish_release_tooling.git_materialization import (
    add_detached_worktree,
    default_materialized_ref_name,
    delete_remote_ref_best_effort,
    git_config_set,
    has_staged_changes,
    push_remote_ref,
    remove_worktree,
    validate_full_ref_name,
    validate_materialized_paths,
)
from apache_buildish_release_tooling.github_checks import (
    assert_ref_ready,
    fetch_check_runs_json,
    fetch_statuses_json,
    resolve_repository_slug,
)
from apache_buildish_release_tooling.github_git_refs import (
    create_annotated_tag_object,
    create_ref,
    update_ref,
)
from apache_buildish_release_tooling.github_release_selection import (
    SelectedGitHubRelease,
    asset_release_url,
    matching_draft_releases,
    plan_draft_release_sync,
    selected_github_release,
    upsert_draft_release,
)
from apache_buildish_release_tooling.github_releases import (
    delete_release,
    delete_release_asset,
    list_releases,
    release_by_tag,
    release_asset_ids_by_names,
    upload_release_assets,
    update_release,
)
from apache_buildish_release_tooling.gpg_signing import (
    detached_ascii_sign,
    import_private_key_from_secret,
    secret_key_fingerprint,
)
from apache_buildish_release_tooling.manifest import write_manifest
from apache_buildish_release_tooling.models import CommandContext, PrepareRcState, ReleaseVersionState
from apache_buildish_release_tooling.prepare_rc_state import resolve_prepare_rc_state
from apache_buildish_release_tooling.process import run_logged_command
from apache_buildish_release_tooling.rc_vote_manifest import build_rc_vote_manifest, read_uri_text
from apache_buildish_release_tooling.rc_vote_verification import (
    required_rc_vote_manifest_file_names,
    required_source_release_file_names,
    verified_staged_source_artifact_sha512,
    verify_staged_source_release_against_vote_manifest,
)
from apache_buildish_release_tooling.release_state import (
    compare_versions,
    derive_final_tag,
    derive_specific_release_line,
    derive_moving_tags,
    is_version_in_release_line,
    published_versions_from_entries,
    require_semantic_version,
    version_from_final_tag,
    versions_to_archive_for_line,
)
from apache_buildish_release_tooling.source_artifact import (
    checksum,
    create_from_git,
    sha512,
    write_checksum_file,
    write_sha512_file,
)
from apache_buildish_release_tooling.summary import SummaryWriter


@dataclass(frozen=True)
class MaterializedGitContent:
    """Resolved outcome from one detached RC content materialization run."""

    materialized_paths: list[str]
    materialized_commit_sha: str
    materialized_ref_name: str
    materialized_ref_mode: str


@dataclass(frozen=True)
class PreparedReleaseAssetUploads:
    """Generated checksum/signature sidecars and the final upload set for one release."""

    upload_paths: list[Path]
    checksum_algorithms: list[str]
    generated_checksum_lines: list[str]
    generated_checksum_paths: list[Path]
    generated_signature_paths: list[Path]
    gpg_fingerprint: str


@dataclass(frozen=True)
class RcVoteManifestArtifacts:
    """Built and signed authoritative RC vote-manifest artifacts."""

    manifest_payload: dict[str, Any]
    manifest_file_path: Path
    manifest_sha512: str
    manifest_sha512_path: Path
    manifest_signature_path: Path
    gpg_fingerprint: str


def _context(args: Namespace) -> CommandContext:
    config_path = args.component_config
    config = load_component_config(config_path)
    validate_release_target_base_urls(
        config,
        allow_non_production_release_targets=getattr(
            args, "allow_non_production_release_targets", False
        ),
    )
    return CommandContext(
        component_config=config,
        component_config_path=Path(config_path),
    )


def _manifest_path(component_id: str, action_name: str) -> Path:
    return Path(os.environ.get("MANIFEST_PATH", Path.cwd() / f"{component_id}-{action_name}.json"))


def _summary_writer() -> SummaryWriter:
    return SummaryWriter.from_environment()


def _summary_code(value: str) -> str:
    """Render one inline-code value for Markdown tables."""

    return f"`{value}`"


def _summary_optional_code(value: str | None) -> str:
    """Render one optional inline-code value for Markdown tables."""

    if value is None or value == "":
        return "<none>"
    return _summary_code(value)


def _artifact_output_dir(component_id: str) -> Path:
    return Path.cwd() / "build" / "release-artifacts" / component_id


def _append_github_outputs(entries: Mapping[str, Any]) -> None:
    """Append one or more step outputs when running inside GitHub Actions."""

    output_path_text = os.environ.get("GITHUB_OUTPUT", "").strip()
    if not output_path_text:
        return
    output_path = Path(output_path_text)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        for key, value in entries.items():
            rendered = "" if value is None else str(value)
            if "\n" not in rendered:
                handle.write(f"{key}={rendered}\n")
                continue
            delimiter = f"__BUILDISH_OUTPUT_{secrets.token_hex(8)}__"
            while delimiter in rendered:
                delimiter = f"__BUILDISH_OUTPUT_{secrets.token_hex(8)}__"
            handle.write(f"{key}<<{delimiter}\n{rendered}\n{delimiter}\n")


@contextmanager
def _temporary_build_dir(prefix: str) -> Iterator[Path]:
    """Yield one temporary build workspace rooted under `./build` and clean it up."""

    temp_parent = Path.cwd() / "build"
    temp_parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=f"{prefix}.", dir=temp_parent))
    try:
        yield temp_root
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def _resolve_prepare_rc_state_from_args(
    args: Namespace,
    context: CommandContext,
    repo: GitRepository,
) -> tuple[str, PrepareRcState]:
    """Resolve one RC workflow state from common CLI arguments."""

    version = args.version
    return (
        version,
        resolve_prepare_rc_state(
            repo,
            context.component_config,
            version,
            getattr(args, "source_sha", None),
            getattr(args, "rc_tag", None),
        ),
    )


def _materialize_rc_git_content(
    repo: GitRepository,
    *,
    state: PrepareRcState,
    repository_slug: str | None,
    materialized_paths: list[str],
    materialized_ref_name: str,
    run_command: str,
) -> MaterializedGitContent:
    """Create, commit, and push one detached materialization worktree result."""

    with _temporary_build_dir("materialize-rc-git-content") as temp_root:
        worktree_path = temp_root / "worktree"
        add_detached_worktree(repo, worktree_path, state.resolved_source_ref)
        try:
            worktree_repo = GitRepository(worktree_path)
            git_config_set(worktree_path, "user.name", "Buildish Release Tooling")
            git_config_set(worktree_path, "user.email", "buildish-release-tooling@example.invalid")
            run_logged_command(["sh", "-lc", run_command], cwd=worktree_path, capture_output=False)
            run_logged_command(
                ["git", "-C", str(worktree_path), "add", "--force", "--", *materialized_paths],
                cwd=worktree_path,
                capture_output=False,
            )
            if not has_staged_changes(worktree_path):
                raise ValueError(
                    "materialized content commit would be empty for "
                    f"{state.resolved_source_ref}: {', '.join(materialized_paths)}"
                )
            run_logged_command(
                [
                    "git",
                    "-C",
                    str(worktree_path),
                    "commit",
                    "-m",
                    f"Materialize RC Git content for {state.rc_tag}",
                ],
                cwd=worktree_path,
                capture_output=False,
            )
            materialized_commit_sha = worktree_repo.current_head_commit()
            materialized_ref_mode = push_remote_ref(
                worktree_repo,
                repository_slug=repository_slug,
                source_ref="HEAD",
                target_ref=materialized_ref_name,
                force=True,
            )
            return MaterializedGitContent(
                materialized_paths=materialized_paths,
                materialized_commit_sha=materialized_commit_sha,
                materialized_ref_name=materialized_ref_name,
                materialized_ref_mode=materialized_ref_mode,
            )
        finally:
            remove_worktree(repo, worktree_path)


def _resolve_materialization_tag_target(
    context: CommandContext,
    state: PrepareRcState,
    target_commit: str | None,
) -> tuple[str, str]:
    """Resolve the commit to tag and whether it comes from source or detached materialization."""

    if target_commit is not None:
        if (
            context.component_config.final_tag_mode != "detached-materialization-commit"
            and target_commit != state.resolved_source_ref
        ):
            raise ValueError("target_commit override is only valid for detached-materialization components")
        tag_target_origin = (
            "materialized-commit" if target_commit != state.resolved_source_ref else "source-commit"
        )
        return target_commit, tag_target_origin
    if context.component_config.final_tag_mode == "detached-materialization-commit":
        raise ValueError("detached-materialization components require --target-commit")
    return state.resolved_source_ref, "source-commit"


def _prepare_release_asset_uploads(
    asset_paths: list[Path],
    checksum_algorithms: list[str],
    *,
    sign: bool,
) -> PreparedReleaseAssetUploads:
    """Generate checksum/signature sidecars and the final GitHub Release upload set."""

    upload_paths = list(asset_paths)
    generated_checksum_lines: list[str] = []
    generated_checksum_paths: list[Path] = []
    for asset_path in asset_paths:
        for algorithm in checksum_algorithms:
            digest_value = checksum(asset_path, algorithm)
            checksum_path = write_checksum_file(asset_path, algorithm, digest_value)
            generated_checksum_lines.append(f"{algorithm}:{digest_value}  {asset_path.name}")
            generated_checksum_paths.append(checksum_path)
            upload_paths.append(checksum_path)

    generated_signature_paths: list[Path] = []
    gpg_fingerprint = ""
    if sign:
        generated_signature_paths, gpg_fingerprint = _sign_release_assets(asset_paths)
        upload_paths.extend(generated_signature_paths)

    return PreparedReleaseAssetUploads(
        upload_paths=upload_paths,
        checksum_algorithms=checksum_algorithms,
        generated_checksum_lines=generated_checksum_lines,
        generated_checksum_paths=generated_checksum_paths,
        generated_signature_paths=generated_signature_paths,
        gpg_fingerprint=gpg_fingerprint,
    )


def _sign_release_assets(asset_paths: list[Path]) -> tuple[list[Path], str]:
    """Generate detached ASCII-armored signatures for one set of release assets."""

    with _temporary_build_dir("attach-github-release-assets") as temp_root:
        gpg_home = temp_root / "gnupg"
        import_private_key_from_secret(gpg_home)
        gpg_fingerprint = secret_key_fingerprint(gpg_home)
        signature_paths: list[Path] = []
        for asset_path in asset_paths:
            signature_path = asset_path.with_name(f"{asset_path.name}.asc")
            detached_ascii_sign(gpg_home, asset_path, signature_path)
            signature_paths.append(signature_path)
        return signature_paths, gpg_fingerprint


def _build_rc_vote_manifest_artifacts(
    context: CommandContext,
    *,
    state: PrepareRcState,
    selected_release: SelectedGitHubRelease,
    rc_tag_target_commit: str,
    source_artifact_sha512: str,
    secondary_artifacts: list[dict[str, Any]],
    output_dir: Path,
) -> RcVoteManifestArtifacts:
    """Build and sign the authoritative RC vote-manifest artifacts."""

    manifest_file_path = output_dir / "rc-vote-manifest.json"
    with _temporary_build_dir("finalize-rc-vote-materials") as temp_root:
        gpg_home = temp_root / "gnupg"
        manifest_payload = build_rc_vote_manifest(
            component_config=context.component_config,
            state=state,
            repository_slug=selected_release.repository_slug,
            draft_release_tag=selected_release.require_release_tag(reference_tag=state.rc_tag),
            draft_release_url=selected_release.release_url,
            rc_tag_target_commit=rc_tag_target_commit,
            source_artifact_sha512=source_artifact_sha512,
            secondary_artifacts=secondary_artifacts,
        )
        write_manifest(manifest_file_path, manifest_payload)
        manifest_sha512 = sha512(manifest_file_path)
        manifest_sha512_path = write_sha512_file(manifest_file_path, manifest_sha512)
        import_private_key_from_secret(gpg_home)
        gpg_fingerprint = secret_key_fingerprint(gpg_home)
        manifest_signature_path = manifest_file_path.with_name(f"{manifest_file_path.name}.asc")
        detached_ascii_sign(gpg_home, manifest_file_path, manifest_signature_path)
        return RcVoteManifestArtifacts(
            manifest_payload=manifest_payload,
            manifest_file_path=manifest_file_path,
            manifest_sha512=manifest_sha512,
            manifest_sha512_path=manifest_sha512_path,
            manifest_signature_path=manifest_signature_path,
            gpg_fingerprint=gpg_fingerprint,
        )


def _stage_rc_vote_manifest_and_mirror(
    context: CommandContext,
    *,
    state: PrepareRcState,
    version: str,
    selected_release: SelectedGitHubRelease,
    artifacts: RcVoteManifestArtifacts,
) -> str:
    """Stage authoritative RC vote-manifest artifacts in SVN and mirror them to GitHub Releases."""

    svn_client = AsfSvnClient.from_environment()
    staging_url = state.staging_url.rstrip("/")
    if not svn_client.path_exists(staging_url):
        raise ValueError(f"RC staging directory does not exist: {staging_url}")
    with _temporary_build_dir("finalize-rc-vote-materials-svn") as temp_root:
        staging_wc = temp_root / "staging-wc"
        svn_client.checkout_url(staging_url, staging_wc)
        svn_client.working_copy_put_file(
            staging_wc,
            artifacts.manifest_file_path,
            artifacts.manifest_file_path.name,
        )
        svn_client.working_copy_put_file(
            staging_wc,
            artifacts.manifest_sha512_path,
            artifacts.manifest_sha512_path.name,
        )
        svn_client.working_copy_put_file(
            staging_wc,
            artifacts.manifest_signature_path,
            artifacts.manifest_signature_path.name,
        )
        svn_client.commit_working_copy(
            staging_wc,
            f"stage RC vote manifest for {context.component_config.component_id} {version}",
        )
    upload_release_assets(
        selected_release.repository_slug,
        tag_name=selected_release.require_release_tag(reference_tag=state.rc_tag),
        asset_paths=[
            artifacts.manifest_file_path,
            artifacts.manifest_sha512_path,
            artifacts.manifest_signature_path,
        ],
        clobber=True,
    )
    return f"{staging_url}/{artifacts.manifest_file_path.name}"


def _rc_vote_manifest_asset_names(artifacts: RcVoteManifestArtifacts) -> list[str]:
    """Return the authoritative RC vote-manifest asset names in mirror order."""

    return [
        artifacts.manifest_file_path.name,
        artifacts.manifest_sha512_path.name,
        artifacts.manifest_signature_path.name,
    ]


def _append_finalize_rc_vote_materials_summary(
    summary: SummaryWriter,
    *,
    context: CommandContext,
    version: str,
    state: PrepareRcState,
    selected_release: SelectedGitHubRelease,
    rc_tag_target_commit: str,
    source_artifact_sha512: str,
    source_signature_text: str,
    secondary_artifacts: list[dict[str, Any]],
    authoritative_manifest_url: str,
    artifacts: RcVoteManifestArtifacts,
    project_vote_email: Any,
    incubator_vote_email: Any | None,
) -> None:
    """Append the full human-facing RC vote-materials summary for one run."""

    summary.append_heading(f"Finalize RC vote materials for version {version}")
    summary.append_key_value_table(
        "Technical details",
        [
            ("Component", _summary_code(context.component_config.component_id)),
            ("Version", _summary_code(version)),
            ("Release branch", _summary_code(state.resolved_release_branch)),
            ("Source commit", _summary_code(state.resolved_source_ref)),
            ("RC tag", _summary_code(state.rc_tag)),
            ("Final tag", _summary_code(state.final_tag)),
            ("RC tag target commit", _summary_code(rc_tag_target_commit)),
            ("ASF SVN staging URL", _summary_code(f"{state.staging_url.rstrip('/')}/")),
            ("Authoritative manifest URL", _summary_code(authoritative_manifest_url)),
            ("Draft GitHub Release URL", _summary_optional_code(selected_release.release_url)),
            ("Secondary artifact count", str(len(secondary_artifacts))),
            ("GPG signing key", _summary_code(artifacts.gpg_fingerprint)),
        ],
    )
    summary.append_sha512_block(state.source_artifact_name, source_artifact_sha512)
    summary.append_signature_text_block(state.source_artifact_name, source_signature_text)
    summary.append_sha512_block(artifacts.manifest_file_path.name, artifacts.manifest_sha512)
    summary.append_signature_block(
        artifacts.manifest_file_path.name,
        artifacts.manifest_signature_path,
    )
    summary.append_bullet_list(
        "Draft GitHub Release mirror assets",
        [_summary_code(asset_name) for asset_name in _rc_vote_manifest_asset_names(artifacts)],
    )
    summary.append_json_block("RC vote manifest", artifacts.manifest_payload)
    summary.append_plaintext_block(
        "Outcome",
        "The RC vote manifest was signed, staged into ASF dev/dist, and mirrored to the draft "
        "GitHub Release. The email proposals below are ready for human review and sending.",
    )
    summary.append_plaintext_block(
        "Verification trust roots",
        f"ASF KEYS: {artifacts.manifest_payload['trust_roots']['asf_keys']['uri']}\n"
        "Buildish verification guide: "
        f"{context.component_config.release_verification_guide_url}",
    )
    summary.append_email_template_blocks(
        "Project vote",
        project_vote_email.subject,
        project_vote_email.body,
    )
    if incubator_vote_email is not None:
        summary.append_email_template_blocks(
            "Incubator vote request",
            incubator_vote_email.subject,
            incubator_vote_email.body,
        )


def _matching_dev_rc_entries(entries: Iterable[str], version: str) -> list[str]:
    """Return sorted RC directory entries for one exact version from `svn list` output."""

    pattern = re.compile(rf"{re.escape(version)}-rc[0-9]+")
    return sorted(
        entry.rstrip("/")
        for entry in entries
        if entry.endswith("/") and pattern.fullmatch(entry.rstrip("/")) is not None
    )


def _load_secondary_artifacts(manifest_paths: Iterable[str]) -> list[dict[str, Any]]:
    """Load generic secondary-artifact entries from one or more JSON manifest files."""

    secondary_artifacts: list[dict[str, Any]] = []
    for manifest_argument in manifest_paths:
        manifest_path = Path(manifest_argument)
        if not manifest_path.is_file():
            raise ValueError(f"secondary artifact manifest does not exist: {manifest_path}")
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"secondary artifact manifest must contain a JSON object: {manifest_path}")
        artifact_entries = payload.get("secondary_artifacts")
        if not isinstance(artifact_entries, list):
            raise ValueError(
                f"secondary artifact manifest must contain a 'secondary_artifacts' list: {manifest_path}"
            )
        for artifact_entry in artifact_entries:
            if not isinstance(artifact_entry, dict):
                raise ValueError(
                    f"secondary artifact entries must be JSON objects: {manifest_path}"
                )
            secondary_artifacts.append(dict(artifact_entry))
    return secondary_artifacts


def _draft_release_body(context: CommandContext, state: PrepareRcState) -> str:
    """Render the body used for the draft GitHub Release placeholder."""

    return "\n".join(
        [
            f"Draft GitHub Release placeholder for {context.component_config.vote_release_name} {state.final_tag.removeprefix('v')}.",
            "",
            f"RC tag: {state.rc_tag}",
            f"Final tag: {state.final_tag}",
            f"Resolved source ref: {state.resolved_source_ref}",
            f"ASF SVN staging URL: {state.staging_url}",
            f"Final tag mode: {context.component_config.final_tag_mode}",
            "",
            "This draft release is convenience metadata only and must remain unpublished until the ASF vote passes.",
        ]
    )


def _published_release_versions(context: CommandContext) -> list[str]:
    svn_client = AsfSvnClient.from_environment()
    release_base_url = context.component_config.asf_dist_release_base.rstrip("/")
    if not svn_client.path_exists(release_base_url):
        return []
    return published_versions_from_entries(svn_client.list_entries(release_base_url))


def _resolve_release_version_state(
    context: CommandContext,
    repo: GitRepository,
    version: str,
    expected_selected_rc_tag: str | None = None,
) -> tuple[str, ReleaseVersionState]:
    version = require_semantic_version(version)
    selected_release = selected_github_release(
        repo=repo,
        version=version,
        expected_selected_rc_tag=expected_selected_rc_tag,
    )
    release_line = derive_specific_release_line(version)
    published_versions = _published_release_versions(context)
    return (
        release_line,
        ReleaseVersionState(
            selected_rc_tag=selected_release.selected_rc_tag,
            final_tag=derive_final_tag(version),
            archive_versions=versions_to_archive_for_line(
                release_line, version, published_versions
            ),
            release_url=f"{context.component_config.asf_dist_release_base.rstrip('/')}/{version}/",
            moving_tags=derive_moving_tags(
                version,
                context.component_config.secondary_targets,
                context.component_config.moving_tags_enabled,
                context.component_config.latest_tag_enabled,
            ),
        ),
    )


def _latest_rc_directory_name(version: str, latest_rc_tag: str) -> str:
    expected_prefix = f"v{version}-rc"
    if not latest_rc_tag.startswith(expected_prefix):
        raise ValueError(f"latest RC tag does not match version {version}: {latest_rc_tag}")
    return latest_rc_tag.removeprefix("v")


def _release_name(context: CommandContext, version: str) -> str:
    return f"{context.component_config.vote_release_name} {version}"


def _repository_slug_or_none(repo: GitRepository) -> str | None:
    try:
        return resolve_repository_slug(repo.path)
    except ValueError:
        return None


def _asset_paths(arguments: Iterable[str]) -> list[Path]:
    """Resolve asset arguments to existing files."""

    asset_paths: list[Path] = []
    for argument in arguments:
        asset_path = Path(argument)
        if not asset_path.is_file():
            raise ValueError(f"asset file does not exist: {asset_path}")
        asset_paths.append(asset_path)
    if not asset_paths:
        raise ValueError("at least one asset file is required")
    return asset_paths


def _deduplicated_checksum_algorithms(algorithms: Iterable[str]) -> list[str]:
    """Return checksum algorithms in first-seen order without duplicates."""

    deduplicated: list[str] = []
    for algorithm in algorithms:
        normalized_algorithm = algorithm.lower()
        if normalized_algorithm not in deduplicated:
            deduplicated.append(normalized_algorithm)
    return deduplicated


def _assert_unique_upload_asset_names(asset_paths: Iterable[Path]) -> None:
    """Reject upload plans that would collide on GitHub asset basenames."""

    seen_names: set[str] = set()
    for asset_path in asset_paths:
        if asset_path.name in seen_names:
            raise ValueError(f"duplicate GitHub Release asset name: {asset_path.name}")
        seen_names.add(asset_path.name)


def _create_or_reuse_annotated_tag(
    *,
    repo: GitRepository,
    repository_slug: str | None,
    tag_name: str,
    target_commit: str,
    message: str,
    allow_update: bool,
    reuse_if_same_target: bool = True,
) -> tuple[str, dict[str, object]]:
    """Create, update, or reuse an annotated Git tag for one target commit."""

    if repo.tag_exists(tag_name):
        existing_target_commit = repo.resolve_commit(tag_name)
        if existing_target_commit == target_commit:
            if not reuse_if_same_target:
                raise ValueError(f"tag already exists: {tag_name}")
            return "already-present", {"ref": f"refs/tags/{tag_name}"}
        if not allow_update:
            raise ValueError(f"tag already exists with a different target: {tag_name}")
        if repository_slug is None:
            repo.force_create_annotated_tag(tag_name, target_commit, message)
            return "local-git-force-update", {"ref": f"refs/tags/{tag_name}"}
        created_tag_object = create_annotated_tag_object(
            repository_slug,
            tag_name=tag_name,
            target_commit=target_commit,
            message=message,
        )
        tag_object_sha = created_tag_object.get("sha")
        if not isinstance(tag_object_sha, str) or not tag_object_sha:
            raise ValueError("GitHub tag-object creation response did not include a tag object sha")
        updated_ref = update_ref(
            repository_slug,
            ref_name=f"refs/tags/{tag_name}",
            target_sha=tag_object_sha,
            force=True,
        )
        return "github-api-force-update", updated_ref

    if repository_slug is None:
        repo.create_annotated_tag(tag_name, target_commit, message)
        return "local-git", {"ref": f"refs/tags/{tag_name}"}
    created_tag_object = create_annotated_tag_object(
        repository_slug,
        tag_name=tag_name,
        target_commit=target_commit,
        message=message,
    )
    tag_object_sha = created_tag_object.get("sha")
    if not isinstance(tag_object_sha, str) or not tag_object_sha:
        raise ValueError("GitHub tag-object creation response did not include a tag object sha")
    created_ref = create_ref(
        repository_slug,
        ref_name=f"refs/tags/{tag_name}",
        target_sha=tag_object_sha,
    )
    return "github-api", created_ref


def _final_version_for_commit(repo: GitRepository, target_commit: str) -> str | None:
    """Resolve the immutable final release version whose tag points at one commit."""

    matching_versions: list[str] = []
    for tag_name in repo.list_tags():
        version = version_from_final_tag(tag_name)
        if version is None:
            continue
        if repo.resolve_commit(tag_name) == target_commit:
            matching_versions.append(version)
    if not matching_versions:
        return None
    matching_versions.sort(key=lambda item: tuple(int(piece) for piece in item.split(".")))
    return matching_versions[-1]


def _moving_tag_scope_release_line(alias: str) -> str | None:
    """Resolve the release-line scope encoded in one moving Git tag alias."""

    normalized_alias = alias.removeprefix("v")
    if normalized_alias == "latest":
        return None
    parts = normalized_alias.split(".")
    if len(parts) == 1 and parts[0].isdigit():
        return f"{parts[0]}.x"
    if len(parts) == 2 and all(part.isdigit() for part in parts):
        return f"{parts[0]}.{parts[1]}.x"
    raise ValueError(f"unsupported moving alias: {alias}")


def _should_move_alias(alias: str, candidate_version: str, current_version: str | None) -> bool:
    """Return whether a moving alias should advance to one candidate final version."""

    if current_version is None:
        return True
    scope_release_line = _moving_tag_scope_release_line(alias)
    if scope_release_line is None:
        return compare_versions(candidate_version, current_version) == 1
    if not is_version_in_release_line(scope_release_line, candidate_version):
        raise ValueError(f"candidate version {candidate_version} is outside alias scope {alias}")
    if not is_version_in_release_line(scope_release_line, current_version):
        raise ValueError(f"current alias target {current_version} is outside alias scope {alias}")
    return compare_versions(candidate_version, current_version) == 1


def _rc_tag_message(context: CommandContext, version: str, rc_tag: str) -> str:
    """Render the standard annotated-message text for one RC tag."""

    return (
        f"Release candidate {context.component_config.vote_release_name} "
        f"{version}-rc{rc_tag.removeprefix(f'v{version}-rc')}"
    )


def _rc_number_from_tag(version: str, rc_tag: str) -> int:
    """Parse the numeric RC suffix from one exact RC tag string."""

    expected_prefix = f"v{version}-rc"
    if not rc_tag.startswith(expected_prefix):
        raise ValueError(f"RC tag does not match version {version}: {rc_tag}")
    rc_suffix = rc_tag.removeprefix(expected_prefix)
    if not rc_suffix.isdigit():
        raise ValueError(f"RC tag does not end in a numeric suffix: {rc_tag}")
    return int(rc_suffix)


def run_create_release_branch(args: Namespace) -> Path:
    """Run the `create-release-branch` command."""

    context = _context(args)
    release_line = args.release_line
    source_ref = args.source_ref
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?\.x", release_line):
        raise ValueError("release_line must look like 1.x or 1.2.x")
    repo = GitRepository.from_current_worktree()
    manifest_path = _manifest_path(context.component_config.component_id, "create-release-branch")
    summary = _summary_writer()
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
    summary = _summary_writer()
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


def run_prepare_rc(args: Namespace) -> Path:
    """Resolve RC state and emit the summary/manifests used by the draft workflow."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version = args.version
    source_sha = args.source_sha
    state = resolve_prepare_rc_state(repo, context.component_config, version, source_sha)
    manifest_path = _manifest_path(context.component_config.component_id, "prepare-rc")
    summary = _summary_writer()
    manifest_entries = {
        "component": context.component_config.component_id,
        "action": "prepare-rc",
        "version": version,
        "resolved_source_ref": state.resolved_source_ref,
        "resolved_release_branch": state.resolved_release_branch,
        "rc_number": str(state.rc_number),
        "rc_tag": state.rc_tag,
        "final_tag": state.final_tag,
        "source_artifact_name": state.source_artifact_name,
        "source_artifact_root_name": state.source_artifact_root_name,
        "source_artifact_prefix_path": state.source_artifact_prefix_path,
        "staging_url": state.staging_url,
        "cleanup_existing_rc_staging": "true",
        "draft_release_action": "recreate",
        "final_tag_mode": context.component_config.final_tag_mode,
    }
    write_manifest(manifest_path, manifest_entries)
    _append_github_outputs(
        {
            "rc_tag": manifest_entries["rc_tag"],
            "resolved_source_ref": manifest_entries["resolved_source_ref"],
        }
    )
    summary.append_heading("Prepare RC")
    summary.append_plaintext_block("Resolved source", state.resolved_source_ref)
    summary.append_plaintext_block("RC identity", state.rc_tag)
    summary.append_plaintext_block(
        "ASF SVN staging cleanup",
        f"Delete and recreate {state.staging_url} before staging the new RC.",
    )
    summary.append_plaintext_block(
        "Email templates",
        "Project vote and other release email templates are emitted by the later "
        "`finalize-rc-vote-materials`, `release-version`, and `finalize-draft-github-release` steps.",
    )
    return manifest_path


def run_cleanup_dev_svn_rcs(args: Namespace) -> Path:
    """Delete pre-existing RC staging directories for one exact version from ASF SVN dev dist."""

    context = _context(args)
    version = args.version
    svn_client = AsfSvnClient.from_environment()
    dev_base_url = context.component_config.asf_dist_dev_base.rstrip("/")
    if svn_client.path_exists(dev_base_url):
        deleted_rc_entries = _matching_dev_rc_entries(svn_client.list_entries(dev_base_url), version)
    else:
        deleted_rc_entries = []
    for entry in deleted_rc_entries:
        svn_client.delete_url(
            url_join(dev_base_url, entry),
            f"delete pre-existing RC staging for {context.component_config.component_id} {version}",
        )
    manifest_path = _manifest_path(context.component_config.component_id, "cleanup-dev-svn-rcs")
    summary = _summary_writer()
    write_manifest(
        manifest_path,
        {
            "component": context.component_config.component_id,
            "action": "cleanup-dev-svn-rcs",
            "version": version,
            "dev_base_url": f"{dev_base_url}/",
            "deleted_rc_directories": ",".join(deleted_rc_entries),
        },
    )
    summary.append_heading(f"Cleanup ASF SVN dev/dist for version {version}")
    summary.append_key_value_table(
        "Technical details",
        [
            ("Component", _summary_code(context.component_config.component_id)),
            ("Version", _summary_code(version)),
            ("ASF SVN dev base", _summary_code(f"{dev_base_url}/")),
            ("Deleted RC directory count", str(len(deleted_rc_entries))),
        ],
    )
    summary.append_bullet_list(
        "Deleted RC directories",
        [
            _summary_code(f"{entry}/") + f" from {_summary_code(url_join(dev_base_url, entry) + '/')}"
            for entry in deleted_rc_entries
        ],
    )
    summary.append_plaintext_block(
        "Outcome",
        (
            f"Deleted {len(deleted_rc_entries)} pre-existing RC staging directories for exact version {version}."
            if deleted_rc_entries
            else f"No pre-existing RC staging directories existed for exact version {version}."
        ),
    )
    return manifest_path


def run_create_source_artifact(args: Namespace) -> Path:
    """Build an unsigned reproducible source artifact from Git."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version = args.version
    source_sha = args.source_sha
    state = resolve_prepare_rc_state(repo, context.component_config, version, source_sha)
    output_dir = _artifact_output_dir(context.component_config.component_id)
    artifact_path = output_dir / state.source_artifact_name
    create_from_git(repo.path, state.resolved_source_ref, state.source_artifact_prefix_path, artifact_path)
    artifact_sha512 = sha512(artifact_path)
    manifest_path = _manifest_path(context.component_config.component_id, "create-source-artifact")
    summary = _summary_writer()
    write_manifest(
        manifest_path,
        {
            "component": context.component_config.component_id,
            "action": "create-source-artifact",
            "version": version,
            "resolved_source_ref": state.resolved_source_ref,
            "source_artifact_name": state.source_artifact_name,
            "source_artifact_path": str(artifact_path),
            "source_artifact_sha512": artifact_sha512,
        },
    )
    summary.append_heading("Source Artifact")
    summary.append_plaintext_block("Source artifact path", str(artifact_path))
    summary.append_plaintext_block("Source artifact ref", state.resolved_source_ref)
    summary.append_sha512_block(state.source_artifact_name, artifact_sha512)
    return manifest_path


def run_build_source_rc(args: Namespace) -> Path:
    """Build, sign, and stage a source RC into ASF SVN."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version, state = _resolve_prepare_rc_state_from_args(args, context, repo)
    output_dir = _artifact_output_dir(context.component_config.component_id)
    artifact_path = output_dir / state.source_artifact_name
    with _temporary_build_dir("build-source-rc") as temp_root:
        gpg_home = temp_root / "gnupg"
        staging_wc = temp_root / "staging-wc"
        create_from_git(repo.path, state.resolved_source_ref, state.source_artifact_prefix_path, artifact_path)
        artifact_sha512 = sha512(artifact_path)
        sha512_path = write_sha512_file(artifact_path, artifact_sha512)
        import_private_key_from_secret(gpg_home)
        asc_path = artifact_path.with_name(f"{artifact_path.name}.asc")
        detached_ascii_sign(gpg_home, artifact_path, asc_path)

        svn_client = AsfSvnClient.from_environment()
        staging_url = state.staging_url.rstrip("/")
        if svn_client.path_exists(staging_url):
            svn_client.delete_url(
                staging_url,
                f"delete existing RC staging for {context.component_config.component_id} {version}",
            )
        svn_client.mkdir_url(
            staging_url,
            f"create RC staging for {context.component_config.component_id} {version}",
        )
        svn_client.checkout_url(staging_url, staging_wc)
        svn_client.working_copy_put_file(staging_wc, artifact_path, artifact_path.name)
        svn_client.working_copy_put_file(staging_wc, sha512_path, sha512_path.name)
        svn_client.working_copy_put_file(staging_wc, asc_path, asc_path.name)
        svn_client.commit_working_copy(
            staging_wc,
            f"stage RC source artifacts for {context.component_config.component_id} {version}",
        )
        manifest_path = _manifest_path(context.component_config.component_id, "build-source-rc")
        summary = _summary_writer()
        write_manifest(
            manifest_path,
            {
                "component": context.component_config.component_id,
                "action": "build-source-rc",
                "version": version,
                "resolved_source_ref": state.resolved_source_ref,
                "rc_tag": state.rc_tag,
                "source_artifact_name": state.source_artifact_name,
                "source_artifact_path": str(artifact_path),
                "source_artifact_sha512": artifact_sha512,
                "source_artifact_sha512_path": str(sha512_path),
                "source_artifact_asc_path": str(asc_path),
                "staging_url": f"{staging_url}/",
            },
        )
        summary.append_heading("Build Source RC")
        summary.append_plaintext_block("Source artifact path", str(artifact_path))
        summary.append_plaintext_block("Source artifact ref", state.resolved_source_ref)
        summary.append_plaintext_block("ASF SVN staged RC URL", f"{staging_url}/")
        summary.append_sha512_block(state.source_artifact_name, artifact_sha512)
        summary.append_signature_block(state.source_artifact_name, asc_path)
        return manifest_path


def run_sync_draft_github_release(args: Namespace) -> Path:
    """Create or recreate the draft GitHub Release placeholder for an exact version."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version, state = _resolve_prepare_rc_state_from_args(args, context, repo)
    repository_slug = resolve_repository_slug(repo.path)
    release_name = _release_name(context, version)
    existing_releases = list_releases(repository_slug)
    matching_release_payloads = matching_draft_releases(
        existing_releases,
        version=version,
        tag_names=[state.final_tag, state.rc_tag],
        release_name=release_name,
    )
    sync_plan = plan_draft_release_sync(
        matching_release_payloads,
        version=version,
        state=state,
    )
    deleted_release_ids = sync_plan.deleted_release_ids
    for release_id in deleted_release_ids:
        delete_release(repository_slug, release_id)
    desired_release_body = _draft_release_body(context, state)
    created_release, sync_mode = upsert_draft_release(
        repository_slug,
        state=state,
        release_name=release_name,
        desired_release_body=desired_release_body,
        same_rc_release=sync_plan.same_rc_release,
    )
    created_release_id = created_release.get("id")
    created_release_tag = created_release.get("tag_name")
    created_release_title = created_release.get("name")
    created_release_url = asset_release_url(created_release)
    manifest_path = _manifest_path(context.component_config.component_id, "sync-draft-github-release")
    summary = _summary_writer()
    write_manifest(
        manifest_path,
        {
            "component": context.component_config.component_id,
            "action": "sync-draft-github-release",
            "version": version,
            "repository_slug": repository_slug,
            "resolved_source_ref": state.resolved_source_ref,
            "rc_tag": state.rc_tag,
            "final_tag": state.final_tag,
            "staging_url": state.staging_url,
            "deleted_release_ids": ",".join(str(item) for item in deleted_release_ids),
            "release_id": str(created_release_id or ""),
            "release_tag": str(created_release_tag or ""),
            "release_name": str(created_release_title or ""),
            "release_url": str(created_release_url),
            "sync_mode": sync_mode,
        },
    )
    summary.append_heading("Sync draft GitHub Release")
    summary.append_plaintext_block("GitHub repository", repository_slug)
    summary.append_plaintext_block(
        "Deleted draft release IDs",
        "\n".join(str(item) for item in deleted_release_ids) if deleted_release_ids else "<none>",
    )
    summary.append_plaintext_block(
        "Created draft release",
        "\n".join(
            [
                f"id: {created_release_id}",
                f"name: {created_release_title}",
                f"tag: {created_release_tag}",
                f"url: {created_release_url}",
                f"mode: {sync_mode}",
            ]
        ),
    )
    return manifest_path


def run_publish_source_release_svn(args: Namespace) -> Path:
    """Promote the latest staged source RC from ASF `dist/dev` into `dist/release`."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version = args.version
    selected_release = selected_github_release(
        repo=repo,
        version=version,
        expected_selected_rc_tag=getattr(args, "selected_rc_tag", None),
    )
    rc_directory_name = _latest_rc_directory_name(version, selected_release.selected_rc_tag)
    source_url = url_join(context.component_config.asf_dist_dev_base.rstrip("/"), rc_directory_name)
    target_url = url_join(context.component_config.asf_dist_release_base.rstrip("/"), version)
    svn_client = AsfSvnClient.from_environment()
    if not svn_client.path_exists(source_url):
        raise ValueError(f"RC staging directory does not exist: {source_url}")
    staged_entries = sorted(svn_client.list_entries(source_url, recursive=True))
    required_source_release_files = required_source_release_file_names(
        context.component_config.source_artifact_prefix,
        version,
    )
    required_file_names = [
        *required_source_release_files,
        *required_rc_vote_manifest_file_names(),
    ]
    missing_required_files = [
        file_name for file_name in required_file_names if file_name not in staged_entries
    ]
    if missing_required_files:
        raise ValueError(
            "RC staging directory is missing required staged release files: "
            + ", ".join(missing_required_files)
        )
    verified_source_artifact_sha512 = verify_staged_source_release_against_vote_manifest(
        context,
        repository_slug=selected_release.repository_slug,
        release_payload=selected_release.release_payload,
        source_url=source_url,
        version=version,
        selected_rc_tag=selected_release.selected_rc_tag,
        expected_source_artifact_name=required_source_release_files[0],
    )
    if svn_client.path_exists(target_url):
        target_entries = sorted(svn_client.list_entries(target_url, recursive=True))
        if staged_entries != target_entries:
            raise ValueError(
                f"final release directory already exists with different contents: {target_url}"
            )
        publish_mode = "already-present"
    else:
        svn_client.copy_url(
            source_url,
            target_url,
            f"publish source release for {context.component_config.component_id} {version}",
        )
        publish_mode = "copied"
    manifest_path = _manifest_path(context.component_config.component_id, "publish-source-release-svn")
    summary = _summary_writer()
    write_manifest(
        manifest_path,
        {
            "component": context.component_config.component_id,
            "action": "publish-source-release-svn",
            "version": version,
            "selected_rc_tag": selected_release.selected_rc_tag,
            "source_url": f"{source_url}/",
            "target_url": f"{target_url}/",
            "verified_source_artifact_sha512": verified_source_artifact_sha512,
            "publish_mode": publish_mode,
        },
    )
    summary.append_heading("Publish source release SVN")
    summary.append_plaintext_block("Selected RC", selected_release.selected_rc_tag)
    summary.append_plaintext_block("Promoted source URL", f"{source_url}/")
    summary.append_plaintext_block("Published release URL", f"{target_url}/")
    summary.append_sha512_block(
        required_source_release_files[0],
        verified_source_artifact_sha512,
    )
    summary.append_plaintext_block("Publish mode", publish_mode)
    return manifest_path


def run_prune_older_line_releases(args: Namespace) -> Path:
    """Delete older same-line releases from ASF `dist/release`."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version = args.version
    release_line, state = _resolve_release_version_state(context, repo, version)
    release_base_url = context.component_config.asf_dist_release_base.rstrip("/")
    svn_client = AsfSvnClient.from_environment()
    for archived_version in state.archive_versions:
        svn_client.delete_url(
            url_join(release_base_url, archived_version),
            f"prune older same-line release for {context.component_config.component_id} {archived_version}",
        )
    manifest_path = _manifest_path(context.component_config.component_id, "prune-older-line-releases")
    summary = _summary_writer()
    write_manifest(
        manifest_path,
        {
            "component": context.component_config.component_id,
            "action": "prune-older-line-releases",
            "version": version,
            "release_line": release_line,
            "pruned_versions": ",".join(state.archive_versions),
            "release_base_url": f"{release_base_url}/",
        },
    )
    summary.append_heading("Prune older line releases")
    summary.append_plaintext_block("Release line", release_line)
    summary.append_plaintext_block("ASF SVN release base", f"{release_base_url}/")
    summary.append_plaintext_block(
        "Pruned versions",
        "\n".join(state.archive_versions) if state.archive_versions else "<none>",
    )
    return manifest_path


def run_materialize_rc_git_content(args: Namespace) -> Path:
    """Create one detached RC materialization commit from release-only generated Git paths."""

    context = _context(args)
    if context.component_config.final_tag_mode != "detached-materialization-commit":
        raise ValueError(
            "materialize-rc-git-content is valid only for detached-materialization components"
        )
    repo = GitRepository.from_current_worktree()
    version, state = _resolve_prepare_rc_state_from_args(args, context, repo)
    materialized_paths = validate_materialized_paths(getattr(args, "materialized_paths", []))
    materialized_ref_name = getattr(args, "materialized_ref_name", None)
    if materialized_ref_name is not None:
        materialized_ref_name = validate_full_ref_name(materialized_ref_name)
    else:
        materialized_ref_name = default_materialized_ref_name(state)
    run_command = getattr(args, "run_command", "").strip()
    if not run_command:
        raise ValueError("--run-command must not be empty")

    materialized_content = _materialize_rc_git_content(
        repo,
        state=state,
        repository_slug=_repository_slug_or_none(repo),
        materialized_paths=materialized_paths,
        materialized_ref_name=materialized_ref_name,
        run_command=run_command,
    )
    manifest_path = _manifest_path(context.component_config.component_id, "materialize-rc-git-content")
    summary = _summary_writer()
    manifest_entries = {
        "component": context.component_config.component_id,
        "action": "materialize-rc-git-content",
        "version": version,
        "resolved_source_ref": state.resolved_source_ref,
        "rc_tag": state.rc_tag,
        "materialized_paths": ",".join(materialized_content.materialized_paths),
        "materialized_commit_sha": materialized_content.materialized_commit_sha,
        "materialized_ref_name": materialized_content.materialized_ref_name,
        "materialized_ref_mode": materialized_content.materialized_ref_mode,
    }
    write_manifest(manifest_path, manifest_entries)
    _append_github_outputs(
        {
            "materialized_commit_sha": materialized_content.materialized_commit_sha,
            "materialized_ref_name": materialized_content.materialized_ref_name,
        }
    )
    summary.append_heading("Materialize RC Git content")
    summary.append_plaintext_block("Resolved source ref", state.resolved_source_ref)
    summary.append_plaintext_block("RC tag", state.rc_tag)
    summary.append_plaintext_block(
        "Materialized paths",
        "\n".join(materialized_content.materialized_paths),
    )
    summary.append_plaintext_block("Materialized commit", materialized_content.materialized_commit_sha)
    summary.append_plaintext_block("Materialized ref", materialized_content.materialized_ref_name)
    summary.append_plaintext_block("Materialized ref mode", materialized_content.materialized_ref_mode)
    return manifest_path


def run_create_rc_materialization_tag(args: Namespace) -> Path:
    """Create the RC tag on either the source commit or one detached materialization commit."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version, state = _resolve_prepare_rc_state_from_args(args, context, repo)
    cleanup_materialized_ref_name = getattr(args, "cleanup_materialized_ref_name", None)
    if cleanup_materialized_ref_name is not None:
        cleanup_materialized_ref_name = validate_full_ref_name(cleanup_materialized_ref_name)
    target_commit, tag_target_origin = _resolve_materialization_tag_target(
        context,
        state,
        args.target_commit,
    )
    repository_slug = _repository_slug_or_none(repo)
    cleanup_materialized_ref_mode = "not-requested"
    try:
        tag_creation_mode, created_ref = _create_or_reuse_annotated_tag(
            repo=repo,
            repository_slug=repository_slug,
            tag_name=state.rc_tag,
            target_commit=target_commit,
            message=_rc_tag_message(context, version, state.rc_tag),
            allow_update=False,
            reuse_if_same_target=False,
        )
    finally:
        if cleanup_materialized_ref_name is not None:
            cleanup_materialized_ref_mode = delete_remote_ref_best_effort(
                repo,
                repository_slug=repository_slug,
                ref_name=cleanup_materialized_ref_name,
            )
    manifest_path = _manifest_path(context.component_config.component_id, "create-rc-materialization-tag")
    summary = _summary_writer()
    write_manifest(
        manifest_path,
        {
            "component": context.component_config.component_id,
            "action": "create-rc-materialization-tag",
            "version": version,
            "resolved_source_ref": state.resolved_source_ref,
            "rc_tag": state.rc_tag,
            "target_commit": target_commit,
            "tag_target_origin": tag_target_origin,
            "cleanup_materialized_ref_name": cleanup_materialized_ref_name or "",
            "cleanup_materialized_ref_mode": cleanup_materialized_ref_mode,
            "tag_creation_mode": tag_creation_mode,
            "created_ref": str(created_ref.get("ref") or ""),
        },
    )
    summary.append_heading("Create RC tag")
    summary.append_plaintext_block("Resolved source ref", state.resolved_source_ref)
    summary.append_plaintext_block("RC tag", state.rc_tag)
    summary.append_plaintext_block("Target commit", target_commit)
    summary.append_plaintext_block("Tag target origin", tag_target_origin)
    summary.append_plaintext_block(
        "Cleanup materialized ref",
        cleanup_materialized_ref_name or "<none>",
    )
    summary.append_plaintext_block("Cleanup materialized ref mode", cleanup_materialized_ref_mode)
    summary.append_plaintext_block("Tag creation mode", tag_creation_mode)
    return manifest_path


def run_create_final_tag(args: Namespace) -> Path:
    """Create the immutable exact final Git tag for a released version."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version = args.version
    selected_release = selected_github_release(
        repo=repo,
        version=version,
        expected_selected_rc_tag=getattr(args, "selected_rc_tag", None),
    )
    final_tag = derive_final_tag(version)
    final_tag_message = f"Release {context.component_config.vote_release_name} {version}"
    target_commit = repo.resolve_commit(selected_release.selected_rc_tag)
    repository_slug = _repository_slug_or_none(repo)
    tag_creation_mode, created_ref = _create_or_reuse_annotated_tag(
        repo=repo,
        repository_slug=repository_slug,
        tag_name=final_tag,
        target_commit=target_commit,
        message=final_tag_message,
        allow_update=False,
    )
    manifest_path = _manifest_path(context.component_config.component_id, "create-final-tag")
    summary = _summary_writer()
    write_manifest(
        manifest_path,
        {
            "component": context.component_config.component_id,
            "action": "create-final-tag",
            "version": version,
            "selected_rc_tag": selected_release.selected_rc_tag,
            "final_tag": final_tag,
            "target_commit": target_commit,
            "tag_creation_mode": tag_creation_mode,
            "created_ref": str(created_ref.get("ref") or ""),
        },
    )
    summary.append_heading("Create final tag")
    summary.append_plaintext_block("Selected RC", selected_release.selected_rc_tag)
    summary.append_plaintext_block("Final tag", final_tag)
    summary.append_plaintext_block("Target commit", target_commit)
    summary.append_plaintext_block("Tag creation mode", tag_creation_mode)
    return manifest_path


def run_update_moving_tags(args: Namespace) -> Path:
    """Move Git tag-backed aliases such as GitHub Action major/minor tags without rollback."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version = args.version
    if "github-action" not in context.component_config.secondary_targets:
        raise ValueError("update-moving-tags currently supports only github-action aliases")
    final_tag = derive_final_tag(version)
    if not repo.tag_exists(final_tag):
        raise ValueError(f"final tag does not exist: {final_tag}")
    target_commit = repo.resolve_commit(final_tag)
    repository_slug = _repository_slug_or_none(repo)
    moving_tags = derive_moving_tags(
        version,
        context.component_config.secondary_targets,
        context.component_config.moving_tags_enabled,
        context.component_config.latest_tag_enabled,
    )
    updated_tags: list[str] = []
    skipped_tags: list[str] = []
    tag_update_modes: list[str] = []
    for moving_tag in moving_tags:
        current_version: str | None = None
        if repo.tag_exists(moving_tag):
            current_version = _final_version_for_commit(repo, repo.resolve_commit(moving_tag))
            if current_version is None:
                raise ValueError(f"moving alias does not point at a known final release: {moving_tag}")
        if not _should_move_alias(moving_tag, version, current_version):
            skipped_tags.append(moving_tag)
            continue
        tag_update_mode, _updated_ref = _create_or_reuse_annotated_tag(
            repo=repo,
            repository_slug=repository_slug,
            tag_name=moving_tag,
            target_commit=target_commit,
            message=f"Move {moving_tag} to {final_tag}",
            allow_update=True,
        )
        updated_tags.append(moving_tag)
        tag_update_modes.append(f"{moving_tag}:{tag_update_mode}")
    manifest_path = _manifest_path(context.component_config.component_id, "update-moving-tags")
    summary = _summary_writer()
    write_manifest(
        manifest_path,
        {
            "component": context.component_config.component_id,
            "action": "update-moving-tags",
            "version": version,
            "final_tag": final_tag,
            "target_commit": target_commit,
            "updated_tags": ",".join(updated_tags),
            "skipped_tags": ",".join(skipped_tags),
            "tag_update_modes": ",".join(tag_update_modes),
        },
    )
    summary.append_heading("Update moving tags")
    summary.append_plaintext_block("Final tag", final_tag)
    summary.append_plaintext_block("Target commit", target_commit)
    summary.append_plaintext_block("Updated aliases", "\n".join(updated_tags) if updated_tags else "<none>")
    summary.append_plaintext_block("Skipped aliases", "\n".join(skipped_tags) if skipped_tags else "<none>")
    return manifest_path


def run_update_moving_image_aliases(args: Namespace) -> Path:
    """Resolve the concrete moving container-image aliases for a released version."""

    context = _context(args)
    version = args.version
    image_aliases = derive_moving_tags(
        version,
        context.component_config.secondary_targets,
        context.component_config.moving_tags_enabled,
        context.component_config.latest_tag_enabled,
    )
    manifest_path = _manifest_path(context.component_config.component_id, "update-moving-image-aliases")
    summary = _summary_writer()
    write_manifest(
        manifest_path,
        {
            "component": context.component_config.component_id,
            "action": "update-moving-image-aliases",
            "version": version,
            "exact_image_tag": version,
            "image_aliases": " ".join(image_aliases),
        },
    )
    summary.append_heading("Update moving image aliases")
    summary.append_plaintext_block("Exact image tag", version)
    summary.append_plaintext_block(
        "Derived image aliases",
        " ".join(image_aliases) if image_aliases else "<none>",
    )
    return manifest_path


def run_publish_dockerhub_moving_tags(args: Namespace) -> Path:
    """Publish moving Docker Hub aliases for one already-pushed exact image reference."""

    context = _context(args)
    if "dockerhub" not in context.component_config.secondary_targets:
        raise ValueError("publish-dockerhub-moving-tags requires the dockerhub secondary target")
    version = args.version
    source_image = args.source_image
    image_reference = parse_image_reference(source_image)
    if image_reference.tag is None and image_reference.digest is None:
        raise ValueError("source image must include the released version tag or an exact digest")
    if (
        image_reference.tag is not None
        and image_reference.digest is None
        and image_reference.tag != version
    ):
        raise ValueError(
            f"source image tag {image_reference.tag} does not match released version {version}"
        )
    image_aliases = derive_moving_tags(
        version,
        context.component_config.secondary_targets,
        context.component_config.moving_tags_enabled,
        context.component_config.latest_tag_enabled,
    )
    target_alias_refs = [f"{image_reference.repository}:{alias}" for alias in image_aliases]
    published_alias_refs = publish_moving_aliases(
        source_image=source_image,
        target_alias_refs=target_alias_refs,
    )
    manifest_path = _manifest_path(context.component_config.component_id, "publish-dockerhub-moving-tags")
    summary = _summary_writer()
    write_manifest(
        manifest_path,
        {
            "component": context.component_config.component_id,
            "action": "publish-dockerhub-moving-tags",
            "version": version,
            "source_image": source_image,
            "image_repository": image_reference.repository,
            "published_alias_refs": " ".join(published_alias_refs),
        },
    )
    summary.append_heading("Publish Docker Hub moving tags")
    summary.append_plaintext_block("Source image", source_image)
    summary.append_plaintext_block("Image repository", image_reference.repository)
    summary.append_plaintext_block(
        "Published alias refs",
        "\n".join(published_alias_refs) if published_alias_refs else "<none>",
    )
    return manifest_path


def run_attach_github_release_assets(args: Namespace) -> Path:
    """Upload one or more convenience assets to the GitHub Release for one final version."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version = args.version
    final_tag = derive_final_tag(version)
    repository_slug = resolve_repository_slug(repo.path)
    release_payload = release_by_tag(list_releases(repository_slug), tag_name=final_tag)
    release_id = release_payload.get("id")
    if not isinstance(release_id, int):
        raise ValueError(f"GitHub Release for {final_tag} does not include a numeric id")
    asset_paths = _asset_paths(args.assets)
    prepared_uploads = _prepare_release_asset_uploads(
        asset_paths,
        _deduplicated_checksum_algorithms(args.checksum_algorithms),
        sign=args.sign,
    )
    _assert_unique_upload_asset_names(prepared_uploads.upload_paths)
    upload_release_assets(
        repository_slug,
        tag_name=final_tag,
        asset_paths=prepared_uploads.upload_paths,
        clobber=True,
    )

    manifest_path = _manifest_path(context.component_config.component_id, "attach-github-release-assets")
    summary = _summary_writer()
    release_name = release_payload.get("name")
    release_tag = release_payload.get("tag_name")
    release_url = asset_release_url(release_payload)
    write_manifest(
        manifest_path,
        {
            "component": context.component_config.component_id,
            "action": "attach-github-release-assets",
            "version": version,
            "repository_slug": repository_slug,
            "release_id": str(release_id),
            "release_name": str(release_name or ""),
            "release_tag": str(release_tag or ""),
            "release_url": release_url,
            "primary_asset_names": ",".join(asset_path.name for asset_path in asset_paths),
            "uploaded_asset_names": ",".join(
                upload_path.name for upload_path in prepared_uploads.upload_paths
            ),
            "generated_checksum_asset_names": ",".join(
                checksum_path.name for checksum_path in prepared_uploads.generated_checksum_paths
            ),
            "generated_signature_asset_names": ",".join(
                signature_path.name for signature_path in prepared_uploads.generated_signature_paths
            ),
            "checksum_algorithms": ",".join(prepared_uploads.checksum_algorithms),
            "gpg_fingerprint": prepared_uploads.gpg_fingerprint,
        },
    )
    summary.append_heading("Attach GitHub Release assets")
    summary.append_plaintext_block("GitHub repository", repository_slug)
    summary.append_plaintext_block(
        "GitHub Release",
        "\n".join(
            [
                f"id: {release_id}",
                f"name: {release_name or ''}",
                f"tag: {release_tag or ''}",
                f"url: {release_url}",
            ]
        ),
    )
    summary.append_plaintext_block(
        "Uploaded assets",
        "\n".join(upload_path.name for upload_path in prepared_uploads.upload_paths),
    )
    if prepared_uploads.checksum_algorithms:
        summary.append_plaintext_block(
            "Checksum sidecars",
            "\n".join(prepared_uploads.generated_checksum_lines),
        )
    if prepared_uploads.generated_signature_paths:
        summary.append_plaintext_block(
            "Signature sidecars",
            "\n".join(
                signature_path.name for signature_path in prepared_uploads.generated_signature_paths
            ),
        )
        summary.append_plaintext_block("GPG signing key", prepared_uploads.gpg_fingerprint)
    return manifest_path


def run_finalize_rc_vote_materials(args: Namespace) -> Path:
    """Build, sign, stage, and mirror the authoritative RC vote manifest."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version, state = _resolve_prepare_rc_state_from_args(args, context, repo)
    if not repo.tag_exists(state.rc_tag):
        raise ValueError(f"RC tag does not exist: {state.rc_tag}")
    selected_release = selected_github_release(
        repo=repo,
        version=version,
        expected_selected_rc_tag=state.rc_tag,
    )
    rc_tag_target_commit = repo.resolve_commit(state.rc_tag)
    source_artifact_url = f"{state.staging_url.rstrip('/')}/{state.source_artifact_name}"
    source_artifact_sha512 = verified_staged_source_artifact_sha512(source_artifact_url)
    source_signature_text = read_uri_text(f"{source_artifact_url}.asc").strip()
    output_dir = _artifact_output_dir(context.component_config.component_id)
    secondary_artifacts = _load_secondary_artifacts(args.secondary_artifact_manifests)
    artifacts = _build_rc_vote_manifest_artifacts(
        context,
        state=state,
        selected_release=selected_release,
        rc_tag_target_commit=rc_tag_target_commit,
        source_artifact_sha512=source_artifact_sha512,
        secondary_artifacts=secondary_artifacts,
        output_dir=output_dir,
    )
    authoritative_manifest_url = _stage_rc_vote_manifest_and_mirror(
        context,
        state=state,
        version=version,
        selected_release=selected_release,
        artifacts=artifacts,
    )
    project_vote_email = render_project_rc_vote_email(
        component_config=context.component_config,
        state=state,
        rc_tag_target_commit=rc_tag_target_commit,
        manifest_payload=artifacts.manifest_payload,
        draft_release_url=selected_release.release_url,
    )
    incubator_vote_email = None
    if context.component_config.incubator_vote_enabled:
        incubator_vote_email = render_incubator_rc_vote_email(
            component_config=context.component_config,
            state=state,
            manifest_payload=artifacts.manifest_payload,
        )
    manifest_path = _manifest_path(context.component_config.component_id, "finalize-rc-vote-materials")
    summary = _summary_writer()
    write_manifest(
        manifest_path,
        {
            "component": context.component_config.component_id,
            "action": "finalize-rc-vote-materials",
            "version": version,
            "resolved_source_ref": state.resolved_source_ref,
            "rc_tag": state.rc_tag,
            "final_tag": state.final_tag,
            "rc_tag_target_commit": rc_tag_target_commit,
            "source_artifact_url": source_artifact_url,
            "authoritative_manifest_url": authoritative_manifest_url,
            "authoritative_manifest_sha512": artifacts.manifest_sha512,
            "draft_release_url": selected_release.release_url,
            "secondary_artifact_count": str(len(secondary_artifacts)),
            "mirrored_asset_names": ",".join(_rc_vote_manifest_asset_names(artifacts)),
            "gpg_fingerprint": artifacts.gpg_fingerprint,
        },
    )
    _append_finalize_rc_vote_materials_summary(
        summary,
        context=context,
        version=version,
        state=state,
        selected_release=selected_release,
        rc_tag_target_commit=rc_tag_target_commit,
        source_artifact_sha512=source_artifact_sha512,
        source_signature_text=source_signature_text,
        secondary_artifacts=secondary_artifacts,
        authoritative_manifest_url=authoritative_manifest_url,
        artifacts=artifacts,
        project_vote_email=project_vote_email,
        incubator_vote_email=incubator_vote_email,
    )
    return manifest_path


def run_finalize_draft_github_release(args: Namespace) -> Path:
    """Publish the existing draft GitHub Release for an exact final version."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version = args.version
    expected_selected_rc_tag = getattr(args, "selected_rc_tag", None)
    selected_release = selected_github_release(
        repo=repo,
        version=version,
        expected_selected_rc_tag=expected_selected_rc_tag,
    )
    release_name = _release_name(context, version)
    final_tag = derive_final_tag(version)
    final_tag_target_commit = repo.resolve_commit(selected_release.selected_rc_tag)
    release_id = selected_release.require_release_id(reference_tag=final_tag)
    deleted_asset_names: list[str] = []
    for asset_name, asset_id in release_asset_ids_by_names(
        selected_release.release_payload,
        asset_names=[
            "rc-vote-manifest.json",
            "rc-vote-manifest.json.asc",
            "rc-vote-manifest.json.sha512",
        ],
    ).items():
        delete_release_asset(selected_release.repository_slug, asset_id)
        deleted_asset_names.append(asset_name)
    if selected_release.release_payload.get("draft") is False:
        finalized_release = selected_release.release_payload
        finalize_mode = "already-finalized"
    else:
        finalized_release = update_release(
            selected_release.repository_slug,
            release_id,
            payload={
                "tag_name": final_tag,
                "target_commitish": final_tag_target_commit,
                "draft": False,
                "prerelease": False,
                "name": release_name,
            },
        )
        finalize_mode = "published-draft"
    finalized_release_tag = finalized_release.get("tag_name")
    finalized_release_name = finalized_release.get("name")
    finalized_release_url = asset_release_url(finalized_release)
    manifest_path = _manifest_path(context.component_config.component_id, "finalize-draft-github-release")
    summary = _summary_writer()
    write_manifest(
        manifest_path,
        {
            "component": context.component_config.component_id,
            "action": "finalize-draft-github-release",
            "version": version,
            "repository_slug": selected_release.repository_slug,
            "release_id": str(release_id),
            "release_tag": str(finalized_release_tag or ""),
            "release_name": str(finalized_release_name or ""),
            "release_url": str(finalized_release_url),
            "deleted_asset_names": ",".join(sorted(deleted_asset_names)),
            "finalize_mode": finalize_mode,
        },
    )
    summary.append_heading("Finalize draft GitHub Release")
    summary.append_plaintext_block("GitHub repository", selected_release.repository_slug)
    summary.append_plaintext_block(
        "Removed draft-only assets",
        "\n".join(sorted(deleted_asset_names)) if deleted_asset_names else "<none>",
    )
    summary.append_plaintext_block(
        "Finalized release",
        "\n".join(
            [
                f"id: {release_id}",
                f"name: {finalized_release_name}",
                f"tag: {finalized_release_tag}",
                f"url: {finalized_release_url}",
                f"mode: {finalize_mode}",
            ]
        ),
    )
    announce_email = render_announce_email(
        component_config=context.component_config,
        version=version,
    )
    summary.append_email_template_blocks(
        "ANNOUNCE",
        announce_email.subject,
        announce_email.body,
    )
    return manifest_path


def run_release_version(args: Namespace) -> Path:
    """Resolve final release state, same-line pruning, and moving aliases."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version = args.version
    release_line, state = _resolve_release_version_state(
        context,
        repo,
        version,
        expected_selected_rc_tag=getattr(args, "selected_rc_tag", None),
    )
    manifest_path = _manifest_path(context.component_config.component_id, "release-version")
    summary = _summary_writer()
    write_manifest(
        manifest_path,
        {
            "component": context.component_config.component_id,
            "action": "release-version",
            "version": version,
            "release_line": release_line,
            "selected_rc_tag": state.selected_rc_tag,
            "final_tag": state.final_tag,
            "archive_versions": ",".join(state.archive_versions),
            "release_url": state.release_url,
            "moving_tags": " ".join(state.moving_tags),
            "final_tag_mode": context.component_config.final_tag_mode,
        },
    )
    summary.append_heading("Release version")
    summary.append_plaintext_block("Selected RC", state.selected_rc_tag)
    summary.append_plaintext_block(
        "Archive older same-line releases",
        "\n".join(state.archive_versions) if state.archive_versions else "<none>",
    )
    summary.append_plaintext_block(
        "Derived moving tags", " ".join(state.moving_tags) if state.moving_tags else "<none>"
    )
    if context.component_config.release_summary_include_final_tag_mode:
        summary.append_plaintext_block("Final tag mode", context.component_config.final_tag_mode)
    vote_result_email = render_project_vote_result_email(
        component_config=context.component_config,
        version=version,
        rc_number=_rc_number_from_tag(version, state.selected_rc_tag),
    )
    summary.append_email_template_blocks(
        "Project vote result",
        vote_result_email.subject,
        vote_result_email.body,
    )
    return manifest_path


def run_verify_rc(args: Namespace) -> Path:
    """Emit authoritative RC verification instructions."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version = require_semantic_version(args.version)
    rc_tag = repo.latest_matching_rc_tag(version)
    manifest_path = _manifest_path(context.component_config.component_id, "verify-rc")
    summary = _summary_writer()
    write_manifest(
        manifest_path,
        {
            "component": context.component_config.component_id,
            "action": "verify-rc",
            "version": version,
            "rc_tag": rc_tag,
            "platforms": "linux,macos",
        },
    )
    summary.append_heading("Verify RC")
    summary.append_plaintext_block(
        "Authoritative verification", context.component_config.verify_rc_instructions
    )
    return manifest_path
