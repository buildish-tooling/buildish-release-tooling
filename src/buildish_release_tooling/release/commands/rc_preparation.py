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

"""RC preparation and source-artifact staging commands."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from buildish_release_tooling.release.config import (
    require_asf_profile,
    require_openpgp_signing,
)
from buildish_release_tooling.release.foundations.asf.dist import AsfSvnClient, url_join
from buildish_release_tooling.release.command_manifests import (
    BuildSourceRcManifest,
    CleanupDevSvnRcsManifest,
    CreateSourceArtifactManifest,
    PrepareRcManifest,
)
from buildish_release_tooling.release.git_repo import GitRepository
from buildish_release_tooling.release.signing.openpgp import (
    OpenPgpSigner,
    OpenPgpSigningInput,
)
from buildish_release_tooling.release.manifest import write_manifest
from buildish_release_tooling.release.source_artifact import (
    create_from_git,
    sha512,
    write_sha512_file,
)
from buildish_release_tooling.release.summary import SummaryWriter

from buildish_release_tooling.release.commands._shared import (
    _append_github_outputs,
    _artifact_output_dir,
    _context,
    _manifest_path,
    _matching_dev_rc_entries,
    _resolve_prepare_rc_state_from_args,
    _summary_code,
    _temporary_build_dir,
)


def run_prepare_rc(args: Namespace) -> Path:
    """Resolve RC state and emit the summary/manifests used by the draft workflow."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version, state = _resolve_prepare_rc_state_from_args(args, context, repo)
    manifest_path = _manifest_path(context.release_config.component.id, "prepare-rc")
    summary = SummaryWriter.from_environment()
    manifest_entries = PrepareRcManifest(
        component=context.release_config.component.id,
        version=version,
        resolved_source_ref=state.resolved_source_ref,
        source_date_epoch=str(state.source_date_epoch),
        resolved_release_branch=state.resolved_release_branch,
        rc_number=str(state.rc_number),
        rc_tag=state.rc_tag,
        final_tag=state.final_tag,
        source_artifact_name=state.source_artifact_name,
        source_artifact_root_name=state.source_artifact_root_name,
        source_artifact_prefix_path=state.source_artifact_prefix_path,
        staging_url=state.candidate_publication_uri,
        final_tag_mode=context.release_config.tags.final_mode,
    )
    write_manifest(manifest_path, manifest_entries)
    _append_github_outputs(
        {
            "version": manifest_entries.version,
            "rc_tag": manifest_entries.rc_tag,
            "resolved_source_ref": manifest_entries.resolved_source_ref,
            "source_date_epoch": manifest_entries.source_date_epoch,
        }
    )
    summary.append_heading("Prepare RC")
    summary.append_plaintext_block("Resolved source", state.resolved_source_ref)
    summary.append_plaintext_block("SOURCE_DATE_EPOCH", str(state.source_date_epoch))
    summary.append_plaintext_block("RC identity", state.rc_tag)
    summary.append_plaintext_block(
        "ASF SVN staging cleanup",
        f"Delete and recreate {state.candidate_publication_uri} before staging the new RC.",
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
    dev_base_url = require_asf_profile(context.release_config).dist_dev_base.rstrip("/")
    if svn_client.path_exists(dev_base_url):
        deleted_rc_entries = _matching_dev_rc_entries(svn_client.list_entries(dev_base_url), version)
    else:
        deleted_rc_entries = []
    for entry in deleted_rc_entries:
        svn_client.delete_url(
            url_join(dev_base_url, entry),
            f"delete pre-existing RC staging for {context.release_config.component.id} {version}",
        )
    manifest_path = _manifest_path(context.release_config.component.id, "cleanup-dev-svn-rcs")
    summary = SummaryWriter.from_environment()
    write_manifest(
        manifest_path,
        CleanupDevSvnRcsManifest(
            component=context.release_config.component.id,
            version=version,
            dev_base_url=f"{dev_base_url}/",
            deleted_rc_directories=deleted_rc_entries,
        ),
    )
    summary.append_heading(f"Cleanup ASF SVN dev/dist for version {version}")
    summary.append_key_value_table(
        "Technical details",
        [
            ("Component", _summary_code(context.release_config.component.id)),
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
    version, state = _resolve_prepare_rc_state_from_args(args, context, repo)
    output_dir = _artifact_output_dir(context.release_config.component.id)
    artifact_path = output_dir / state.source_artifact_name
    create_from_git(repo.path, state.resolved_source_ref, state.source_artifact_prefix_path, artifact_path)
    artifact_sha512 = sha512(artifact_path)
    manifest_path = _manifest_path(context.release_config.component.id, "create-source-artifact")
    summary = SummaryWriter.from_environment()
    write_manifest(
        manifest_path,
        CreateSourceArtifactManifest(
            component=context.release_config.component.id,
            version=version,
            resolved_source_ref=state.resolved_source_ref,
            source_date_epoch=str(state.source_date_epoch),
            source_artifact_name=state.source_artifact_name,
            source_artifact_path=str(artifact_path),
            source_artifact_sha512=artifact_sha512,
        ),
    )
    summary.append_heading("Source Artifact")
    summary.append_plaintext_block("Source artifact path", str(artifact_path))
    summary.append_plaintext_block("Source artifact ref", state.resolved_source_ref)
    summary.append_plaintext_block("SOURCE_DATE_EPOCH", str(state.source_date_epoch))
    summary.append_sha512_block(state.source_artifact_name, artifact_sha512)
    return manifest_path


def run_build_source_rc(args: Namespace) -> Path:
    """Build, sign, and stage a source RC into ASF SVN."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version, state = _resolve_prepare_rc_state_from_args(args, context, repo)
    output_dir = _artifact_output_dir(context.release_config.component.id)
    artifact_path = output_dir / state.source_artifact_name
    with _temporary_build_dir("build-source-rc") as temp_root:
        gpg_home = temp_root / "gnupg"
        staging_wc = temp_root / "staging-wc"
        create_from_git(repo.path, state.resolved_source_ref, state.source_artifact_prefix_path, artifact_path)
        artifact_sha512 = sha512(artifact_path)
        sha512_path = write_sha512_file(artifact_path, artifact_sha512)
        signer = OpenPgpSigner.from_environment(
            gpg_home,
            OpenPgpSigningInput.from_config(
                require_openpgp_signing(context.release_config)
            ),
        )
        asc_path = artifact_path.with_name(f"{artifact_path.name}.asc")
        signer.sign_file(artifact_path, asc_path)

        svn_client = AsfSvnClient.from_environment()
        staging_url = state.candidate_publication_uri.rstrip("/")
        if svn_client.path_exists(staging_url):
            svn_client.delete_url(
                staging_url,
                f"delete existing RC staging for {context.release_config.component.id} {version}",
            )
        svn_client.mkdir_url(
            staging_url,
            f"create RC staging for {context.release_config.component.id} {version}",
        )
        svn_client.checkout_url(staging_url, staging_wc)
        svn_client.working_copy_put_file(staging_wc, artifact_path, artifact_path.name)
        svn_client.working_copy_put_file(staging_wc, sha512_path, sha512_path.name)
        svn_client.working_copy_put_file(staging_wc, asc_path, asc_path.name)
        svn_client.commit_working_copy(
            staging_wc,
            f"stage RC source artifacts for {context.release_config.component.id} {version}",
        )
        manifest_path = _manifest_path(context.release_config.component.id, "build-source-rc")
        summary = SummaryWriter.from_environment()
        write_manifest(
            manifest_path,
            BuildSourceRcManifest(
                component=context.release_config.component.id,
                version=version,
                resolved_source_ref=state.resolved_source_ref,
                source_date_epoch=str(state.source_date_epoch),
                rc_tag=state.rc_tag,
                source_artifact_name=state.source_artifact_name,
                source_artifact_path=str(artifact_path),
                source_artifact_sha512=artifact_sha512,
                source_artifact_sha512_path=str(sha512_path),
                source_artifact_asc_path=str(asc_path),
                gpg_fingerprint=signer.fingerprint,
                staging_url=f"{staging_url}/",
            ),
        )
        summary.append_heading("Build Source RC")
        summary.append_plaintext_block("Source artifact path", str(artifact_path))
        summary.append_plaintext_block("Source artifact ref", state.resolved_source_ref)
        summary.append_plaintext_block("SOURCE_DATE_EPOCH", str(state.source_date_epoch))
        summary.append_plaintext_block("ASF SVN staged RC URL", f"{staging_url}/")
        summary.append_sha512_block(state.source_artifact_name, artifact_sha512)
        summary.append_signature_block(state.source_artifact_name, asc_path)
        return manifest_path
