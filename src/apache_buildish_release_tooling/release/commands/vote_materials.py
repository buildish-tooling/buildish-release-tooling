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

"""RC vote-manifest generation, staging, and summary commands."""

from __future__ import annotations

import json
import re
from argparse import Namespace
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apache_buildish_release_tooling.release.asf_svn import AsfSvnClient
from apache_buildish_release_tooling.release.email_templates import (
    render_incubator_rc_vote_email,
    render_project_rc_vote_email,
)
from apache_buildish_release_tooling.release.git_repo import GitRepository
from apache_buildish_release_tooling.release.github_release_selection import SelectedGitHubRelease, selected_github_release
from apache_buildish_release_tooling.release.github_releases import update_release, upload_release_assets
from apache_buildish_release_tooling.release.gpg_signing import (
    detached_ascii_sign,
    import_private_key_from_secret,
    secret_key_fingerprint,
)
from apache_buildish_release_tooling.release.manifest import write_manifest
from apache_buildish_release_tooling.release.models import CommandContext, PrepareRcState
from apache_buildish_release_tooling.release.rc_vote_manifest import (
    build_rc_vote_manifest,
    origin_repository_metadata,
    read_uri_text,
)
from apache_buildish_release_tooling.release.rc_vote_verification import verified_staged_source_artifact_sha512
from apache_buildish_release_tooling.release.source_artifact import sha512, write_sha512_file
from apache_buildish_release_tooling.release.summary import SummaryWriter
from apache_buildish_release_tooling.release.verification.bootstrap import (
    VerifyRcBootstrapArtifacts,
    build_verify_rc_bootstrap_artifacts,
)

from apache_buildish_release_tooling.release.commands._shared import (
    _artifact_output_dir,
    _context,
    _manifest_path,
    _resolve_prepare_rc_state_from_args,
    _summary_code,
    _summary_optional_code,
    _temporary_build_dir,
)


@dataclass(frozen=True)
class RcVoteManifestArtifacts:
    """Built and signed authoritative RC vote-manifest artifacts."""

    manifest_payload: dict[str, Any]
    manifest_file_path: Path
    manifest_sha512: str
    manifest_sha512_path: Path
    manifest_signature_path: Path
    gpg_fingerprint: str
    bootstrap_artifacts: VerifyRcBootstrapArtifacts
    supplemental_file_paths: tuple[Path, ...] = ()


@dataclass(frozen=True)
class SecondaryArtifactAttachment:
    """One staged sidecar file attached to a secondary artifact bundle."""

    source_path: Path
    staged_filename: str
    sha512: str


@dataclass(frozen=True)
class LoadedSecondaryArtifact:
    """One secondary artifact plus any local bundle files needed by finalization."""

    manifest_entry: dict[str, Any]
    attachments: tuple[SecondaryArtifactAttachment, ...] = ()


_SHA512_PATTERN = re.compile(r"^[0-9a-fA-F]{128}$")


def _validated_supplemental_filename(filename_value: object, *, manifest_path: Path) -> str:
    if not isinstance(filename_value, str) or not filename_value.strip():
        raise ValueError(
            "secondary artifact inventory filename must be a non-empty string in "
            f"{manifest_path}"
        )
    filename = filename_value.strip()
    if Path(filename).name != filename:
        raise ValueError(
            "secondary artifact inventory filename must be a simple file name in "
            f"{manifest_path}: {filename}"
        )
    return filename


def _inventory_attachments_for_entry(
    manifest_path: Path,
    artifact_entry: dict[str, Any],
) -> tuple[SecondaryArtifactAttachment, ...]:
    inventory = artifact_entry.get("inventory")
    if inventory is None:
        return ()
    if not isinstance(inventory, dict):
        raise ValueError(f"secondary artifact inventory must be a JSON object: {manifest_path}")
    if "filename" not in inventory:
        return ()
    filename = _validated_supplemental_filename(inventory["filename"], manifest_path=manifest_path)
    sha512_value = inventory.get("sha512")
    if not isinstance(sha512_value, str) or not _SHA512_PATTERN.fullmatch(sha512_value.strip().lower()):
        raise ValueError(f"secondary artifact inventory must declare a valid sha512 in {manifest_path}")
    inventory_path = manifest_path.parent / filename
    if not inventory_path.is_file():
        raise ValueError(f"secondary artifact inventory file does not exist: {inventory_path}")
    normalized_sha512 = sha512_value.strip().lower()
    if sha512(inventory_path) != normalized_sha512:
        raise ValueError(f"secondary artifact inventory sha512 does not match the file bytes: {inventory_path}")
    return (
        SecondaryArtifactAttachment(
            source_path=inventory_path,
            staged_filename=filename,
            sha512=normalized_sha512,
        ),
    )


def _load_secondary_artifacts(manifest_paths: Iterable[str]) -> list[LoadedSecondaryArtifact]:
    """Load generic secondary-artifact entries from one or more JSON manifest files."""

    secondary_artifacts: list[LoadedSecondaryArtifact] = []
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
            manifest_entry = dict(artifact_entry)
            secondary_artifacts.append(
                LoadedSecondaryArtifact(
                    manifest_entry=manifest_entry,
                    attachments=_inventory_attachments_for_entry(manifest_path, manifest_entry),
                )
            )
    return secondary_artifacts


def _resolved_secondary_artifacts(
    staging_url: str,
    secondary_artifacts: list[LoadedSecondaryArtifact],
) -> tuple[list[dict[str, Any]], tuple[Path, ...]]:
    resolved_entries: list[dict[str, Any]] = []
    staged_files_by_name: dict[str, str] = {}
    supplemental_file_paths: list[Path] = []
    staging_url = staging_url.rstrip("/")
    for artifact in secondary_artifacts:
        manifest_entry = dict(artifact.manifest_entry)
        inventory = manifest_entry.get("inventory")
        if artifact.attachments and not isinstance(inventory, dict):
            raise ValueError(
                "secondary artifact bundle attachments require an inventory object in the manifest entry"
            )
        if isinstance(inventory, dict) and artifact.attachments:
            inventory_payload = dict(inventory)
            filename = _validated_supplemental_filename(
                inventory_payload.get("filename"),
                manifest_path=artifact.attachments[0].source_path,
            )
            attachment = next(
                (candidate for candidate in artifact.attachments if candidate.staged_filename == filename),
                None,
            )
            if attachment is None:
                raise ValueError(
                    "secondary artifact inventory filename did not match any local bundle file: "
                    f"{filename}"
                )
            inventory_payload["sha512"] = attachment.sha512
            inventory_payload["uri"] = f"{staging_url}/{attachment.staged_filename}"
            manifest_entry["inventory"] = inventory_payload
        for attachment in artifact.attachments:
            existing_sha512 = staged_files_by_name.get(attachment.staged_filename)
            if existing_sha512 is not None and existing_sha512 != attachment.sha512:
                raise ValueError(
                    "duplicate secondary artifact supplemental filename with different content: "
                    f"{attachment.staged_filename}"
                )
            if existing_sha512 is None:
                staged_files_by_name[attachment.staged_filename] = attachment.sha512
                supplemental_file_paths.append(attachment.source_path)
        resolved_entries.append(manifest_entry)
    return resolved_entries, tuple(supplemental_file_paths)


def _build_rc_vote_manifest_artifacts(
    context: CommandContext,
    *,
    state: PrepareRcState,
    selected_release: SelectedGitHubRelease,
    rc_tag_target_commit: str,
    source_artifact_sha512: str,
    secondary_artifacts: list[dict[str, Any]],
    supplemental_file_paths: tuple[Path, ...],
    output_dir: Path,
) -> RcVoteManifestArtifacts:
    """Build and sign the authoritative RC vote-manifest artifacts."""

    manifest_file_path = output_dir / "rc-vote-manifest.json"
    staging_url = state.staging_url.rstrip("/")
    manifest_url = f"{staging_url}/{manifest_file_path.name}"
    keys_url = context.component_config.asf_keys_url
    with _temporary_build_dir("finalize-rc-vote-materials") as temp_root:
        gpg_home = temp_root / "gnupg"
        import_private_key_from_secret(gpg_home)
        gpg_fingerprint = secret_key_fingerprint(gpg_home)
        bootstrap_artifacts = build_verify_rc_bootstrap_artifacts(
            output_dir=output_dir,
            manifest_url=manifest_url,
            keys_url=keys_url,
            gpg_home=gpg_home,
        )
        _repository_slug, source_repository_url = origin_repository_metadata(
            GitRepository.from_current_worktree()
        )
        manifest_payload = build_rc_vote_manifest(
            component_config=context.component_config,
            state=state,
            repository_slug=selected_release.repository_slug,
            source_repository_url=source_repository_url,
            draft_release_tag=selected_release.require_release_tag(reference_tag=state.rc_tag),
            draft_release_url=selected_release.release_url,
            rc_tag_target_commit=rc_tag_target_commit,
            source_artifact_sha512=source_artifact_sha512,
            secondary_artifacts=secondary_artifacts,
        )
        write_manifest(manifest_file_path, manifest_payload)
        manifest_sha512 = sha512(manifest_file_path)
        manifest_sha512_path = write_sha512_file(manifest_file_path, manifest_sha512)
        manifest_signature_path = manifest_file_path.with_name(f"{manifest_file_path.name}.asc")
        detached_ascii_sign(gpg_home, manifest_file_path, manifest_signature_path)
        return RcVoteManifestArtifacts(
            manifest_payload=manifest_payload,
            manifest_file_path=manifest_file_path,
            manifest_sha512=manifest_sha512,
            manifest_sha512_path=manifest_sha512_path,
            manifest_signature_path=manifest_signature_path,
            gpg_fingerprint=gpg_fingerprint,
            bootstrap_artifacts=bootstrap_artifacts,
            supplemental_file_paths=supplemental_file_paths,
        )


def _rc_vote_manifest_asset_paths(artifacts: RcVoteManifestArtifacts) -> list[Path]:
    return [
        artifacts.manifest_file_path,
        artifacts.manifest_sha512_path,
        artifacts.manifest_signature_path,
        artifacts.bootstrap_artifacts.script_path,
        artifacts.bootstrap_artifacts.script_sha512_path,
        artifacts.bootstrap_artifacts.script_signature_path,
        *artifacts.supplemental_file_paths,
    ]


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
        for asset_path in _rc_vote_manifest_asset_paths(artifacts):
            svn_client.working_copy_put_file(
                staging_wc,
                asset_path,
                asset_path.name,
            )
        svn_client.commit_working_copy(
            staging_wc,
            f"stage RC vote manifest for {context.component_config.component_id} {version}",
        )
    upload_release_assets(
        selected_release.repository_slug,
        tag_name=selected_release.require_release_tag(reference_tag=state.rc_tag),
        asset_paths=_rc_vote_manifest_asset_paths(artifacts),
        clobber=True,
    )
    authoritative_manifest_url = f"{staging_url}/{artifacts.manifest_file_path.name}"
    _update_draft_release_body(
        context,
        state=state,
        selected_release=selected_release,
        authoritative_manifest_url=authoritative_manifest_url,
        artifacts=artifacts,
    )
    return authoritative_manifest_url


def _rc_vote_manifest_asset_names(artifacts: RcVoteManifestArtifacts) -> list[str]:
    """Return the authoritative RC vote-manifest asset names in mirror order."""

    return [path.name for path in _rc_vote_manifest_asset_paths(artifacts)]


def _update_draft_release_body(
    context: CommandContext,
    *,
    state: PrepareRcState,
    selected_release: SelectedGitHubRelease,
    authoritative_manifest_url: str,
    artifacts: RcVoteManifestArtifacts,
) -> None:
    """Update the selected draft GitHub Release body with RC verification details."""

    update_release(
        selected_release.repository_slug,
        selected_release.require_release_id(reference_tag=state.rc_tag),
        payload={
            "body": _draft_release_body(
                context,
                state=state,
                authoritative_manifest_url=authoritative_manifest_url,
                artifacts=artifacts,
            )
        },
    )


def _draft_release_body(
    context: CommandContext,
    *,
    state: PrepareRcState,
    authoritative_manifest_url: str,
    artifacts: RcVoteManifestArtifacts,
) -> str:
    """Render the finalized draft GitHub Release body with verification bootstrap details."""

    bootstrap_script_url = f"{state.staging_url.rstrip('/')}/{artifacts.bootstrap_artifacts.script_path.name}"
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
            "Authoritative RC vote manifest:",
            f"- {authoritative_manifest_url}",
            f"- {authoritative_manifest_url}.sha512",
            f"- {authoritative_manifest_url}.asc",
            "",
            "Verification bootstrap convenience:",
            f"- {bootstrap_script_url}",
            f"- {bootstrap_script_url}.sha512",
            f"- {bootstrap_script_url}.asc",
            "",
            "Verify RC bootstrap one-liner:",
            "",
            "```sh",
            artifacts.bootstrap_artifacts.invoker_snippet,
            "```",
            "",
            "This draft release is convenience metadata only and must remain unpublished until the ASF vote passes.",
        ]
    )


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
    bootstrap_script_url = f"{state.staging_url.rstrip('/')}/{artifacts.bootstrap_artifacts.script_path.name}"
    summary.append_code_block(
        "Verification bootstrap one-liner",
        "sh",
        artifacts.bootstrap_artifacts.invoker_snippet,
    )
    summary.append_plaintext_block(
        "Verification bootstrap note",
        "The bootstrap script is a signed convenience layer around the verifier. "
        "The signed RC vote manifest and ASF KEYS remain the trust anchors.\n"
        f"Bootstrap script: {bootstrap_script_url}",
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
    loaded_secondary_artifacts = _load_secondary_artifacts(args.secondary_artifact_manifests)
    secondary_artifacts, supplemental_file_paths = _resolved_secondary_artifacts(
        state.staging_url,
        loaded_secondary_artifacts,
    )
    artifacts = _build_rc_vote_manifest_artifacts(
        context,
        state=state,
        selected_release=selected_release,
        rc_tag_target_commit=rc_tag_target_commit,
        source_artifact_sha512=source_artifact_sha512,
        secondary_artifacts=secondary_artifacts,
        supplemental_file_paths=supplemental_file_paths,
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
        bootstrap_script_url=f"{state.staging_url.rstrip('/')}/{artifacts.bootstrap_artifacts.script_path.name}",
        bootstrap_invoker=artifacts.bootstrap_artifacts.invoker_snippet,
    )
    incubator_vote_email = None
    if context.component_config.incubator_vote_enabled:
        incubator_vote_email = render_incubator_rc_vote_email(
            component_config=context.component_config,
            state=state,
            manifest_payload=artifacts.manifest_payload,
            bootstrap_script_url=(
                f"{state.staging_url.rstrip('/')}/{artifacts.bootstrap_artifacts.script_path.name}"
            ),
            bootstrap_invoker=artifacts.bootstrap_artifacts.invoker_snippet,
        )
    manifest_path = _manifest_path(context.component_config.component_id, "finalize-rc-vote-materials")
    summary = SummaryWriter.from_environment()
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
            "bootstrap_script_url": (
                f"{state.staging_url.rstrip('/')}/{artifacts.bootstrap_artifacts.script_path.name}"
            ),
            "bootstrap_script_sha512": artifacts.bootstrap_artifacts.script_sha512,
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
